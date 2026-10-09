# P3 — L3 ACK-promotion / frontier HOL 修复：最小正确语义（architect e2）

status: done
artifacts:
  - 本报告：phase2-l3ack-architect-e2.md
  - 证据来源：sglang-3090-24g-opt 分支 3090-24g-opt（只读，未改代码）
evidence:
  - unified_tree_core.py:2132 clear_storage_durable、:2141-2142 清双旗、:2153 advance_storage_persisted、:2163-2171 父链 contiguity 检查、:2173-2190 _promote_persisted_subtree、:2186 child 仅递归 storage_acked
  - unified_radix_cache.py:3321 clear_storage_durable 唯一调用点（revoke miss）、:3586 advance_storage_persisted 唯一调用点（ack drain）、:3594-3595 对 promoted 唤醒、:2842 mark_storage_restored（restore finalize）
  - scheduler.py:3680-3688 frontier_anchor_ready 唤醒谓词、:3158 T13 60s timeout、:3171 restore_recompute
summary:
  - conclusion: A+B 组合，以 A 为主，B 为收窄式守卫（见下）
  - current_architecture / problem_forces / proposed_architecture / alternatives / migration_impact / open_decisions 见正文

---

## 0. 裁决摘要

**A+B 组合，主 A、辅 B，全部落在 `UnifiedTreeCore`（+ 一个 radix-cache 层 reconcile 触发器），最小修复面。**

- **A（主，必需）**：durable 状态变化（promotion 的逆事件——`clear_storage_durable` / host-eviction 删除 / tombstone 删除）之后，任何 `storage_acked==True && storage_persisted==False` 的节点必须在**同一 pass 内主动重新传播**，不得等待新 IO 碰巧触发。落地：给 `clear_storage_durable` 增加"被清节点若仍有 ACKed 非 persisted 后代 → 立即重新发起它们（gap 补写 + 重 promotion）"的主动递补路径。
- **B（辅，守卫）**：`clear_storage_durable` 不得清掉**仍被 ACKed descendants 依赖**的 parent durable 状态。落地：改为只清"已无任何 ACKed 依赖子树"的节点的 durable 信念；若存在依赖子树，则**延迟** clear（置 invalid 标记）而不是立刻抹除，依赖子树递补完成后一并重写/重 promotion。
- 理由与"硬约束"逐条对应，见 §3。

**关键正确性前提（当前代码已满足，新逻辑必须保持）**：持久性来源被统一成 `storage_persisted OR storage_restored`（`is_l3_durable`，unified_tree_core.py:2144-2151 / radix :2263-2268）。修复引入的"重传播"不得产生**无底层存储事实**的 promotion——一切 promotion 必须由真实的 ack（`advance_storage_persisted`）或真实的 restore read-back（`mark_storage_restored`）驱动，reconcile 只做"把已被 ack 的事实重新补齐到链上"，不做"凭空宣称 durable"。

---

## 1. Current Architecture（真实机制，逐点带行号证据）

### 1.1 durable 状态模型（UnifiedTreeNode）
- `storage_written`：KV 已提交 L3（dedupe 守卫，非连续性）。
- `storage_acked`：写已 ack（全量或全无；partial ack 只清 `storage_written`、不置 `storage_acked`）。
- `storage_persisted`：写已 ack **且父链连续**——才是 anchor。
- `storage_restored`：刚被成功 restore 读回，L3 中确认存在。
- 统一谓词 `is_l3_durable = storage_persisted OR storage_restored`（unified_tree_core.py:2144-2151）。root 恒为 anchor，本身不写。

### 1.2 advance_storage_persisted —— promotion 的唯一入口（unified_tree_core.py:2153-2190）
- ack drain（unified_radix_cache.py:3586）在"该写全量完成"时调用。
- 置 `storage_written=True; storage_acked=True`；若该节点已 persisted 则直接返回（幂等，2163）。
- **contiguity 检查（2165-2170）**：仅当 `parent is None` 或 `parent is root` 或 `parent.storage_persisted` 才 `_promote_persisted_subtree(node)`；**否则返回 []，节点停留在 `acked && !persisted`（deferred）**——这就是冻结事实 37 node 的成因。
- `_promote_persisted_subtree`（2173-2190）：置自身 persisted，**只递归 `storage_acked && !storage_persisted` 的子节点**（2186），对 persisted 子节点不重走（"已 promoted 时所有 acked 后代已一起 promoted，之后 acked 的由各自 ack drain 负责"——2180-2182 注释）。
- **结论**：promotion 是**单向、ack 驱动、依赖父链连续性**。一旦父链被破坏，所有未 promoted 的 ACKed 后代**永久搁置**——没有任何机制在父链恢复后重新遍历它们。这是 bug 的核心。

