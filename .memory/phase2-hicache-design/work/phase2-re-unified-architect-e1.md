# phase2-re-unified-architect-e1 — 统一 restore eligibility 语义模型（read-only 设计）

```text
status: done
artifacts:
  - 本报告（read-only 架构设计，未改任何代码；spec 供后续 coder 实现）
  - 本轮 coder 实现范围（用户裁决 ledger:2113）：per-anchor 版本修正 + no-material fast-forward，
    不做统一状态机重写
evidence:
  - 仓库 /home/charles/Workspaces/3rdparty/sglang-3090-24g-opt（分支 3090-24g-opt，HEAD=3c71553a20）
  - unified_tree_core.py：l3_publish_epoch 字段 :517 / _bump_l3_publish :2119 / is_l3_durable :2200 /
    mark_storage_restored :2111（bump）/ advance_storage_persisted :2209 / _promote_persisted_subtree :2229
    （bump :2245）/ clear_storage_durable :2132 / deferred_acked_nodes :2185 / is_backuped :531 / is_root :540
  - hicache_restore.py：miss_rearm_allowed :227-250 / next_restore（T4 :123 / T5 :132 / T6 :134 / T9 :156 /
    T12 :173 / T13 :178 / T15 :189）/ too_short_wait_armed :281 / wait_reason_for :202
  - scheduler.py：miss epoch 记录 :3216-3226 / ready-horizon NO_L3 负缓存 cursor :3240-3244 /
    T6 re-arm :4546-4556 / GATE_SKIP_FRONTIER :3064-3068 / _reconcile_restore_states :3076
  - unified_radix_cache.py：frontier_anchor_ready :2490 / has_restore_potential :3191-3228 /
    prompt_can_qualify_for_prefetch :3178 / register_frontier_waiter :3105 / _wake_frontier_waiters :3155 /
    chain_backup_frontiers :2389 / backup_wait_ready :2427
  - 先验：work/phase2-churn-rebound-architect-e1.md（§5 修正方向）、phase2-restorearm-architect-e3.md、
    phase2-tooshort-architect-e1.md、phase2-p3-closeout-architect-e1.md（no-material 前向判定 followup）
  - 用户裁决：ledger.md:2106-2118（统一模型五态 / per-anchor + no-material 本轮实现 / 禁止 heuristic）
summary:
  Conclusion
  Current Architecture
  Problem / Forces
  Proposed Architecture
  Alternatives
  Migration / Impact
  Open Decisions
followups:
  - 见 §8：本轮 coder 实现范围（per-anchor + no-material）与后续扩展路径
open_issues:
  - 见 §7 Open Decisions：4 项待确认（clear 是否 bump / anchor 删除处理 / no-material 作用域 / NO_L3 cursor 是否同步）
```

## Conclusion（一页裁决）

统一 restore eligibility 的核心不是加一个状态、而是把**每一种拒绝态都改写成同一个四元组**：
**negative evidence（什么事实证明此刻不可 restore）/ anchor binding（证据绑定到哪个具体节点/前缀/链）/
rearm condition（哪类锚定因果状态变化才解除证据）/ forward fallback（被拒后的前进路径）**。五种拒绝态全部落进这个契约，差异只在"锚定对象"与"有无在途因果生产者"两个维度。

**统一判别（一句话）**：候选的 eligibility 只能因 (a) 锚定因果状态实质变化（rearm），(b) 新候选身份（generation/prefix/anchor 变），(c) forward fallback 执行而改变——**禁止**计时器、次数计数、全局事件作为 re-arm 判据。

**五种拒绝态的二分类**（关键结构洞察）：

- **有在途因果生产者（live producer）→ 等待该生产者的 ACK/前移**：capacity-headroom wait（等资源释放）、durable-frontier pending（等同一锚的 L3 写 ack / restore 读回前移）。
- **无在途因果生产者（dead-end）→ 立即 forward，不等待**：definitive miss（L3 缺失且无该锚物材化在途）、too_short never-case（几何上永不达标）、no-material（锚永无物材化在途）。

