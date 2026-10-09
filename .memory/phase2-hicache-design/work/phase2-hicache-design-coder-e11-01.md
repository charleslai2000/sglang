# phase2-hicache-design-coder-e11-01 — P2-1 终判阻断项：lock_ref 锁链泄漏 → GPU OOM

## status
done（全量配对核对完成 + OOM 机制定位 + 最小修复 + 5 新测 + 本机/远端全绿 + 双侧 md5 + 未启动引擎）

## 1. 全量配对核对（inc/dec 调用点清单与配对结论）

| # | inc 点 | 位置 | dec 点 | 配对 |
|---|---|---|---|---|
| 1 | `_req_inc_lock_ref(req)` 准入锁（req.last_node） | schedule_policy.py:1031（dllm 1452 / 非 chunked 1465 / chunked 1516） | `_dec_req_lock`：cache_finished_req（unified_radix_cache.py:975）/ cache_unfinished_req（L1079） | 活请求配对；add_chunked_req 不重复 inc |
| 2 | `_lock_node` 临时准入锁 | schedule_policy.py:1132 | finally dec（L1141/1143） | 平衡 |
| 3 | cache_unfinished_req 每 chunk：dec 旧 last_node + inc 新 last_node | unified_radix_cache.py:1079/1091 | 下一 chunk 的 dec / cache_finished_req | 活 chunked 请求逐 chunk 配对 |
| 4 | `_execute_and_commit_kv_backup` write_through D→H | unified_radix_cache.py:1420 | `_finish_write_through_ack`（ack 到达时） | ack 到达即配对 |
| 5 | `load_back` 祖先锁 | unified_radix_cache.py:1518 | L1567/1576/1589（全部失败路径） | 平衡 |
| 6 | load_back 成功 → ongoing_load_back 条目 | unified_radix_cache.py:1603 | `loading_check` L3169-3171（ack 到达） | ack 到达即配对 |
| 7 | decode_hicache_mixin.py:234 | 仅 disagg decode（本引擎 disaggregation_mode=null，未启用） | — | 不适用 |
| 8 | `_write_backup_storage_node` inc_host_lock_ref | unified_radix_cache.py:1763 | `_drain_backup`（storage ack） | ack 到达即配对 |
| 9 | prefetch_from_storage（ongoing_prefetch 条目） | 主机锁，finalize/revoke/abort 释放 | release_aborted_request 覆盖 | 配对 |

**配对结论：未发现 inc 无 dec 的泄漏点。** 所有站点在正常与失败路径上均配对。崩溃 dump 中 [9]→[195] 链上恰好 1 个 lock_ref = 在途 chunked prefill 请求对自身链的合法持有（cache_unfinished_req 的 inc，chunk 间驻留，`#running-req: 0` 因 chunked_req 不在 running_batch）。锁链 16384 tokens 是该请求真实的 working set，不是泄漏。

## 2. OOM 机制定位（四次同模式根因）

崩溃现场（1g，22:08:45）：device 池 32768 = 锁链 [187]…[195]（16384，lock_ref=1，prefill 中请求的自身链）+ [167] 链（16375，无锁，可驱逐）+ 9 空闲。`full token usage` 只统计非可驱逐部分（capacity−available−evictable），故 0.12→0.50 的爬升 = 锁链自身的增长。

**死锁链：**
1. 预取并发超载 host 池（49152）：ec97487a 27776-token 材料 3 次 finalize 驻留 + f3ecade6/c4aff0c7 各 20910 在途（22:08:42 发起，22:08:47 才 io_finished）→ evict_host 回收 [167] 链 host 副本（redundant duplicates）→ is_backuped([167])=False。
2. 下一 chunk（2048）分配 → 驱逐 walker 选 [167] 链叶 [175] → D→H backup 失败（`_execute_kv_backup` evict_host 无法腾出 2048，L1436-1443）→ `drop_subtree_no_host(175)` 拒绝（L1302-1311：子树上 host_lock_ref>0 —— 在途预取的 DMA 材料锁在 [180]…[186]）→ 该链全部叶子同因不可驱逐 → 0 回收 → RuntimeError → SIGQUIT。
3. **frontier 热循环**：waiter 7349fb0c 在 node 175 以 ~1ms 周期振荡（8,351 次 register_frontier_waiter）——T11/T12 唤醒谓词 `frontier_anchor_ready`（is_storage_persisted 或已删）通过，而 `_prefetch_kvcache` gate（is_backuped）失败：host 副本被压力回收后 gate 永远不过、wake 每 pass 重发 → 每 pass 重跑 write_backup_storage（D→H 重试 + L3 gap 走查）。

## 3. 修复清单（最小改动；未 commit 未 push）

