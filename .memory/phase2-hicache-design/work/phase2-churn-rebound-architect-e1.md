# phase2-churn-rebound-architect-e1 — P3 miss-churn 反弹 + epoch 非平稳性 架构复核（read-only）

```text
status: done
artifacts:
  - 本报告（read-only 架构复核，未改任何代码）
  - 代码语义：unified_tree_core.py（_bump_l3_publish:2119 / l3_publish_epoch:2127 /
    clear_storage_durable:2132 / _has_deferred_acked_descendant:2159 /
    deferred_acked_nodes:2185 / advance_storage_persisted:2209 /
    _promote_persisted_subtree:2229）
  - unified_radix_cache.py（_reconcile_deferred_acked:2166-2201，每 pass ack drain 末尾调用；
    write_backup_storage:2208 / collect_storage_gap 链补写）
  - scheduler.py（:3223 miss epoch 记录 / :4546-4556 T6 miss_rearm 门 /
    :3240 ready-horizon NO_L3 负缓存 epoch_cursor）
  - hicache_restore.py:227-250 miss_rearm_allowed 语义
evidence:
  - git 30a5a3698a diff（tree_core +58/-1、radix +78，纯增量）逐行核对
  - tester e1: work/phase2-fixb-strip-tester-e1.md（对照表 §3、归因 §4.2、limitations §6）
  - architect 先验: phase2-l3ack-architect-e2.md §8（epoch anchor 粒度 open issue）、
    phase2-tooshort-architect-e1.md（never-case 门 / 统一状态机衔接）
summary:
  Conclusion
  Current Architecture
  Problem / Forces
  Proposed Architecture
  Alternatives
  Migration / Impact
  Open Decisions
followups:
  - 判定 1 的验证项（§1.3）由 tester 承接；判定 2b 的逐链因果闭合见 §2.3
  - 建议在 fast-forward + soak 中夹带 §6 B-2 的逐链 epoch 观测（低成本、可证伪）
open_issues:
  - 见 §7：anomalous-epoch 语义由 tester 提供再收敛；不做 epoch=0 特判
```

## Conclusion（一页裁决）

1. **P3 是否引入 miss churn 反弹：证据不足以判"真引入"，同时不足以判"纯噪声"——是"结构上合理、需逐链验证的强相关"，不构成 P3 收口回退。** 四个同步观测（rebound 时间线 / reversed 序 / global-global bump 耦合 / 每 bump 1 次 ack 级机械）把 P1→P3 的 1159→2615 翻倍唯一地落在"P3 每 pass reconcile 的 ack-驱动 _bump_l3_publish（+78 代码里的新增 bump 路径）被 8-agent 并发写的无关链 ack 周期触发"，是全局 epoch 放行扩大；它不是 L3 内容实质变化，是 epoch 计数器层面 churn 放大。但测试未对"bb4deb 的 22 次 re-arm 时刻的 epoch 值"做直接观测，逐链因果未闭合。
2. **P1 epoch 门在当前 epoch 非平稳下确实退化为"永不拦截"。** `miss_rearm_allowed` 的 `current_epoch > miss_epoch` 判据（hicache_restore.py:246）是**全局**单调计数；在 8-agent 负载下 ~2.1/s 前移（0→3902）且每次 bump 都来自"任一无关联前缀链的 durability 事件"（unified_tree_core.py:2245 每次 promotion 都 bump），故任一 MISS 请求在 ~0.5s 内必然 current>miss → 恒放行。epoch 门所依赖的"epoch 前进 = 该前缀 L3 覆盖真变"的前提在并发负载下**不成立**。**缺 anchor 粒度（前缀级）是结构缺陷**（正是 l3ack-e2 §8 open issue 1）。
3. **裁决：**
   a. **P3 收口维持 confirmed，无需重审**。P3 的 HOL 修复与 miss-churn 放大是**正交**的：P3 引入的 epoch 放大经**全局**计数路径（_bump_l3_publish）作用，不触碰 HOL 判定路径（frontier_anchor_ready / is_l3_durable / T13 timeout），后者的正确性证据（P3 fix tester e1 + harness test_p3_warmtree_hol.py）不被动摇。P3 修 HOL（真缺陷），顺带放大 miss churn（"durable-frontier HOL 已消除"仍 confirmed）。
   b. **P1 epoch 门在 epoch 非平稳下失效**。修正方向见 §5：锚定 **anchor/前缀粒度**——epoch 改为 per-prefix-anchor 版本号（写 ack / restore 读回时对该 anchor bump），miss 判据只对比"本请求前缀所在 anchor 的版本"，与"无关链写 ACK 的全局 bump"脱钩；与 host/device 实质物材判定（has_restore_potential）结合；与 too_short never-case 门统一成"re-arm 前判据"状态机（用户预警的第三种同构 churn）。
   c. **可推进 fast-forward + soak**，但**必须带条件**：加装"断言/观测 re-arm 时刻的真实逐链 epoch"（§6 或 tester 观测），证明 dev>0 请求的 re-arm 与自身 anchor 的实质变化对齐；否则"soak 期间 miss churn 回到 P1 水平"不可预期，只能当成"已知缺口的特征基线"。

