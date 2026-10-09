# P2-1 eviction deadlock 两轮修复 + 测试配对 — reviewer e1 报告

## 1. status

**done** — 审查完成：hollow-eviction fallback（e11）+ sanity_check 放宽（e12）+ 测试配对（100 测）全量静态核对，md5 与 e17 现场一致（unified_tree_core fb931e5c / unified_radix_cache d992a972 / scheduler 7305eb0b / test_storage_regression 3378313d）。结论：**APPROVE-WITH-NOTES**（0 Critical / 0 High；2 Medium 潜在缺口 + 2 Low；均不阻塞，附修复建议）。

## 2. artifacts（审查范围）

- python/sglang/srt/mem_cache/unified_cache/unified_tree_core.py（e11+e12；sanity_check :2223-2329；evict_device_leaf_storage_backed :1336-1370；advance_storage_persisted :1965-1977；_is_device_leaf :1782-1798；_is_host_leaf :1800-1812）
- python/sglang/srt/mem_cache/unified_radix_cache.py（_evict_components fallback :823-832；_evict_device_leaf_storage_backed :755-763；prefetch_gate_ok :1792-1803；frontier_anchor_ready :1820-1834；register_frontier_waiter / _wake_frontier_waiters / discard / pop :2370-2445；_drain_backup :2824-2852；_handle_storage_failure :3273-3300；_write_backup_storage_node :1750-1787）
- python/sglang/srt/managers/scheduler.py（_prefetch_kvcache gate :2863-3010；_reconcile_restore_states :3014-3085；admission WAIT skip :3886-3890；NO_TOKEN/RESTORE_DENIED 分支 :3923-3957）
- python/sglang/srt/managers/scheduler_components/hicache_restore.py（next_restore / wait_clock_next / capacity_wake_applies）
- python/sglang/srt/managers/cache_controller.py（stop_storage_threads / _storage_thread_fatal / _page_backup :1353-1373）
- python/sglang/srt/managers/schedule_policy.py / schedule_batch.py / hiradix_cache.py / hybrid_cache_controller.py / server_args.py
- 测试：3090-dev/test_storage_regression.py（45 测，含 HollowStateSanityCheckTests 3 + StorageBackedHollowEvictionTests 2 + PrefetchGateAgreementTests 3）、test_hicache_restore.py（43 测）、test_drain_reentry.py（12 测，含 M2 4 测）

## 3. evidence（关键结论的 file:line 依据）

### 3.1 不变量保持（已验证）

1. **L3 副本存在性**：hollow 前置 `is_storage_persisted` 要求自身 L3 写 ack（advance_storage_persisted :1965-1977；_drain_backup :2838）。L3 写需 `node.backuped`（build_storage_backup_spec :1912-1917）→ 创建路径为"曾 backup→L3 ack→host 被 duplicate-reclaim（:1447 _reclaim_full_host_duplicates 仅双份时回收）→ 再成 D-leaf"。hollow 只释 DEVICE 层（target=EvictLayer.DEVICE，:1336-1370），aux host 切片由组件自身 evict_component 的 "After device tombstone → insert into host LRU" 维护（mamba_component.py:348-355、swa_component.py 同）→ 无 host LRU 悬挂。
2. **整链可恢复性**：restore 按 hash 读 L3（query_storage_hit_length :1840-1883 → _storage_hit_query），与树结构 dead-node 截断无关；match 停于 hollow 节点（"dead node (evicted + not backuped)" 语义，:737 区域）但 anchor 链 L3 连续 → CHAIN_GAP 不变式保持。
3. **leaf 集合一致性**：hollow 后 evicted=True、backuped=False → _is_device_leaf/_is_host_leaf 均 False（:1789/:1806）→ 不在任何 leaf set，sanity PART 3 自洽（e12 测试用真实树钉住）。
4. **gate/wake 闭合**：gate=backuped∨root∨persisted∨(buffer∧hash)（:1792-1803）；T12 wake=自身 ack+链晋升（:2426-2443，node_exists/persisted 双守卫）；T11 FRONTIER=persisted∨deleted（:1820-1834）。热循环形态核查：persisted→gate 过（闭合）；deleted→self-heal 重 match（_prefetch_kvcache 内 init_next_round_input 先 re-match 再 gate :2871-2913 → 旧 id 不触发 KeyError）；backuped-未-persisted→无 wake（睡到 T13，有界，非循环）；重 match 落非 ready 新 anchor → 新 wait 一次即稳。**未发现可复现的 spin 形态**。
5. **F2 exactly-once**：_wake_frontier_waiters 仅 set 成员操作、在 pop 之后（:2832-2843），不碰队列/写路径；test_drain_reentry 4 测钉住（含重复 drain 不重 wake）。
6. **并发**：树结构与 waiter 注册表全部仅在 scheduler 线程（ack drain 在 check_hicache_events 内）；storage 线程只推队列 + 置 storage_failure_reason（GIL 原子）→ 无新数据竞争。
7. **sanity 放宽边界**（:2272/2283/2289）：豁免面恰为 `(is_write_back ∧ persisted ∧ ¬full_dev)`；真 dead（无三层副本）仍断言；write_back 外 aux-host 无 Full 仍断言；parent 链规则未动。e12 3 测（真实 UnifiedTreeCore）钉住通过/两种失败边界。
8. **写穿/缓冲模式不可达**：write_through 路径无 backup_kv（evict_device_leaf :1262-1289）→ fallback 不可达；buffer mode 无 host 副本 → 无 L3 写 → storage_persisted 恒 False → hollow 不可达。

