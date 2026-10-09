# P3 收口裁决 — 剩余 restore_recompute(timeout) 单例分类确认（architect e1，read-only）

status: done
artifacts:
- 本报告（read-only 复核，未改任何代码）
- 代码语义：`unified_tree_core.py`（advance_storage_persisted / clear_storage_durable / deferred_acked_nodes / collect_storage_gap / _promote_persisted_subtree / is_l3_durable）、`unified_radix_cache.py`（_reconcile_deferred_acked / frontier_anchor_ready / _wake_frontier_waiters / has_restore_potential / prompt_can_qualify_for_prefetch）、`scheduler.py`（_reconcile_restore_states T12/T13）、`hicache_restore.py`（T13 状态机）、`server_args.py`（hicache_restore_wait_timeout_s=60.0）
- 确定性 harness：`3090-dev/test_p3_warmtree_hol.py`
- tester 证据：`work/phase2-p3-fix-tester-e1.md`（rid 9d8b5428 单例分类）
evidence:
- P3 commit 30a5a3698a diff（tree_core +58/-1、radix +78）逐行核对
- unified_tree_core.py:2209-2246 advance_storage_persisted：仅当 parent 为 None/root/storage_persisted 才 `_promote_persisted_subtree`；promotion 只由真实 ack（storage_acked=True 在此写入）或 restore 驱动
- unified_tree_core.py:2185-2198 deferred_acked_nodes = storage_acked && !storage_persisted（无 ack 不入集）
- unified_radix_cache.py:2129-2153 _reconcile_deferred_acked_inner：只对 deferred 集内节点 write_backup_storage + advance_storage_persisted；comment 明确 "Reconciliation never sets storage_persisted itself — promotion stays a real-ack / real-restore fact"
- unified_tree_core.py:2132-2156 clear_storage_durable B 守卫：有 acked-deferred 后代时不清 anchor
- scheduler.py:3153-3172 T13：WAIT_CAPACITY 超时（hicache_restore_wait_timeout_s=60.0）→ ADMIT_RECOMPUTE → restore_recompute(timeout)
- scheduler.py:3057-3075 GATE_SKIP_FRONTIER（T5）入口：anchor 非 storage anchor + prompt_can_qualify_for_prefetch → register_frontier_waiter
- unified_radix_cache.py:2490-2503 frontier_anchor_ready = node_exists 或 is_l3_durable 或 is_root
- unified_tree_core.py:2200-2207 is_l3_durable = storage_persisted or storage_restored
- unified_radix_cache.py:3191-3228 has_restore_potential：host>0 / ongoing / backuped / root
- harness test_p3_warmtree_hol.py：确定性复现 P3 场景（acked-deferred 愈合），非 9d8b5428 场景
- tester e1：wait→timeout 恰 60.3s，与 T13 默认 60.0s 语义一致

## Conclusion

**P3 可收口为 confirmed。** 唯一剩余 restore_recompute(timeout) 单例（rid 9d8b5428, BB2, dev=17079/host=0/store=0）分类为**正确兜底 recompute（非 P3 缺陷）**，非 durable-frontier HOL 残留。P3 durable-frontier HOL 已消除。

## Current Architecture（核实后的 P3 语义）

- **reconcile 驱动源**：`_flush_pending_storage_writes` 每 pass 末尾调用 `_reconcile_deferred_acked()`，扫描 `deferred_acked_nodes()`（= `storage_acked && !storage_persisted`）。该集合的**唯二入口**是 `advance_storage_persisted` 写入 storage_acked=True（真实 L3 写 ack 驱动）与 `mark_storage_restored`（真实 restore 读回）。**无真实 ack 的节点永远不进此集。**
- **promotion 约束**：reconcile 对 deferred 节点仅做 (1) `write_backup_storage` 补写 gap 链（真实 L3 写）→ 真实 ack； (2) 重跑 `advance_storage_persisted`——其内部仅在 `parent is None/root/parent.storage_persisted`（父链连续）时 `_promote_persisted_subtree`。**reconcile 从不自行置 storage_persisted**；所有 promotion 由真实 ack / 真实 restore 驱动。此即"reconcile 永不伪造 durable"约束，成立。
- **B 守卫**：`clear_storage_durable` 遇 `_has_deferred_acked_descendant` 时不清 anchor，清权推迟到 reconcile pass。无 acked-deferred 后代时与旧路径一致。
- **frontier 等待**：scheduler `GATE_SKIP_FRONTIER`（T5）在 anchor 非 storage anchor 且 `prompt_can_qualify_for_prefetch` 时 park frontier waiter；`frontier_anchor_ready(anchor)` = anchor 存在且 `is_l3_durable`（storage_persisted 或 storage_restored）。无 L3 物材的 anchor 恒 False → 60s T13 timeout → `ADMIT_RECOMPUTE`。