## 1. P3 反弹归因（判定 1）

### 1.1 直接代码证据（强证据，可复核）

**P3 是纯增量、只碰 durability/epoch 机械**（30a5a3698a: tree_core +58/-1、radix +78；无 scheduler / hicache_restore / restore 资格 / capacity 改动）：

- A3 reconcile（unified_radix_cache.py `_reconcile_deferred_acked_inner`）挂在 `_flush_pending_storage_writes` **每 pass 末尾**，对 `deferred_acked_nodes()`（= `storage_acked && !storage_persisted`，unified_tree_core.py:2185）逐节点 `write_backup_storage` 补链 + `advance_storage_persisted` 重 promotion + `_wake_frontier_waiters`。
- `advance_storage_persisted`（unified_tree_core.py:2209）：对**已是 persisted** 的节点**提前返回**（:2219-2220）——reconcile 对已 persisted 节点不 bump；对确实 promotion 的节点，`_promote_persisted_subtree`（:2229）在 promoted 非空时 `_bump_l3_publish()`（:2245）**每次 promotion bump 一次**。
- `_bump_l3_publish`（:2119）：每次 bump 是"一次真实 L3 durability 事件（写 ack 或 restore 读回）"，但**计数是全局单调**，不与任何前缀/链/节点绑定。

**结构性影响（强推理）**：P3 引入前，bump 仅来自 ack drain / restore 的**单次** promotion（并发下同量级但每条路径独立）；P3 新增了"每 pass 全量重扫 deferred 集 + 每节点 promotion"——**deferred 节点在被并发的无关链写 ack 逐轮补齐时，每轮都 bump**。8-agent 并发下总 bump 率上升。这与"l3_publish_epoch ~2.1/s 全局前移、0→3902"的观测吻合，也与"T13 从不触发（Fix B 不生效）"吻合。

### 1.2 因果推理（强推理，未逐链闭合）

tester 证据（phase2-fixb-strip-tester-e1.md §3/§4）四个同步观测，把反弹唯一定位到 P3 引入时刻：