### 3.2 运行时证据（tester e17，未独立复跑）

96/96 K=8、OOM=0、idle sanity 通过、优雅退场、md5 4/4 与工作树一致。K=1 12/12。归因 100% 可解释。

## 4. summary（按严重性）

### MEDIUM

**M1. 部分写 ack 也晋升 persisted，hollow 据此释放最后完整副本**
- 位置：unified_radix_cache.py:2832-2843（_drain_backup 无 completed_tokens 校验）+ cache_controller.py:1353-1373（_page_backup 失败 break 后仍 ack）+ unified_radix_cache.py:1787（提交即 mark_storage_written，部分写永不再补）
- 问题：`page_set_func` 返回 False 时 operation 带部分 completed_tokens 照常 ack → advance_storage_persisted → 链永久残缺（storage_written 已置，gap fill 跳过）。hollow 在此 flag 上释放 device 层 → "L3 副本即持久备份"前提在部分写窗口内不成立。
- 风险：restore 有 all-or-nothing 校验（hybrid_discard :2172-2180）→ 无静默损坏，退化为 recompute；影响限于缓存效率与前提语义。inferred（依赖后端失败路径，未在测试/运行中观察到）。
- 建议：_drain_backup 中 `advance_storage_persisted` 前置 `operation.completed_tokens >= len(operation.host_indices)`（host_indices 即期望长度）；部分写时清除 storage_written 使下次 gap fill 重写。

**M2. 链晋升非追溯式：先于父 ack 的子节点永远停在 unpromoted**
- 位置：unified_tree_core.py:1965-1977（advance_storage_persisted 仅 ack 时看父）+ unified_radix_cache.py:2843（wake 仅在该节点自身 ack）
- 问题：子 ack 先于父 → 子不晋升；父后来 ack 不回溯晋升子 → (a) 该子锚上的 frontier waiter 永不 T12 wake（睡满 T13→recompute，恢复机会损失）；(b) 该链叶永久不符合 `is_storage_persisted` → hollow fallback 不触发，P2-1 死锁对该链仍可能复发。
- 现状缓解：单 backup 线程 FIFO + collect_storage_gap 祖先优先提交（cache_controller.py:1375-1387）→ 实际 ack 有序，目前为潜在缺口（若未来并行化写线程即触发）。
- 建议：advance_storage_persisted 晋升时递归晋升 `storage_written and not storage_persisted` 的子节点；或在 _wake_frontier_waiters 内从父回溯。

### LOW

**L1. hollow 路径不记 dropped-token 指标**：unified_radix_cache.py:823-832 hollow 分支未调 `_record_dropped_tokens`（:844-859），与 drop 路径语义同源（host 压力下无 host 副本释放 KV）但计数归类不同。建议 hollow 分支同样 `_record_dropped_tokens(tracker, freed_before_drop)`。

**L2. storage 降级后 persisted flag 不失效**：_handle_storage_failure（:3273-3300）后 L3 读已禁用，但 hollow fallback 不查 `storage_failure_reason`，可对不可读链 hollow。有界（recompute 覆盖），建议 fallback 加 `cc.storage_failure_reason is None` 门。

### 已验证无问题（不重复展开）
frontier 热循环闭合（4 形态逐一核查）、KeyError 兜底（node_exists + re-match 双保险）、F1/F2 ACK 语义、CHAIN_GAP、并发、buffer/write_through 模式不可达、sanity 边界不过度放宽、优雅退出顺序（stop_storage_threads 先于 pool destroy）。

## 5. followups

1. （建议，非阻塞）M1：_drain_backup 加 completed_tokens 完整性校验 + 部分写重试；配 1 测（partial ack 不晋升）。
2. （建议，非阻塞）M2：晋升追溯化或父 ack 时重检子链；配 1 测（父后 ack 触发子晋升 + wake）。
3. 测试缺口记录：hollow 后 restore 再填充（refill）路径无单元测（仅 stub 级 + K 级运行覆盖）；`evict_device_leaf_storage_backed` 在真实树/真实组件下的 frees/LRU/leaf-set 行为无直接单元测。如需门禁级保障，建议补 1 个真实树 hollow→insert 恢复测试。
4. RED→GREEN：coder e11/e12 报告声称的 RED 复现（violation 与 e16 现场逐字一致）与 GREEN（本机 100/100 + 远端 100/100）未由 reviewer 独立复跑（只读），以 tester e17 的 96/96 实跑为准。

## 6. open_issues

- 无阻塞项。M1/M2 为潜在缺口（当前单线程 FIFO + all-or-nothing 校验下均被兜底），不构成 REJECT。
- reviewer 未执行任何测试（只读边界）；运行时结论全部引用 tester/coder 报告证据。

## 结论

**APPROVE-WITH-NOTES** — 0 Critical / 0 High / 2 Medium（M1 部分写 ack、M2 非追溯晋升）/ 2 Low。e11 hollow-eviction fallback 在全部已核查路径上保持不变量（L3 副本存在性、leaf 集合、aux host 保留、CHAIN_GAP、F2 exactly-once、并发安全），gate/wake 一致闭合无热循环；e12 sanity 放宽边界恰为 hollow 合法态。测试配对充分（100 测 + 真实树构造 + 边界双向钉住）。M1/M2 建议在下轮顺手修复或登记为已知有界缺口。