### 1.3 clear_storage_durable —— 破坏父链的两个源头之一（unified_tree_core.py:2132-2142）
- 唯一调用点：unified_radix_cache.py:3321，`restore` 查询报 0 pages（P2-1 e15 Y）时的 revoke-miss 路径。
- 动作：`storage_persisted=False; storage_restored=False`（2141-2142）。
- **关键缺陷（B 靶点）**：无条件清双旗，**不管被清节点是否仍是 ACKed descendants 的父锚点**。clear 后，其下所有 `storage_acked && !storage_persisted` 的后代失去"父链连续"锚点，`_promote_persisted_subtree` 的 contiguity 检查（2166-2169）永久不成立 → 后代永久 deferred → frontier_anchor_ready 永不成立。

### 1.4 破坏父链的另一源头：节点删除（host-eviction / tombstone 级联删除）
- `_evict_host_leaf`（1655-1680）：对 host leaf 清全层并从父 `children.pop`（`_remove_leaf_from_parent` 1807-1816）、`_unregister_node` 移出 `_node_arena`（592-594）。若父变 childless 且无 device/host 值，`_iteratively_delete_tombstone_ancestors`（1866-1920）向上级联删除 childless 祖先，**一直删到 root 或某个有值的节点**。
- `detach_miss_dropped`（1414-1451）同理：forced-miss tombstone 连同整棵子树删除。
- **结论**：父链的"物理节点"可被 eviction 删除（不是只清 durable 旗）。对 ACKed 后代的持久性语义，删除父节点与 clear durable 旗等价——都断链。**B 守卫无法单独覆盖"父被物理删除"情形**（物理删除不可能"不清"，父已不存在），这正是 A（主动递补）不可省略的第二个理由：父链断裂后，唯一能恢复下游的是**把父链重新补到存储**（write_back_storage 的 gap 补写天然包含"从最近 persisted 祖先（root 兜底）填到目标"）。

### 1.5 frontier_anchor_ready / T13 timeout —— 症状闭环
- `frontier_anchor_ready`（unified_radix_cache.py:2379-2392）= `node_exists` 且 `is_l3_durable`（或 root）。deferred 节点 `storage_persisted=False` 且 `storage_restored=False` → **恒 False**。
- scheduler T12 唤醒（scheduler.py:3115-3150）依赖 `pop_frontier_ready`（由 ack drain 的 `_wake_frontier_waiters` 填充，radix :3594-3595 / 3044-3066）。
- FRONTIER waiter 的 per-pass 唤醒谓词 `_restore_wait_capacity_fits`（scheduler.py:3680-3688）调 `frontier_anchor_ready`，恒 False → 不醒。
- T13（scheduler.py:3158-3171）：`now - state_ts > hicache_restore_wait_timeout_s(60)` → `_log_restore_recompute("timeout")`。
- **闭环**：deferred 永不 promotion → anchor 永不 durable → FRONTIER waiter 只能等 60s timeout → restore_recompute。与冻结事实 p95≈61s 完全吻合。

---

## 2. Problem / Forces

- **结构性缺陷**：durable 状态是"ack 时一次性从父推子"，无"父链变化时反向补救"的逆路径。父链被破坏（clear durable 旗 / 物理删除）后，ACKed 后代的 promotion 依赖"未来某个新 IO 碰巧再次 `advance_storage_persisted`"，而无此保证 → 永久 deferred → frontier HOL（确定性 60s cliff）。
- **硬约束**：
  1. 禁改 60s timeout（绕过症状）。
  2. 禁简单忽略 parent persisted（破坏 durability——L3 无完整 prefix 时 anchor 不可信）。
  3. ACKed 后代必须被递归/迭代重新 promotion，不依赖新 IO。
  4. clear_storage_durable 不得清仍被依赖的 parent 状态，须有 reconciliation，不留永久不可达 frontier。