1. **rebound 时间线**：P1(74246bb90f w/FixB) revoked:miss=1159 → too_short(7155cd8973 w/FixB)=1205（仍 P1 水平）→ P3(30a5a3698a w/FixB)=**2615**（翻倍）→ strip(3c71553a20 无FixB)=2529。**翻倍发生在 P3 引入时，早于剥离**。
2. **reversed 序排除顺序噪声**：miss churn 单调升序与引入顺序（P1→too_short→P3）无关，只与"是否含 P3"相关——跨 2 次独立 run 稳定，非单 run 抖动。
3. **global-global bump 耦合**：reconcile 每次 ack 驱动 promotion 都 bump **全局** epoch（:2245）；dev>0 前缀链的写 ack 周期性地把**其它请求**（含 dev=0 的纯设备链）的 `miss_epoch` 判据推到放行。这是"全局 epoch 放行扩大"，不是"本前缀 L3 内容变化"。
4. **每 bump 1 次 ack 级机械**：观测 epoch 从 0→3902，远高于 P0/P1 时期（P1 验证时 ~0.8/s）——计数增长量与 8-agent 并发 L3 写吞吐正相关，是计数器层面 churn 放大。

**注意 P1 改善口径**：tester 复现 P1 run 最差 offender 9 miss（P1 报告称 68→1）。P1 是"降低"非"消除"；即便无 P3，P1 改善也存在环境依赖。反弹是与 P3 引入耦合的**回归**，不是 P1 失效本身。

### 1.3 需验证点（区分强证据 vs 需进一步验证）

- **[强证据] P3 收口正确性不受影响**：P3 修复 HOL 的路径（frontier_anchor_ready / is_l3_durable / 60s T13）不涉及 epoch bump 计数，P3 收口证据（test_p3_warmtree_hol.py + P3 fix tester e1）不被动摇。
- **[需验证] 逐链因果闭合**：测试未直接观测 bb4deb 在 22 次 re-arm 时刻的 `l3_publish_epoch` 是否真的在自身链无实质变化时前进。建议（tester）：对最差 offender 的 re-arm 时刻做"per-pass l3_publish_epoch + 该前缀 deferred 集非空"的配对日志，闭合或推翻"无关链 bump 放行"。
- **[需验证] 环境噪声排除**：L3 碎片 / /data 空间 / 模型热度跨 run 差异（tester §6 已声明）——但"反弹只随 P3 引入出现"跨 2 次 run 稳定，已基本排除纯噪声。

## 2. epoch 门退化（判定 2）

### 2.1 机制（代码证据）

- **miss 证据记录**（scheduler.py:3216-3226）：REVOKED_MISS 且 genuine_miss 时记录 `hicache_restore_miss_epoch = tree_cache.l3_publish_epoch()`（**全局**值）+ `miss_generation`。
- **re-arm 门**（scheduler.py:4546-4556 → hicache_restore.py:227-250 `miss_rearm_allowed`）：`if current_epoch > miss_epoch: return True`——**只看全局 epoch 是否前进**，不要求"本请求前缀的 L3 覆盖真变"。
- **ready-horizon NO_L3 负缓存**（scheduler.py:3240-3244）同样以全局 epoch 为 cursor——同一缺陷的第二个受害者。

### 2.2 非平稳下失效（代码证据 → 强推理）

- **bump 来源不区分前缀**（unified_tree_core.py:2245 `_promote_persisted_subtree` 每次 promotion 都 `_bump_l3_publish()`）。8-agent 并发下，任一前缀链的写 ack / 补链 promote 都推高全局 epoch。
- 因此在 0.5-1s 紧循环（WAIT→RESTORING→revoked:miss→MISS→WAIT，~2.1 epoch/s 前移）内，`current_epoch > miss_epoch` 几乎**必然**在下一秒为 True → **sticky MISS 判据秒级即过 → re-arm 总是放行 → epoch 门退化为"永不拦截"**。
- 观测佐证：最差 offender bb4deb 22 次紧循环**无一次 ADMISSION_DENY/no_token**（tester §4.2）。
- **推论**：P1 在低并发/低写负载（~0.8/s）下 epoch 门能拦截一部分（epoch 前移慢，MISS 请求在窗口内保持 current==miss）；P3 + 8-agent 把 bump 率推高后门即失效。**这不是"门设计错"，而是"门的输入（全局单调计数）在并发下与它要判定的语义（本前缀 L3 覆盖变化）脱钩"**——正是 architect open issue 1（l3ack-e2 §8）。

