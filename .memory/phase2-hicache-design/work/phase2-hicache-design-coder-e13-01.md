# P2-1 reviewer M1/M2 修复 + 回归 — coder e13-01 报告

## 1. status

**done** — M1（部分写 ack 完整性校验 + 清除重试）与 M2（晋升追溯化）已修复，各配 RED→GREEN 测试；本机 105/105、远端 3090 105/105、双侧 md5 4/4 一致；引擎未启动（远端 GPU 15 MiB、0 引擎进程）；未 commit 未 push。

## 2. artifacts（改动文件）

- `python/sglang/srt/mem_cache/unified_radix_cache.py`（`_drain_backup`，:2831-2871）
  - **M1**：`advance_storage_persisted` 前置完整性校验 `operation.completed_tokens >= len(operation.host_indices)`（host_indices 为页索引展平，len == 期望 token 数，与 completed_tokens 同单位）；部分写走 else 分支：不晋升、不 wake，`tree_core.clear_storage_written(node_id)` 清除提交去重守卫使下次 gap fill 重写，并记 `[P2A] partial backup ack` warning。
  - **M2**：`advance_storage_persisted` 现返回本次晋升的节点列表，drain 对每个晋升节点调 `_wake_frontier_waiters`（父晋升时子被追溯晋升 → 子的 frontier waiter 被 wake）。
- `python/sglang/srt/mem_cache/unified_cache/unified_tree_core.py`
  - `UnifiedTreeNode.__init__` 新增 `storage_acked` 标志（:146）——与 storage_written（=已提交，可能 in-flight）区分，追溯晋升只认已 ack 节点，杜绝"子未 ack 即晋升 → 设备层释放于不完整 L3 副本"。
  - `advance_storage_persisted`（:1976-2001）重写：置 storage_written + storage_acked；父链连续（parent 为 None/root/persisted）→ `_promote_persisted_subtree` 递归晋升，返回 `list[NodeId]`（原返回 None）；幂等（已 persisted → []）。
  - 新增 `_promote_persisted_subtree`（:2003-2015）：递归晋升 `storage_acked and not storage_persisted` 的子节点；递归止于未 ack 子节点（其自身的 ack drain 会再触发）与已 persisted 子节点（其晋升时已处理全部 acked 后代）——摊销 O(节点数)，无热循环。
  - 新增 `clear_storage_written`（:1968-1972）。
- `3090-dev/test_drain_reentry.py`：`_FakeTreeCore` 升级为忠实链规则模型（父先于子的条件晋升 + 追溯晋升 + storage_acked），`advance_storage_persisted` 返回列表；既有 3 处 backup ack 补 `completed_tokens`/`host_indices` 字段（新增 `_backup_ack` helper）。新增 2 测。
- `3090-dev/test_storage_regression.py`：`_FakeTreeCore.advance_storage_persisted` 返回 `[node_id]`；新增 `StoragePromotionChainTests`（真实 UnifiedTreeCore）3 测。

## 3. 新增测试（RED→GREEN 均已做）

| 测试 | 钉住语义 |
|---|---|
| `test_drain_backup_partial_ack_does_not_promote_and_clears_guard`（drain 级，M1） | 部分写 ack（8/16）不晋升、storage_written 被清除、waiter 不 wake；随后重写全量 ack（16/16）→ 晋升 + wake（重试闭环） |
| `test_drain_backup_parent_ack_promotes_child_acked_earlier`（drain 级，M2） | 子先 ack → 不晋升不 wake；父后 ack → 子被追溯晋升 → 子的 frontier waiter 进 ready；重复 drain 不重 wake（exactly-once） |
| `test_child_acked_before_parent_promotes_on_parent_ack`（真实树，M2） | `advance(child)` → `[]` 不晋升；`advance(parent)` → `[parent, child]` 双晋升；重复 advance 幂等 |
| `test_submitted_but_unacked_child_is_not_retroactively_promoted`（真实树，M2 边界） | storage_written 仅提交未 ack → 父晋升时子不晋升（防设备层释放于 in-flight 副本） |
| `test_partial_ack_clears_dedupe_guard_for_rewrite`（真实树，M1 边界） | clear_storage_written 后 `collect_storage_gap` 重新收集该节点 |

