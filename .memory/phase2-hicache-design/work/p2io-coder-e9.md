# P2-IO 性能收口 P0 — e9（修正版 R1 target-frontier park + 修正版 R2 DEMAND_RESTORE ticket）

## 1. status

done

按协调人 correction #3 执行：弃 span-overlap 方案，实现修正版 R1（三 frontier：
`durable_frontier` / `backup_target_frontier` / `requested_frontier`，park 条件双成立，
wake 条件 `durable >= requested`，counter-example 不 park）与修正版 R2（DEMAND_RESTORE
ticket：仅豁免 speculative PREFETCH_BUDGET，独立有界并发，DEVICE_QUOTA 语义不变）。
本机全门 104+64+29+7+94 = 298 全绿；RED→GREEN 已证明（e8 surface 重建 + counter-example
语义对比）。3090 同步与实测属 orchestrator 职责，本 epoch 未动。

## 2. artifacts

| 文件 | 改动 | 为什么 |
|---|---|---|
| `python/sglang/srt/managers/scheduler_components/hicache_restore.py` | `backup_wait_applies` 改为 frontier 签名 `(storage_hit_pages, requested_pages, *, durable_frontier, backup_target_frontier)`；新增 `backup_wake_applies(durable_frontier, requested_pages)`（wake 条件）、`DEMAND_RESTORE_MAX_INFLIGHT = 4`、`demand_restore_available(inflight)`（有界并发票池谓词）；`capacity_wake_applies` docstring 同步为 frontier 谓词 | 修正版 R1/R2 的纯逻辑：park 仅在"管道目标覆盖请求终点"时发生；wake 保证一次 re-lookup 全命中；票池独立限流 |
| `python/sglang/srt/mem_cache/unified_cache/unified_tree_core.py` + `unified_tree_core_interface.py` | 删除 e8 的 `is_ancestor_or_self`；新增 `page_block_in_request(node_id, pos, requested_pages) -> Optional[tuple[int,int]]`（按 hash 位置连续匹配求节点在请求跨度内的块，首个 hash 不在请求链上 → None）与 `persisted_chain_frontier(node_id, pos, requested_pages) -> int`（沿 persisted 前缀最深块尾；未提升子节点不进入，删除节点返回 0） | durable frontier 的来源：树状态（acked+父链连续的写推进前沿）就是协调人定义的 durable_frontier |
| `python/sglang/srt/mem_cache/unified_radix_cache.py` | 删除 `chain_backup_in_flight`；新增 `chain_backup_frontiers(anchor, requested_pages, page_hashes) -> (durable, target)`（durable=persisted_chain_frontier，target=max(durable, 在途 backup 写块尾)；anchor 已删 → (requested, 0) 防 park）、`backup_wait_ready(req_id)`（wake 谓词：span 存续 + durable 越过终点；anchor 已删 self-heal True）、`demand_restore_inflight()`；新增 `_backup_wait_spans`（park 时存 `(anchor, requested_pages, page_hashes)`，`discard_frontier_waiter` 时 pop——T12 hold 路径先 gate 后 discard，span 保留）；新增 `_demand_restore_rids`（demand issue 时 add，四个 ongoing_prefetch 移除点 discard）；`prefetch_from_storage(..., demand_restore=False)` 仅跳过 rate check；park 统一走 `_backup_park_applies`（两处：revoke 分类 + drain 阈值上预检） | 修正版 R1/R2 的树侧实现：target 从在途写块推导（无需扩展记录——ongoing_backup 的 node_id + 树 hash 足够）；ticket 生命周期与 prefetch 一致 |
| `python/sglang/srt/managers/scheduler.py` | `_prefetch_kvcache(req, *, demand_restore=False)` 透传；新增 `_restore_backup_wake_ready(req)`（backup_wait_ready AND demand_restore_available）；step3（T12）对 BACKUP_PENDING 先 gate 后 discard（不 ready → continue 持 park，span 不丢），re-issue 带 demand 标志；step4（T11）在 `_apply_restore_event` 前捕获 `was_backup_pending`，re-issue 带 demand 标志；`_restore_wait_capacity_fits` 的 BACKUP_PENDING 分支改为 `_restore_backup_wake_ready` | 修正版 R2 的调度侧：wake 后的一次性 re-issue 持票绕过 speculative PREFETCH_BUDGET；T13/quota-deny/cancellation 语义不变 |
| `3090-dev/test_hicache_restore.py` | 54→64：BackupWaitAppliesTests 重写为 frontier 语义（含协调人 counter-example：durable=[0..6000)、missing=[6000..20000)、inflight 只到 [6000..7000) → target=7000 < requested=20000 → 不 park；无在途管道 target==durable 不 park；durable 已过终点不 park）；新增 BackupWakeAppliesTests（4）、DemandRestoreTicketTests（4，含票池满/超界） | R1 纯谓词 + R2 票池边界守卫 |
| `3090-dev/test_drain_reentry.py` | 20→29：`_FakeTreeCore` 以 `node_hashes` 建模每节点页 hash + `page_block_in_request`/`persisted_chain_frontier` 模型（替换 is_ancestor_or_self）；`_make_cache` 补 page_size/_backup_wait_spans/_demand_restore_rids/prefetch_loaded_tokens_by_reqid；`_FakeController.terminate_prefetch`；BackupPendingRevokeTests 重写（锚 persisted、hash 链），新增 counter-example（3 节点链 inflight 只到 70）、BackupWaitReadyTests（5：frontier 未过不醒/ack drain 过醒/锚删 self-heal/未知 rid/ discard 终 park）、DemandRestoreTicketTests（3：初始 0/revoke 释放/abort 释放） | R1 wake 条件 + R2 ticket 释放路径的缓存级守卫 |
| `3090-dev/test_hicache_restore_scheduler_feed.py` | 5→7：wake 谓词改为 backup_wait_ready/demand_restore_inflight 双条件（frontier 未过 False、越过 True、票池满 False=thundering herd 守卫）；新增 step4 端到端（`_reconcile_restore_states` 真实走一遍：BACKUP_PENDING wake → `_prefetch_kvcache(demand_restore=True)` spy） | R2 调度接线守卫：wake 后绝不落回 speculative PREFETCH_BUDGET |
| `3090-dev/test_storage_regression.py` | fake tree core 的 is_ancestor_or_self lambda 换为 page_block_in_request/persisted_chain_frontier 双 lambda；_make_cache 补新字段 | 兼容新分类调用（94 保持绿） |