"无在途生产者"正是 P1 sticky miss、too_short never-case、no-material fast-forward 三者的共同结构：**负证据对该候选是终局的，等待零期望 → 立即 forward；re-arm 只对锚定实质变化（产生新在途生产者）或新候选开放**。这就是用户预警的第三种同构 churn 的统一语义。

**本轮实现边界**（用户裁决 ledger:2113，不越界）：
1. **per-anchor/per-chain version**：把 `miss_rearm_allowed` 与 ready-horizon NO_L3 cursor 从全局 `l3_publish_epoch` 改锚到 anchor 级版本；全局 epoch 降为纯诊断。
2. **no-material fast-forward**：对"明确无任何可恢复物材"的 FRONTIER_WAIT 直接 ADMIT_RECOMPUTE。
统一状态机骨架**只出接口契约**，不重写既有状态机。

---

## Current Architecture（证据核实）

### 现存的四类 re-arm/拒绝判据（各自为政，粒度/信号不一致）

| 拒绝态 | 当前代码 | 现判据 | 现锚定 | 缺陷 |
|---|---|---|---|---|
| **definitive miss** | hicache_restore.py:227-250 `miss_rearm_allowed` + scheduler.py:4546-4556 T6 | `current_epoch > miss_epoch`（全局）+ generation | **全局** l3_publish_epoch | 无关链 bump 也放行（churn-rebound-e1 判定 2：并发下恒放行） |
| **too_short** | unified_radix_cache.py:3178-3228 `prompt_can_qualify_for_prefetch`/`has_restore_potential` + hicache_restore.py:123-131 DENIED_SHORT | 几何（suffix < prefetch_threshold，含理论最大） | **请求几何**（prompt_len/host_hit_length），非节点 | 已收口（too_short-fix）；无 re-arm 路径，直接 recompute |
| **no-material（FRONTIER 无物材）** | scheduler.py:3064-3068 GATE_SKIP_FRONTIER + unified_radix_cache.py:2490 frontier_anchor_ready | anchor 非 durable → park frontier waiter | **anchor** | 无在途生产者时 idle 满 60s T13（P3-closeout followup，rid 9d8b5428） |
| **capacity-headroom wait** | scheduler.py:4526/4570+ hicache_restore.py:134 T6 / :168 T11 / :295 promotion_budget_fits | 容量 charge < available+evictable | **资源**（charge/锚） | 正交（Fix A 资源 epoch）；当前对 miss 与纯容量不区分 re-arm |
| **durable-frontier pending** | hicache_restore.py:173 T12 / :189 T15 + unified_radix_cache.py:2389-2444 | durable frontier < requested end，有在途写 | **anchor/链** | 已收口（P3 A+B）；ACk 驱动唤醒 |

### 证据要点

- **全局 epoch 是"状态变化的代理信号"**（unified_tree_core.py:2119-2130 `_bump_l3_publish` 每次 promotion/restore 读回 bump 全局计数，:2245）。它不携带"哪个锚"信息 → 8-agent 并发下任意无关链写 ack 都 bump → 全局前移解除无关 MISS（churn-rebound-e1 判定 2，观测 0→3902、~2.1/s）。
- **miss 负证据当前锚在全局**：scheduler.py:3216-3226 记 `hicache_restore_miss_epoch = l3_publish_epoch()`（全局），re-arm 只对比全局 → 秒级失效。
- **ready-horizon NO_L3 负缓存同病**：scheduler.py:3240-3244 cursor = 全局 epoch（RH 专用，但同一代理缺陷的第二个受害者）。
- **too_short 已收口为"几何终局"**：`prompt_can_qualify_for_prefetch`（can-never-qualify）→ `has_restore_potential` False → 不 park WAIT，直接 recompute；device-match-decay bet 保留为 REVALIDATE（当前 sub-threshold 但 decay 后可增长）。
- **P3 durable-frontier HOL 已收口**（P3-closeout confirmed）：A+B 补链 + clear 守卫；剩余 9d8b5428 单例 = 纯设备链无在途生产者 → 60.3s 满 T13 idle，已分类为正确兜底（非 HOL），但正是"no-material 应立即 forward"的缺口。