RED 验证（临时改回旧逻辑再还原，非 git 操作）：
- M1：旧 drain（无条件晋升）→ `test_drain_backup_partial_ack_...` FAIL（`True is not false`）；还原后 GREEN。
- M2：旧 advance（非追溯）→ `test_child_acked_before_parent_...` FAIL（`[9] != [9, 10]`）；还原后 GREEN。

## 4. 证据（验证命令与真实输出）

- 本机（sglang-venv，torch 2.13.0+cu129）：`python -m unittest test_drain_reentry test_storage_regression test_hicache_restore` → **Ran 105 tests in 0.060s OK**（基线 100 + 新 5；45+2+3+43+12）
- 新 5 测单独跑：**Ran 5 tests in 0.001s OK**（含 `[P2A] partial backup ack: node 42 got 8/16 tokens; will rewrite` 日志可见）
- `python -m py_compile` 4 文件：PY_COMPILE_OK
- 远端（3090，`root@175.155.64.171:24052`，`/root/sglang-b1-continuity/`，sglang-patch env，torch 2.13.0+cu130）：**Ran 105 tests in 0.082s OK**；新 5 测 **Ran 5 tests in 0.001s OK**
- **双侧 md5 4/4 一致**：unified_tree_core.py `a2721792…`、unified_radix_cache.py `b77e23ac…`、test_drain_reentry.py `f88220a9…`、test_storage_regression.py `95037123…`
- 引擎未启动：远端 `ps -eo cmd | grep -E 'python.*(launch_server|sglang)'` 0 命中、`nvidia-smi` memory.used = 15 MiB（部署全程未触碰引擎；无引擎在运行，未与 tester 实验冲突）

## 5. summary（修复语义 + 交互确认）

- **M1**：部分写 ack 不再晋升 persisted（hollow 的"L3 副本即持久备份"前提在部分写窗口内成立），清除 storage_written 允许下次 gap fill 重写（`_page_backup` 的 break-后-ack 行为保持原样，完整性判定收敛在 drain）。host 锁在部分 ack 时照常释放、重提交时重新加锁（inc/dec 配对平衡）；若 host 副本在重试前被 duplicate-reclaim 回收，`build_storage_backup_spec` 经 `backuped`（派生自 host_value）返回 None → 重试安全跳过，不写垃圾、不崩溃，仅损失缓存效率（有界）。
- **M2**：`advance_storage_persisted` 晋升时递归晋升 `storage_acked and not storage_persisted` 的子节点并返回全部新晋升 id；drain 对新晋升的每个节点 wake 其 frontier waiter。`storage_acked` 与 `storage_written` 分离是关键——子"已提交未 ack"绝不被追溯晋升，防止 hollow 在不完整副本上释放设备层。
- **F1**（backup 失败 evict_host 重试）：在 `_drain_write_through_acks`/evict 路径，本改动未触碰。
- **F2 exactly-once**：drain 每个 ack 仍恰消费一次（pop entry → 释放锁 → 判定）；wake 保持纯 set 成员操作、零队列消费零回调；重复 drain 不重 wake（测试钉住）。
- **KeyError 兜底**：`clear_storage_written`/`advance` 沿用原 `node_by_id` 暴露面（in-flight 备份节点受 host 锁保护不被删除——既有不变式，未新增暴露）；`_wake_frontier_waiters` 有 `node_exists` + `is_storage_persisted` 双守卫；重试路径 `_flush_pending_storage_writes` 有 try/except KeyError backstop。
- **M1×M2 交互**：部分 ack 不置 `storage_acked` → 追溯晋升跳过它；其重写全量 ack 时再晋升（含其 acked 后代）。M1 的"父部分写→子先全量 ack"正是 M2 追溯晋升的现实触发场景，两修复互补。

## 6. followups / open_issues

- M1/M2 之外的 L1（hollow 不记 dropped-token 指标）、L2（storage 降级后 persisted flag 不失效）为 reviewer 的 Low 项，本任务范围外，未动。
- `StoragePromotionChainTests` 用真实 `UnifiedTreeCore`（stub components），与既有 `HollowStateSanityCheckTests` 同构；运行级别覆盖仍由 tester 的 K 级 run 负责。
- 未 commit 未 push（按要求）。