### 2.3 miss 判据应锚定的东西

- **正确语义**：MISS 证明"请求前缀在探针时刻 L3 缺失"；重探同一前缀应被拒绝，**直到该前缀的 L3 覆盖有实质变化**（该前缀出现新的写 ack / restore 读回 / 该前缀的 storage_persisted/storage_restored 真变）。
- **当前实现锚错**：锚的是**全局**"任意前缀 durability 事件"→ 无关链写 ACK 的全局 bump 也放行（放行过多）；同时**漏掉**"同一前缀内部因 reconcile 补链导致的覆盖变化其实值得放行"（粒度粗，因果不对齐）。
- **建议的实质物材判据**：`is_l3_durable(anchor) = storage_persisted OR storage_restored`（unified_tree_core.py 已有统一谓词）——它是**前缀级事实**，正好是该前缀的实质 cache 状态。见 §5。

## 3. P3 收口重审裁决（判定 3a）

**维持 confirmed，不重审。**

- **正交性**：HOL 修复判定路径 = `frontier_anchor_ready`（radix :2490）/ `is_l3_durable`（tree_core :2200）/ T13 60s timeout 状态机；miss churn 放大路径 = **全局 `_bump_l3_publish` 计数**。两者**在代码里不交叉**（P3 不触碰 scheduler / hicache_restore / restore 资格 / capacity）。
- P3 修 HOL 是**真缺陷修复**（ACKed 后代被 clear/删除父链永久 strand），其正确性证据（P3 fix tester e1 + harness）不依赖 epoch 计数。
- P3 顺带**放大 miss churn**是**副作用**（全局计数路径被并发写扩大），不构成"durable-frontier HOL 已消除"的否定——confirmed 结论与反弹**独立**。
- 结论：**P3 收口不动**；反弹作为"P1 门在并发下失效"的现象归因到 epoch 粒度缺陷（见 §5 修正方向），在 epoch 门修正中一并处理。

## 4. fast-forward + soak 裁决（判定 3c）

**可推进，带两个条件。**

- **可推进的理由**：P3 收口 confirmed（§3）未被本次反弹动摇；P1 门失效是"已知缺口"（open issue 1 的确认），不阻塞 P3 本身。若拦下 fast-forward，也无现成修复可挂（修正方向尚未实现）。
- **条件 1（必带）**：把"re-arm 时刻的真实逐链 epoch"观测加进 soak（见 §6 B-2，成本极低、可证伪）——否则 miss churn 水平只能当"特征基线"而非"P1 改善复现"。
- **条件 2（口径）**：用户裁决的 fast-forward + soak 的 PASS 判据**不应包含**"miss churn 回到 P1 水平"，只应包含"无 60s HOL 复发 + 无崩溃/正确性 + forward progress"（与 P3 收口口径一致）；若 soak 观测证明"re-arm 与自身链实质变化对齐"，则可追加 epoch 门修正为 followup。

## 5. epoch 门修正方向（架构建议，不改实现）

**最小充分结构变更 = 把"epoch"从全局计数改为"per-prefix-anchor 版本号"，让 miss 判据只与本前缀实质变化对齐。**