---

## Problem / Forces

- **代理信号失效**：restore eligibility 语义是"该候选的因果状态变化"，但当前以全局 epoch 作代理，在并发下代理与语义脱钩（解除无关 MISS / 放行过多 re-probe）。
- **拒绝态各自为政**：五种拒绝态分处 4 个模块（tree_core / radix_cache / scheduler / hicache_restore），re-arm 判据粒度不一（全局计数 vs 几何 vs 资源 vs anchor），无法统一演进；每次新 churn 都堆补丁。
- **"无在途生产者"被当"有在途生产者"处理**：definitive miss / too_short never-case / no-material 都是终局负证据，当前或空等（no-material idle 60s）或因全局事件误放行（miss）。统一后全部立即 forward。
- **用户硬约束**：禁止 TTL / 次数计数 / 全局 epoch / "任意 L3 写发生即重试"作为 re-arm 判据（ledger:2112）。re-arm 必须 = "与该候选相关的实质变化"。
- **本轮不做大重构**（ledger:2113）：先定义统一模型 + 只实现 per-anchor + no-material；统一状态机骨架仅出契约。

---
## Proposed Architecture（统一模型）

### 1. 统一契约：五态 × 四元组（用户 Deliverable 1）

每条拒绝态统一写成四元组：**negative evidence / anchor binding / rearm condition / forward fallback**。

| 拒绝态 | negative evidence（什么事实证明此刻不可 restore） | anchor binding（绑定到哪个具体节点/前缀/链） | rearm condition（哪类锚定因果状态变化才解除） | forward fallback（被拒后的前进路径） |
|---|---|---|---|---|
| **1. definitive miss** | 该候选前缀在**某时刻、以某版本**被探针证明 L3 缺失（storage query 命中 0） | **候选锚节点/前缀 + 锚版本**（本次 miss 时刻该锚的 version）+ identity(generation/prefix) | 该锚的**实质 L3 物材化变化**：锚 version 前移（该锚发生写 ack promotion 或 restore 读回）；或 identity 变（generation/prefix 变） | **ADMIT_RECOMPUTE**（立即 recompute 尾段，不等待） |
| **2. too_short（never-case）** | 该候选的当前后缀**与理论最大后缀都 < prefetch_threshold**（can-never-qualify，几何终局） | **请求几何**（prompt_len / host_hit_length / 锚位置），非节点 | 无——终局；除非 identity 变（新 prefix 几何不同）。device-match-decay bet（当前 sub-threshold 但 decay 后可达）**不属于**此态，保留 REVALIDATE | **ADMIT_RECOMPUTE**（立即，too_short-fix 已收口） |
| **3. no-material（FRONTIER 无物材）** | 锚非 durable，且**无任何在途因果生产者**（无 L3 写 pending/在途 restore 读回/将来物材化的写 ack） | **锚节点/链** | 有在途生产者出现（锚被写 pending / 有 restore 读回在途）→ 转 durable-frontier pending；或 identity 变 | **ADMIT_RECOMPUTE**（立即，不等 60s T13）——本轮实现 |
| **4. capacity-headroom wait** | 设备容量不足（charge > available+evictable），**资源侧在途**（等释放） | **资源/请求 charge**（与锚正交，但同一候选） | **资源实质变化**：available+evictable 前移（headroom release，Fix A 资源 epoch）；或候选 charge 变小（device 命中增长） | 等资源（T13 兜底）→ 超时后 **ADMIT_RECOMPUTE** |
| **5. durable-frontier pending** | 链仅部分 durable（durable frontier < requested end），但**有在途 L3 写**（target >= requested） | **锚/链 + 在途写 op** | 该锚 durable frontier 前移越过 requested end（**同锚** ACK 驱动） | 等 ack（T15/T12）→ frontier ready 后 RETRY_PREFETCH（P3 已收口） |