- **约束（最小修复面、可组合、禁无证据扩大）**：只动 durable 状态语义，不碰 timeout、不碰容量、不碰 restore 资格、不碰 RH。

---

## 3. Proposed Architecture（A+B 最小正确语义）

### 3.1 A（主）：deferred-ACK reconciliation —— 父链恢复后主动重传播

**新索引（UnifiedTreeCore 内）**：维护 `deferred_acked: set[NodeId]`（或对每个节点一个 `acked && !persisted` 判定即可，无需持久索引——见 3.3 收敛性）。

**触发点 A1（clear durable 后主动递补）**：`clear_storage_durable(node_id)` 内，在清 node 双旗后：
1. 若 node 已无 `storage_acked` 依赖子树 → 直接清（等效现状，B 守卫放行）。
2. 若存在 ACKed 非 persisted 后代 → **不抹除 node 的 persisted 信念**（见 B），改对 node 发起一次 `write_backup_storage(node_id)` 的**重写 + 重 promotion**：`collect_storage_gap(node_id)` 会从最近 persisted 祖先（含 root 兜底）重新补写整个 gap，再经 ack drain 的 `advance_storage_persisted` 递归下推所有 ACKed 后代（2186 已具备该递归）。

**触发点 A2（父链物理删除后递补）**：父被 eviction/tombstone 删除（`_remove_leaf_from_parent` / `detach_miss_dropped`）后，若其下仍有 `storage_acked` 后代，父节点已不存在，无法在其上补写——但 `write_backup_storage(descendant)` 的 `collect_storage_gap`（2089-2098）**天然会从最近 persisted 祖先/root 重新填满整个缺失 gap**（`not node.storage_persisted` 即入 gap，2093；`storage_written` 的节点走过后不重收集 2095）。因此对任一 ACKed deferred 后代调用 `write_backup_storage` 即可把整条断裂链重新补齐到持久 + 重 promotion。

**触发点 A3（统一 reconcile 挂载点，避免 A2 的"哪个后代"发散）**：在 radix-cache 层 `_drain_*`/per-pass 事件循环（`_finish_write_through_ack` 之后、`_flush_pending_storage_writes` 处，radix :2097-2118）增加一次"扫描 deferred_acked"：对每个 `storage_acked && !storage_persisted` 的存活节点，若其链可递补（最近的 persisted 祖先存在或 root），主动 `write_backup_storage` 触发补写。**幂等**：`collect_storage_gap` 对已 written 节点跳过（2095）、`write_backup_storage` 对 `is_storage_written` 跳过（2159）、对不存在的节点 `_skip_stale_storage_persist`（2105-2113）——重复触发不产生重复写。

**事件**：递补完成后统一经 ack drain 的 `advance_storage_persisted` → `_wake_frontier_waiters`（3594-3595）唤醒 FRONTIER waiter，闭环回到既有 wake 路径，**不改任何 wake/状态机逻辑**。

### 3.2 B（辅）：durable-state invalidation guard —— 不清仍被依赖的父状态

`clear_storage_durable`（2132-2142）增加守卫：仅当被清节点**无 `storage_acked` 依赖子树**时才执行物理清双旗；否则：
- 不抹除 node 的 `storage_persisted/storage_restored`（避免 1.3 的永久断链），
- 改走 A1（对该 node 重写/重 promotion）或置一 `invalidated` 标记由 A3 递补。
- 语义校正：e15 Y 的本意是"restore 查询无 pages → 该 anchor 的 durable 信念过期"。**正确做法是"让该 anchor 的持久性被重新验证/重新补齐"而非"无条件抹除其 durable 信念"**——尤其当它仍被 ACKed 后代依赖时。

### 3.3 收敛性 / 幂等 / 不产生错误 durable promotion