## Problem / Forces

P3 修复前：ACKed 但父链未 persisted 的节点（deferred）若父链被 clear/删除，无任何重 promotion 机制 → `frontier_anchor_ready` 恒 False → 永久 HOL → 60s T13 timeout → restore_recompute(timeout)（warm-tree p95≈61s 根因）。P3 以 A（per-pass reconcile）+ B（clear 守卫）最小修复消除该根因链。

## Proposed Architecture（P3 现状，无需改动）

P3 A+B 已正确收口 durable-frontier HOL：
- A3 每 pass 对 deferred 集补链 + 真实 ack 驱动重 promotion + 唤醒 frontier waiter（T12 语义同 ack drain）；
- B 守卫防 clear 清掉仍被 acked 后代依赖的 anchor；
- 不改 timeout/wake 状态机/scheduler/restore 资格/容量。

## Alternatives（单例处置）

该单例不触发 reconcile（无 storage_acked 节点入集），故 reconcile 按设计不做任何事。可选优化（非缺陷）见 Open Decisions。

## Migration / Impact

P3 无需变更。该单例若优化，属新增前向判定逻辑，不改 P3 既有 reconcile/clear/ack 语义，可独立评估。

## 单例分类判定（rid 9d8b5428）

- **判据**：dev=17079/host=0/store=0 = 请求 anchor 链为纯设备缓存（无 L3 读回、无 host copy、无 L3 写 ack）。该链**无任何节点满足 storage_acked** → `deferred_acked_nodes()` 为空 → reconcile 正确地不做任何 promotion（若强行 promote 即伪造 durable，违反核心约束）。
- **是否为 HOL 残留**：否。HOL 定义 = "ACKed durable 后代被永久 defer 且无修复机制"。9d8b5428 无 ACKed durable 后代（无 L3 写 ack），不属于 P3 场景。wait→timeout 恰 60.3s 是"无 durable 物材的 FRONTIER 等待 idling 满一个 T13 时钟"的干净信号（frontier_anchor_ready 因无物材恒 False），与 T13 默认 60.0s 语义一致。
- **确证边界**：dev/host/store 的逐 rid 解读与"该链无任何 storage_acked 节点"这一关键前提，直接证据在远程 `/root/evidence-gate3-p3fix/`（本地不可读）。代码语义强支持该解读（store=0 且无 ack → deferred 集为空 → reconcile 无动作 → 干净满时钟 idle）；且若该节点确曾 storage_acked，reconcile 会补链重 promote，而观测为 60.3s 满时钟 idle，与"无物材"一致。此前提为 tester 证据 + 代码语义双支撑，非本地可直读，标为证据指针。

## Open Decisions

- **open followup（可选优化，非缺陷）**：对"纯设备缓存、无 host copy、无 L3 写 pending"的 FRONTIER 等待，在 `GATE_SKIP_FRONTIER` 入口做前向判定（该 anchor 永无可能变成 durable，因为无 L3 写/restore 物材 → 等待必 idle 满 60s T13），直接 `ADMIT_RECOMPUTE`，省去空等。注意与 `prompt_can_qualify_for_prefetch` 的语义区分：能 qualify 仅表示"后缀长度可达阈值"，不等于"存在可等待的物材"；需判定"有无任何会使其 durable 的写/restore 在途"。此为优化，不改 P3 收口。
- P3 核心判据 restore_recompute(timeout)=0 的严格 gate 若坚持，则需先采纳上述前向判定；否则该单例记为非阻塞 followup。

## Followups

- （可选）2h warm-tree soak 确认长期无 60s cliff 复发（tester followup，非收口阻塞）。
- （可选）前向判定优化评估（见 Open Decisions）。
- 若需彻底闭合"无 storage_acked 节点"前提，可让 tester 从远程证据逐行复核 9d8b5428 的 anchor 链 ack 状态（非阻塞，分类已由代码语义 + 60.3s idle 双支撑）。

## Open Issues

- 无阻塞。1 个剩余 restore_recompute(timeout) 已分类为正确兜底（无 durable 物材），非 P3 缺陷。