**二分类（结构洞察）**：
- **有在途因果生产者**（态 4、5，及态 3 的反面）：等待该生产者的 ACK/前移即可，无需 re-arm 事件。
- **无在途因果生产者**（态 1、2、3）：负证据终局，等待零期望 → **立即 forward**；仅锚定实质变化（新在途生产者出现）或新候选才恢复资格。

### 2. per-anchor/per-chain version 统一定义（用户 Deliverable 2，本轮实现）

**version 挂哪**：挂**锚节点**上（`UnifiedTreeNode` 新增单调字段 `storage_version: int`，或等价地每个锚节点一个计数）。version 的"锚"语义 = **触发事件的节点所在持久链的最深 durable 锚**。

**何时 bump（仅该锚相关 durability 事件）**：与 `_bump_l3_publish` 同源、粒度收窄——仅在写 ack promotion 或 restore 读回**作用于该锚所在链**时 bump 该锚的 version。三个 bump 点（对应现有树核 `_bump_l3_publish` 调用点）：
- `mark_storage_restored(node_id)`（:2111-2117）：bump **node 所在链的锚** version。
- `_promote_persisted_subtree(node)`（:2229-2246）：bump **node 所在链的锚** version（即被 promotion 的 node 的持久链锚）。
- 具体到"哪个节点是锚"：对 miss 判定而言，**锚 = 请求 miss 时其探针覆盖的最深 durable 祖先**（即请求前缀与持久链的相接点）。reconcile 补链 `write_backup_storage` + `advance_storage_persisted` 产生真实写 ack promotion 时，同样 bump 其所在链锚。

**与全局 l3_publish_epoch 的关系**：`_bump_l3_publish` 保留（每次 bump 同时 bump 对应锚 version + 全局计数），**全局计数降为纯诊断统计，不参与任何门判定**。`miss_rearm_allowed` 与 NO_L3 cursor 只读锚 version。

**anchor 被 clear/删除/重新锚定 root 时的 version 处理**（用户明确要求）：
- **clear_storage_durable（:2132）**：清 durability 信念时**bump 该锚 version**（这是该锚的实质状态变化——从 durable 变非 durable，同样是"锚状态实质变化"，应按同一规则解除/重挂依赖它的负证据）。在既有 `_has_deferred_acked_descendant` B 守卫下：有 deferred 后代时不清也不 bump（P3 语义保持）；实际清除时 bump。
- **节点物理删除/evict**：锚节点从 arena 移除 → 依赖它的负证据（miss 记录 / NO_L3 park / frontier waiter）应**失效**（self-heal 到 re-match from root，与既有 `frontier_anchor_ready` node_exists→True 语义一致）；重锚定到 root 即身份/锚改变，等价新候选。
- **重新锚定 root**：锚身份变化 = 新候选 → 旧负证据不适用，允许 re-arm（等价 generation/prefix 变化）。
- **语义铁律**：version 单调、**只反映该锚的 durability 事件**；绝不被无关锚事件 bump；不因容量/调度事件 bump（容量是资源 epoch，Fix A 领域）。

**锚 version 与 generation 的并集**：`miss_rearm_allowed` 新签名——
```
rearm_allowed =
    identity_changed(generation/prefix/anchor)          # 新候选，旧证据作废
    OR anchor_version_now > miss_anchor_version          # 该锚实质 durability 变化
```
移除了 `current_epoch > miss_epoch`（全局）。`miss_epoch` 字段改为 `miss_anchor_version` + `miss_anchor_id`；若请求在 miss 时锚已被删（无锚），记 identity 即可，靠 generation/prefix 变 re-arm。