- **收敛**：A 的每次触发都朝"ACKed 节点 persisted"单调推进；无新 IO 时 A3 单次扫描即可把全部 deferred 一次补齐（`collect_storage_gap` 从 root 兜底，一条链一次补满），**不会反复触发**。deferred 集合只会因节点被删除而缩小，不会新增非 acked 的 persisted 成员。
- **幂等**：三处 dedupe 天然幂等（§3.1 已列：written 跳过 / gap 已覆盖跳过 / 死节点跳过）；`advance_storage_persisted` 对已 persisted 提前返回（2163）；重 promotion 只推进 `acked && !persisted`（2186）。
- **不产生错误 durable promotion**：reconcile **从不自己置 `storage_persisted`**——它只调用 `write_backup_storage`（真实写 + 真实 ack），promotion 仍只由 `advance_storage_persisted`（真实 ack）或 `mark_storage_restored`（真实读回）驱动。B 守卫是"延迟 clear"，不是"伪造持久"；被 B 保留的 node 的 persisted 信念最终由 A1/A3 用真实写重新验证（若写失败则走既有 partial-ack / `_skip_stale_storage_persist` 路径，不产生假的 durable）。

### 3.4 改哪些函数 / 加什么

| 层 | 函数 | 改动 |
|---|---|---|
| tree_core | `clear_storage_durable` | 加 B 守卫（无 acked 依赖才清）+ A1 触发（有依赖则递补而非抹除） |
| tree_core | 新增 `deferred_acked_nodes()` / `has_acked_descendant(node)` 判定 | 供 A1/B 判定依赖子树 |
| radix_cache | 新增 reconcile 入口（挂到 `_flush_pending_storage_writes` 附近或 per-pass drain） | A3：扫描 deferred_acked → `write_backup_storage` |
| radix_cache | `_flush_pending_storage_writes` / ack drain | 递补完成后既有的 `_wake_frontier_waiters` 自动唤醒（无需改） |
| interface | `advance_storage_persided` 签名已返回 list[NodeId]；`clear_storage_durable`/`mark_storage_restored` 不在 interface（仅 tree_core 内），**无需改 interface** |

**最小性**：不改 scheduler、不改 timeout、不改容量、不改 wake 状态机、不改 restore 资格（P1 另案）。唯一新状态是 tree_core 内的 deferred 判定（可用现成 `storage_acked && !storage_persisted` 派生，无需持久新字段；若需显式 B 标记，加一个 `storage_invalidated` 布尔即可）。

---

## 4. clear_storage_durable 审查（约束④专项）

- **现状问题（确认）**：唯一调用点 radix :3321 是 revoke-miss 时无条件清 anchor 双旗；被清节点可能仍是 ACKed descendants 的父锚点 → 永久断链。**判定：允许清仍被依赖的 parent durable 状态，且无 reconciliation**——违反约束④，需 B 守卫 + A 递补。
- **B 的边界（诚实标注）**：B 只覆盖"父仍存活"的情形（clear 双旗）。父被**物理删除**（eviction/tombstone）时 B 无法兜底（节点已不在 arena），此时必须靠 A2/A3 的 gap 补写（从 root 或最近 persisted 祖先重新补齐）。因此 **B 单独不充分，A 是充分必要条件**；B 的价值是缩小 A 的触发面（尽量保留仍可用的 durable 父，少一次重写）。
- **不要为 B 扩大面的警告**：B 守卫判定"是否仍有 ACKed 依赖子树"本身要遍历子树；若热路径每次 clear 都全量遍历会引入开销。建议：clear 调用点极少（仅 revoke-miss），且可先查"直接 children 是否 acked"剪枝，递归仅在有 acked 子时才继续——无 acked 子即直接清（绝大多数情形），成本可忽略。

---

## 5. Alternatives（裁决依据）

- **A-only**：去掉 B，只做 reconcile。可行（A3 能从 root 补满一切断裂链），但每次父 durable 被 clear 都强制重写整条已存在的链，即使父本身仍有效——**多余 IO**。B 把"父仍可用的情形"排除在重写之外。故 A+B 优于 A-only（更小写放大）。
- **B-only**：只加守卫不清。**不充分**：物理删除父节点时无守卫可加（父已消失），仍永久断链；且"不清"会让已过期的 durable 信念长期误报为可恢复 anchor（e15 Y 的本意就是发现过期要处理）。B-only 违背约束④的"须有 reconciliation"。
- **懒修复（等新 IO 触发）**：违背约束③（不依赖新 IO 碰巧触发），且 60s cliff 确定性复现，否决。
- **清理 deferred 集合 + 定时重扫**：无事件驱动的轮询式 reconcile 引入不确定延迟且与现有"每 pass 事件驱动"哲学冲突；A 的事件驱动（clear/删除时立即触发 + ack drain 后统一递补）更贴合现有 `_l3_publish_epoch` 的因果事件语义。否决。
- **"简单忽略 parent persisted"**：约束②明确禁止（会伪造 L3 完整性），否决。