未动（前 epoch 面）：cache_controller.py（e6 extent 接线）、hicache_storage.py（e5）、
extent_file_backend.py（e7 IOV_MAX）、test_extent_file_backend_unit.py（e7）。本轮未触碰
extent 后端 / allocator / cache_controller，符合协调人"不在本任务面"约束。

## 3. evidence

RED（e9 新测试对 e8 语义失败）：

- e8 surface 重建（e8 文件不在磁盘——未提交、已被 e9 覆盖；按 e8 逐字谓词 + 当前模块
  减 e9 新增面重建，e8→e9 其余纯逻辑零差异，重建对被测面精确）：
  `/tmp/e9-red/e8_surface.py`、`/tmp/e9-red/run_red.py`
- `python3 /tmp/e9-red/run_red.py` → `Ran 14 tests; FAILED (errors=14)`：
  14/14 全失败——`BackupWaitAppliesTests` 6 项 `TypeError: backup_wait_applies() got an
  unexpected keyword argument 'durable_frontier'`（e8 签名无 frontier）；`BackupWakeAppliesTests`
  4 项 + `DemandRestoreTicketTests` 4 项 `NameError: ... not defined`（e8 模块无
  backup_wake_applies / demand_restore_available / DEMAND_RESTORE_MAX_INFLIGHT）
- counter-example 语义 RED→GREEN（venv python 直测）：
  `e8 parks=True (WRONG), e9 parks=False (correct)`（e8 只判"部分命中+任意在途写"即 park；
  修正版要求管道目标覆盖请求终点）→ `semantic RED->GREEN for the counter-example: OK`

GREEN（本机 venv = /home/charles/sglang-venv，torch 2.13.0+cu129；PYTHONPATH=python
强制本地树，e8 已验证 sglang.__file__ 指向本地）：