### 3. 统一状态机骨架（用户 Deliverable 3，本轮不实现，仅接口契约）

**统一接口**（骨架第一步，per-anchor 修正即它的首例落地，不排斥后续扩展）：
```
RestoreEligibility:
    negative_evidence() -> Evidence          # 此刻不可 restore 的事实（结构化：kind + anchor + version/geometry/resource）
    anchor_binding() -> AnchorRef | Geometry | Resource   # 证据绑定对象
    has_inflight_producer() -> bool          # 有无在途因果生产者（决定等待 vs 立即 forward）
    rearm_condition() -> Predicate           # 锚定因果状态变化的精确解除条件（禁用全局/计数/TTL）
    forward_fallback() -> Decision           # ADMIT_RECOMPUTE | RETRY_PREFETCH | WAIT
```
- **二分类路由**：`has_inflight_producer()` True → 等待生产者的 ACK/前移（态 4/5）；False → `forward_fallback()` 立即执行（态 1/2/3），仅在 `rearm_condition()` 满足或新候选时重新评估。
- **per-anchor 修正 = 骨架的态 1 特例**：`definitive miss` 的 `anchor_binding = (锚, version)`、`rearm_condition = 锚 version 前移 or identity 变`、`forward_fallback = ADMIT_RECOMPUTE`。既有 `miss_rearm_allowed` 只把判据从全局改锚，**状态机结构不变**——这正是"第一步不排斥后续"。
- **扩展路径**：no-material / too_short / capacity / durable-frontier 逐步把各自的负证据、锚定、rearm、fallback 填进同一契约；既有的 T5/T6/T11/T12/T13/T15 转换作为骨架各态的实现载体保留，不重写。

### 4. no-material fast-forward 统一语义（用户 Deliverable 4，本轮 coder 实现）

**no-material 的 negative evidence**：锚非 durable（`frontier_anchor_ready` False，即非 is_l3_durable 非 root），**且无任何在途因果生产者**使该锚未来 durable——即：无该锚在途 L3 写 pending（`ongoing_backup`/`ongoing_prefetch` 无该链）、无在途 restore 读回、该锚无 `storage_acked && !storage_persisted` deferred 后代（deferred 集为空 → 无将来 promotion 源）。纯设备链（dev>0, host=0, store=0，如 9d8b5428）即此态。

**anchor binding**：该 FRONTIER waiter 的锚节点/链。

**为何立即 forward 而不等**：没有在途生产者，锚的 durable 状态**永不实质变化**（P3 reconcile 也只补写 deferred 集，纯设备链不进集），等待必 idle 满 T13（60s）→ 期望等待时间为零收益。**re-arm 的唯一来源是"新在途生产者出现"**——但无物材的锚不会自发出现生产者（其写发生在 eviction 时，非该候选的 L3 restore 场景）→ 等待无解除条件 → 立即 ADMIT_RECOMPUTE 是唯一一致解。

**落点**：`GATE_SKIP_FRONTIER` 入口（scheduler.py:3064-3068）在 `prompt_can_qualify_for_prefetch` 之外**加一道 no-material 判定**（与 too_short 几何门并列但独立）：能 qualify 只表示"后缀长度可达阈值"，不等于"存在可等待的物材"（P3-closeout Open Decision）。判定 = 锚非 durable + 无在途生产者 + deferred 集无该锚后代 → **直接 ADMIT_RECOMPUTE，不 register_frontier_waiter**。保持 P3 收口：有在途生产者 / 有 deferred 后代时仍走 frontier wait（A+B 语义不变）。

**与 too_short never-case 的衔接**：二者都是"无在途生产者 → 立即 forward"的同一类；too_short 的负证据是几何（suffix < threshold），no-material 的负证据是物材（无 durable + 无在途生产者）。两门互补不重叠：too_short 几何门已收口，no-material 物材门是它的"能 qualify 但无可等物材"补充。

### 5. 与 P1 / too_short / P3 已收口行为的衔接（用户 Deliverable 5）