**结论**：A+B 是最小充分组合。A 是语义必需，B 收窄 A 的触发面并满足约束④。

---

## 6. Migration / Impact

- **修复面**：tree_core（clear_storage_durable + 判定辅助）+ radix_cache（一个 reconcile 入口）。不触碰 interface 抽象（`advance_storage_persisted` 已在 interface，其返回 list 语义不变）。
- **风险点**：
  1. 重写整条断裂链的 IO 放大：仅在父链真的被 clear/删除且有 acked 依赖时发生（罕见路径），且与既有 `write_backup_storage` 的 gap 去重一致。
  2. B 守卫的子树遍历：调用点极少 + 剪枝，可忽略。
  3. 递归重 promotion 的深链：沿用 `_promote_persisted_subtree` 既有递归（2186），不新增深度风险。
- **回归**：所有 promotion 仍经真实 ack/restore；wake 路径零改动；timeout 零改动。

---

## 7. 验证映射（对照 ledger 冻结清单）

**unit / state-machine 5 项（tree_core 层，直测）：**
1. child ACK 先到、parent 后 durable → 最终 promotion（现状 `advance_storage_persisted` + `_promote_persisted_subtree` 已覆盖，测 A 不改坏）。
2. parent clear（B 守卫下无 acked 依赖）再恢复 → descendants 最终 promotion：clear 后 parent 重写 → ack drain 重下推。
3. A→B→C→D 乱序 ACK 收敛：多节点 defer，A1/A3 单次递补后全部 persisted。
4. 重复 ACK / 重复 reconcile 幂等：`advance_storage_persisted` 提前返回 + gap/written 跳过 + 死节点跳过。
5. 不产生错误 durable promotion：reconcile 不置 persisted，仅经真实写 ack。

**deterministic warm-tree**：修复前 defer→frontier_wait≈60s→timeout（现态复现基线）；修复后 defer 可暂时出现，但 parent 愈合（reconcile）后 descendant 继续 promotion、frontier 推进、frontier_wait 不达 60s、restore_recompute(timeout)=0。

**真实 Claude c8 A/B**：p50≈1-2s、p95 无 60s cliff、L3 保持 ON。

**correctness 4 项**：0 OOM / 0 HTTP err / 0 zero-progress / 0 durability violation。通过后 2h warm-tree soak。

---

## 8. Open Decisions / 待确认

1. **B 的"延迟 clear"是否引入显式 `storage_invalidated` 标记，还是复用"有 acked 依赖即不 clear、直接递补"的隐式判定**——倾向隐式（最小字段），但需 coder 确认不会让过期 durable 信念在递补前被误当 anchor 使用（可复用 `_l3_publish_epoch` 语义，递补完成即前移）。
2. **A3 reconcile 的确切挂载点**：挂在 `_flush_pending_storage_writes`（ack 后统一）最贴合现状，但需确认其调用频率/是否每次 event loop 必经——若仅在 drain 内则保证"每 pass 一次"，符合约束③。
3. **B 守卫在 revoke-miss 路径的开销上限**：建议先查 direct children acked 剪枝；若 subtree 判定仍需全量递归，是否接受（调用点极少）。请 coder 实现后由 tester 在 warm-tree 上实测 frontier_wait 分布佐证。
4. **物理删除父链时 A2 的"哪个后代发起"**：A3 统一扫描避免发散；但若 deferred 后代数量大，单 pass 扫描+批量补写是否需限流（复用现有 prefetch/写并发控制），待 tester 观察写放大后再定。

followups:
  - coder 实现 A+B（tree_core + radix_cache 两个文件 + 可选 interface 不需改），配 5 项 unit。
  - tester 先复现 warm-tree 60s cliff 基线，再验证修复后 frontier_wait<60s。
  - P1（restore re-arm churn）与 P0（build_backup_spec assert）为独立缺陷，不混入本修复。

open_issues:
  - §8 四项待实现/观测确认；均为非阻塞实现细节，裁决（A+B、主 A 辅 B）已定。