| 文件 | 位置 | 改动 |
|---|---|---|
| python/sglang/srt/mem_cache/unified_cache/unified_tree_core.py | drop_subtree_no_host 后新增 | `evict_device_leaf_storage_backed(node_id)`：D→H backup 失败且 drop 被拒、链已 L3-persisted 时，只释放叶子 device 层、保留节点与 host 子树（L3 副本即持久备份）；模板 = `_demote` 去 backuped 断言 + evictable_device_leaves discard + parent 集合更新 |
| python/sglang/srt/mem_cache/unified_radix_cache.py | `_evict_components` L823-832 | 新 elif：`is_storage_persisted(node_id)` 时走 hollow 驱逐（打破 host-full + 子树锁死锁）；配套 `_evict_device_leaf_storage_backed` 包装（L754-762） |
| python/sglang/srt/mem_cache/unified_radix_cache.py | is_backuped 后新增 | `prefetch_gate_ok(node_id, buffer_mode)`：gate 谓词 = is_backuped or is_root or **is_storage_persisted** or (buffer_mode and hash)——与 T11/T12 wake 谓词一致 |
| python/sglang/srt/managers/scheduler.py | `_prefetch_kvcache` L2913 + t38c probe L2905 | 原内联 gate 改为 `tree_cache.prefetch_gate_ok(last_host_node, buffer_mode)` |

**语义说明**：锁链 [187] 非泄漏，tester 判定的"锁未释放"不成立；真正的阻断是 [167] 链在 host-full 下的不可驱逐（backup 失败 + drop 被在途预取锁拒绝）。hollow 驱逐使 L3-persisted 链的 device 层可无条件释放（L3 即备份，等价 write_back 语义），gate 一致性消除热循环并允许 persisted anchor 重发预取重建 host 副本（恢复 demote 免分配路径）。

## 4. 新增测试（torch-free；RED→GREEN 已做：初版 stub 未绑定 is_backuped 等实例属性导致断言失败 → 修复后全绿）

- `PrefetchGateAgreementTests.test_gate_agrees_with_frontier_wake_on_persisted_anchor`：persisted 但 unbacked anchor 唤醒谓词与 gate 一致（热循环回归钉）
- `test_gate_still_rejects_unpersisted_unbacked_anchor`：原 gate 行为不变
- `test_gate_accepts_backuped_root_and_buffer_hash`：其余 gate 分支
- `StorageBackedHollowEvictionTests.test_hollow_evict_breaks_backup_and_drop_deadlock`：backup 失败 + drop 拒绝 + persisted → hollow 释放 2048（OOM 回归钉）
- `test_no_hollow_when_chain_not_persisted`：非 persisted 链不 hollow（不丢唯一副本）

## 5. 证据（验证命令与真实输出）

- 本机 torch-free：`test_storage_regression.py` **42/42 OK**（37+5）、`test_hicache_restore.py` **43/43**、`test_drain_reentry.py` **12/12** → 合计 **97/97**
- 本机 `python3 -m py_compile` 3 源文件 + 测试文件：PY_COMPILE_OK
- 部署 `/root/sglang-b1-continuity/`（3090，ssh 24052），**双侧 md5 四文件全一致**：unified_tree_core.py `7d5ac691…`、unified_radix_cache.py `d992a972…`、scheduler.py `7305eb0b…`、test_storage_regression.py `c884b7c4…`
- 远端真实 torch（sglang-patch env）：REMOTE_PY_COMPILE_OK + **97/97 全绿**（0.074s）
- 引擎未启动：GPU 15MiB/0%，无引擎进程（jupyter-lab 883 为既有无关进程）

## followups
1. **重跑建议（按序）**：先 K=1 回归（复用 0c 链，验证 hollow 驱逐与 gate 一致性不破坏 restore 路径）→ 通过后 K=8 完整第五次 run（md5 已核对：新代码 7d5ac691/d992a972/7305eb0b）。预计 K=8 不再 OOM：L3-persisted 链在 host-full 下可驱逐，frontier 热循环消失
2. 若 K=8 仍失败：检查 prefill 预算 `rem_total_tokens_lock`（22:08:28 出现 1 次）与 prefill 准入对 chunked 请求 #cached-token: 0（重复链写入）的策略——重复链本身是空间浪费，但不阻断
3. `evict_device_leaf_storage_backed` 的 hollow 节点在 match_prefix/insert 路径的行为未在真实 torch 下直接验证（测试为 stub 级）——K=1 run 的 restore 命中即覆盖

## open_issues
- 锁定链 = 在途 chunked 请求合法 working set（16384 tokens 恰为半池属高负载巧合：两链各 ~16K 同时驻留）；若设计上要限制单请求 working set 上限，属 p2-0-10 决策，不在本次修复
- host 池在途预取（DMA）期间 [167] 链不可驱逐的窗口（~2.5s）是设计内瞬态；hollow 驱逐消除了该窗口的致命性
- 远端 /root/sglang-b1-continuity-p2b1-staging/ 存在旧测试副本（31a82696 时代），未触碰