| 已收口项 | 统一模型是否覆盖 | 是否破坏既有行为 |
|---|---|---|
| **P1 sticky miss**（MISS_RECOMPUTE 态 + re-arm epoch 门） | 态 1（definitive miss）。rearm 判据从全局 epoch 改锚 version | **不破坏**——只收窄放行（无关链不再解除 MISS），MISS_RECOMPUTE 状态机、ADMIT_RECOMPUTE forward、generation 变化路径原样保留 |
| **too_short never-case 门**（too_short-fix 已收口） | 态 2（几何终局）。与 P1 统一为"无在途生产者→立即 forward" | **不破坏**——too_short 判定/never-case/device-match-decay bet 原样保留，仅被统一模型归类 |
| **P3 durable-frontier HOL 修复**（A+B confirmed） | 态 5（durable-frontier pending）有在途生产者，等待同锚 ACK。A+B 补链 + clear 守卫语义保留 | **不破坏**——A+B 只动 deferred 集补写/clear 守卫，不碰 re-arm 判据；per-anchor bump 在 `advance_storage_persisted`/`mark_storage_restored` 处与之正交共存 |
| **no-material 单例**（9d8b5428，原 idle 60s） | 态 3，本轮 fast-forward 消除空等 | **改进**——由 60s T13 idle 变为立即 ADMIT_RECOMPUTE；P3 收口判据（restore_recompute(timeout)=0 严格 gate）若坚持则需先采纳本前向判定（P3-closeout Open Decision 已预告） |
| **capacity wait / Fix A（资源 epoch）** | 态 4，资源在途等待 | **不破坏**——容量判据（promotion_budget_fits / available+evictable）原样；与锚 version 正交（容量是资源 epoch，miss 是 cache 证据 epoch） |
| **Fix B（T13 timeout 计数 cap）** | 已被 P1 epoch 门结构性替代（restorearm-e3 §7）；本轮剥离后不再依赖 | 已在 HEAD=3c71553a20 剥离（"revert Fix B" commit） |

**关键不破坏保障**：per-anchor 修正只改"re-arm 判据的锚定粒度"，不动状态机转换、不动容量判据、不动 A+B 补链、不动 too_short 几何门。全局 epoch 从门判定移除但保留为诊断计数（无行为副作用，仅日志/统计消费）。

## Alternatives

- **A. 保留全局 epoch + 增加"前缀匹配"过滤**（当前判据上加"仅当本请求前缀的 deferred 集非空/锚 durable 变才放行"）：粒度仍粗（前缀扫描 O(subtree) 做门判据、每请求开销），且 deferred 集非空不等价"该锚的 L3 覆盖变"；是代理的修补，不是锚定。**不推荐**。
- **B. per-request 时间戳/退避**（re-arm 前冷却）：TTL heuristic，被用户明确禁止（ledger:2112），且频率代理无结构意义（restorearm-e3 §5）。**不推荐**。
- **C. 锚 version（采纳）**：把 bump 的因果对象从"全局"收窄到"该锚所在持久链"。开销=每锚一个 int + bump 点按链定位锚，无 O(subtree) 门判据、无计时器。与既有 `_bump_l3_publish` 同源（在其旁做锚级递增），侵入最小。**推荐**。
- **D. 完全重写统一状态机**：把五种拒绝态并入单一 eligibility 对象。语义上最干净，但违背用户"本轮不做大重构、只出骨架契约"的裁决（ledger:2113）。**不做**，仅以接口契约 + per-anchor 首例落地先行。
- **E. no-material 用"等待更短 T13"替代 fast-forward**：仍占用 WAIT 时钟（哪怕缩短），且对"永无物材"的候选任何等待都是零期望；不如立即 forward。**不推荐**（与 P3-closeout Open Decision 一致，前向判定更干净）。

## Migration / Impact（本轮实现 = per-anchor + no-material）