1. **anchor/前缀粒度版本**：在 `UnifiedTreeNode` 上加 per-anchor 单调版本（或复用 storage_persisted/storage_restored 的组合 + 递增版本）。`_bump_l3_publish` 改为**只 bump 事件所在 anchor/前缀**（写 ack / restore 读回作用于哪个 anchor 就 bump 哪个）。保留全局计数仅作诊断统计，不参与门判定。
2. **miss 判据改锚**：`miss_rearm_allowed` 对比"本请求前缀 anchor 的版本"（miss 时记录该 anchor 版本），而不是全局 epoch。无关链写 ACK 不再放行；本前缀 reconcile 补链的实质覆盖变化能正确放行。与 ready-horizon NO_L3 负缓存（cursor 同步改 per-anchor）一致。
3. **与实质物材判定结合**：miss 放行条件可加"该前缀 anchor `is_l3_durable` 已变"（`storage_persisted OR storage_restored`，前缀级事实）作为第二判据——版本前进但 durable 仍 False 时仍不放行（防 reconcile 空转 bump 被误当放行信号）。
4. **与 too_short never-case 门统一**：`has_restore_potential` 的 `host_hit_length>0` 短路（too-short 空转根因）与 miss_rearm 门都是"re-arm 前判据"——统一为**"restore eligibility 状态机"**：一个请求能否/应否 re-arm = f(本前缀物材 [host/device/L3] + 本前缀版本 vs 上次判定版本 + 是否 too_short never-case + generation 是否变)。这正是用户预警的"第三种同构 churn 才启动统一状态机"——**本次（epoch 门）确认是第三种同构，可启动统一状态机设计**。
5. **不做 epoch=0 特判**：不为 "0 次 bump" 或 "bump 频率低" 做特例——那只是规避症状。

## 6. 验证项（判定 1/2 的闭合路径）

- **B-1（tester，判定 1 的逐链闭合）**：对最差 offender 的 re-arm 时刻做配对观测——per-pass `l3_publish_epoch` + 该前缀 deferred 集是否非空 + 该前缀 anchor durable 状态。若 re-arm 时该前缀 deferred 非空/durable 未变但全局 epoch 已前进 → 证实"无关链 bump 放行"。若 re-arm 时该前缀确有实质变化 → 反弹部分来自"P3 reconcile 真在补链、放行合理"，需下调反弹严重度。
- **B-2（soak 内夹带，低开销）**：soak 日志里为 `miss_rearm_allowed` 放行打"rearm_by_epoch / rearm_by_generation / rearm_dup"三类计数 + 每 pass 全局 epoch。若 rearm_by_epoch 占比高且对应前缀 deferred 常空 → 证实门失效仍在 soak 期间活跃（为修正方向提供数字）。

## 7. Open Decisions（返回 orchestrator / 用户）

1. **统一 restore eligibility 状态机的触发**：本次 epoch 门失效是否作为"第三种同构 churn"的正式判据启动统一状态机设计（§5-4）——是，本次证据链（全局计数与语义脱钩）已满足"同构"定义。
2. **修正实现优先级**：epoch 门修正（§5-1/2）是否作为独立小修，还是并入统一状态机一起设计。倾向：per-anchor 版本（§5-1/2）先行（最小、局部、低风险），统一状态机随后。
3. **soak 判据口径确认**：fast-forward + soak 的 PASS 判据是否按 §4 条件 2 收窄（不含"miss churn 回到 P1"）。需用户确认。

## Migration / Impact（修正方向如果被采纳）

- 改动面：`unified_tree_core.py`（per-anchor 版本字段 + _bump 粒度）+ `scheduler.py`（miss 记录/re-arm 判据 + ready-horizon cursor）+ `hicache_restore.py`（miss_rearm_allowed 签名）。纯 predicate/字段粒度变更，无状态机大改（若走统一状态机则另计）。
- 不影响已确认基线：P3 HOL 修复（不触碰）、RH、Fix A/B、P2-IO extent 后端。
- 风险：per-anchor 版本需要在"anchor 被 clear/删除/重新锚定 root"时正确处理（版本归零/新号）；这是 open decision 2 的实现细节，架构层面已给出语义（版本代表"该 anchor 的 durability 事件计数"）。

## Open Issues

- 判定 1 的逐链因果未闭合（§6 B-1）；判定 2 的"re-arm 时真实 epoch"未直接观测（tester §6 已声明）。
- anomalous-epoch 语义（若测试中出现 epoch 异常跳变）需 tester 提供证据再收敛；不做 epoch=0 特判。