```
$ PYTHONPATH=python:test .../python -m unittest test_extent_file_backend_unit test_hicache_file_lru_unit
  -> Ran 104 tests in 0.956s OK
$ PYTHONPATH=python:3090-dev .../python -m unittest 3090-dev.test_hicache_restore
  -> Ran 64 tests OK            (54 + 10 新增)
$ PYTHONPATH=python:3090-dev .../python -m unittest 3090-dev.test_drain_reentry
  -> Ran 29 tests OK            (20 + 9 新增)
$ PYTHONPATH=python:3090-dev .../python -m unittest 3090-dev.test_hicache_restore_scheduler_feed
  -> Ran 7 tests OK             (5 + 2 新增)
$ PYTHONPATH=python:3090-dev .../python -m unittest 3090-dev.test_storage_regression
  -> Ran 94 tests OK
$ .../python -m py_compile 9 个改动文件 -> COMPILE-OK
```

预存在失败（非本 epoch 引入，e8 已记录、HEAD 复现验证）：test_unified_radix_cache_unittest
import-path quirk + GPU/MagicMock 错误（`'<=' not supported between instances of 'MagicMock'
and 'int'`、`ValueError: Not enough host memory...`），本轮复跑失败模式与 e8 记录一致。
`git status --porcelain` 14 项（5 源文件 + 4 测试文件 + 3 前 epoch 文件 + 2 untracked）。

## 4. summary

e4 净负结果的两根因按协调人修正版收口：(1) R1——park 谓词从"部分命中+在途写"改为
frontier 语义：只有 backup 管道目标覆盖请求终点（`backup_target_frontier >= requested`）
且 durable 前沿仍落后时才 park；wake 条件 `durable >= requested` 保证 wake → 一次
re-lookup → 全命中 → 一次 restore。counter-example（在途写只到 7000 < requested 20000）
明确不 park，走现有部分恢复/recompute 路径。目标前沿从 `ongoing_backup` 在途写的
请求内块直接推导，无需扩展记录。(2) R2——wake 的 re-issue 改为 DEMAND_RESTORE ticket：
只豁免 speculative PREFETCH_BUDGET（issue 侧 rate check 跳过；drain 侧 buffer-mode-only
rate gate 本就不适用 cache 模式），Host staging、promotion admission、IO 并发、
cancellation 全部照旧；票池 4 独立有界（wake 批次防惊群），ticket 随 prefetch 生命周期
（4 个移除点释放）。调试中自审发现并修复两处真实缺陷：tree-core frontier 方法对已删
节点的 KeyError 崩溃风险（node_exists 守卫）；锚已删时 park 会形成"park→wake→re-issue"
每 pass 循环（chain_backup_frontiers 返回 (requested, 0) 防 park，与 e8 行为一致）。

## 5. followups

- 3090 实测派发（orchestrator）：同步 5 源文件 + 4 测试文件到 3090 树；复测 M4T 配置，
  判据按协调人硬性六条：① park→full-hit >90%；② park 后 partial IO ≈0；③ 每 park rid
  wake ≤1 为常态；④ BACKUP_PENDING wake 后不再出现 PREFETCH_BUDGET；⑤ BACKUP_PENDING
  p95 保持秒级；⑥ 全链 p50 <1s、p90 无数十秒尾巴
- 本机可加的性能微基准（可选）：`p2io_batch_size_microbench.py` 风格的 park→wake 全流程
  计数（frontier 语义下 park 数应显著少于 e4 的 72，wake 后 full-hit 比例应显著高于 18.6%）
- T6 device-full wait 本身仍是尾源（Ready Horizon 域，范围外，e8 已记录）

## 6. open_issues

- 恢复锚（storage_restored 而非 persisted）的子链在写 ACK 后不推进 persisted 前沿的
  角落：该情形 wake 不触发，park 由 T13 兜底（安全、有界）。e8 的"写完成即醒"对此类
  更快。属持久化推进语义的既有属性，未改（协调人允许面：state machine + drain + tree
  core 记录；本次仅新增 frontier 读取方法）。
- `_restore_wait_capacity_fits` 的 BACKUP_PENDING 分支返回 `_restore_backup_wake_ready`，
  不重复 device-charge/promotion-budget 检查（与 e8 相同）：wake 后准入门仍是权威，
  过度宽松只多一次 re-lookup。
- 预存在失败（见 evidence）待 tester/orchestrator 排期。