**改动面**（本轮 coder 范围，纯 predicate/字段粒度变更，无状态机大改）：
1. `unified_tree_core.py`：`UnifiedTreeNode` 加 `storage_version: int`；`_bump_l3_publish` 保留（全局诊断），新增/收窄锚级 bump（mark_storage_restored / _promote_persisted_subtree / clear_storage_durable 实际清除处）；暴露 `anchor_version(node_id)`。
2. `scheduler.py`：miss 记录（:3216-3226）改记 `miss_anchor_id + miss_anchor_version`（而非全局 epoch）；T6 re-arm（:4546-4556）改读锚 version；NO_L3 cursor（:3240-3244）同步改锚 version（见 Open Decision 4）。GATE_SKIP_FRONTIER（:3064-3068）加 no-material 前向判定。
3. `hicache_restore.py`：`miss_rearm_allowed` 签名改 `(miss_anchor_version, current_anchor_version, generation)`。
4. 全局 `l3_publish_epoch` 从所有门判定移除，仅诊断统计。

**风险**：锚 version 的"锚"解析（事件节点→其持久链最深 durable 锚）需准确定义，避免错误锚定；anchor 删除/重锚定 root 时负证据失效处理（§2）。均属实现期校验（open decision 2/3）。

**不影响已确认基线**：P3 A+B（补链/clear 守卫）、too_short never-case、device-match-decay bet、Fix A 容量 epoch、P2-IO extent 后端、RH（除 NO_L3 cursor 若同步）。全局 epoch 计数移除不改变任何门行为（仅日志/统计消费）。

## Open Decisions（返回 orchestrator / 用户）

1. **clear_storage_durable 是否 bump 锚 version**：本报告建议"实际清除时 bump"（清除=该锚实质状态变化，应解除依赖它的负证据）。但需确认是否会引入"clear→re-arm→re-probe miss→clear"新环（本报告判断不会：clear 只在有实质理由时发生，且 re-probe 若仍 miss 会再次记录锚 version，负证据自我续期）。**建议采纳 bump，实现期验证无新环**。
2. **锚删除时负证据处理**：节点物理删除/evict 后，miss 记录/NO_L3 park/frontier waiter 如何处理。本报告建议 self-heal（删除=锚身份变→re-match from root→等价新候选，允许 re-arm）。需确认与既有 `frontier_anchor_ready` node_exists→True、`backup_wait_ready` self-heal 语义一致。**建议采纳 self-heal**。
3. **no-material fast-forward 作用域**：判定 = 锚非 durable + 无在途生产者 + deferred 集无该锚后代。是否也覆盖 buffer mode（buffer mode 读 hash 不读锚，GATE_SKIP 已是 final recompute，无需 fast-forward）。**建议仅 cache mode**；实现期确认。
4. **ready-horizon NO_L3 cursor 是否本轮同步改锚 version**：NO_L3 负缓存与 miss_rearm_allowed 同病（全局 epoch cursor）。用户裁决聚焦 P1 miss 门；NO_L3 是 RH 专用且 RH 默认 OFF。**建议**：本轮同步改锚（成本低、同一代理缺陷），但若保守可留 followup——需用户裁定。

## 8. 本轮 coder 实现范围（followups / 交接）

1. **per-anchor version**（§2 + §Migration 1-4）：tree_core 锚 version 字段与 bump / scheduler miss 记录与 T6 re-arm 改锚 / hicache_restore 签名。交付后跑 P1 deterministic workload 6 点验证（ledger:2114）。
2. **no-material fast-forward**（§4 + Open Decision 3）：GATE_SKIP_FRONTIER 入口加 no-material 前向判定 → 直接 ADMIT_RECOMPUTE。保持 P3 收口（有在途生产者/deferred 后代仍走 frontier wait）。
3. 统一状态机骨架**本轮不实现**，仅本报告契约（§3）供后续扩展；per-anchor 作为骨架态 1 的首例落地。
