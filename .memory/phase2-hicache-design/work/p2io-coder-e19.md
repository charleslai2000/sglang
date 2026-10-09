# p2io-coder-e19 — 两个 P0 修复：①恢复 B_ep/B_fin 可测 ②writeback reserve 真实语义

## status
done

## artifacts
- `python/sglang/srt/mem_cache/pool_host/group.py` — 新增 `HostPoolGroup.alloc_writeback(...)`：
  D→H writeback 分配的 facade。这是 Fix 2 的**根因**——两个 host cache controller 的 `write()`
  用 `getattr(mem_pool_host, "alloc_writeback", mem_pool_host.alloc)` 选分配器，而 HiCache 栈的
  `mem_pool_host` 是 HostPoolGroup（无 `alloc_writeback` 方法）→ 静默回退到 reserve 封锁的
  `group.alloc(writeback=False)`。reserve 因此成为"永久禁用容量"，writeback 通道也消费不了它
  （解释 22.9K reserve 保留但 writeback 仍因只剩 46 tokens 失败）。新方法转发 `alloc(writeback=True)`。
- `python/sglang/srt/mem_cache/pool_host/base.py` — `alloc_writeback` 增加 **margin floor**：
  冻结语义 `D→H writeback occupancy ≤ C − margin`（writeback 可侵入 reserve，但不得耗尽 margin）。
  原实现无 margin 检查。
- `python/sglang/srt/mem_cache/pool_host/mamba.py` — `alloc_writeback` 同样加 margin floor
  （镜像 HostKVCache 语义），`__init__` 补 `_writeback_margin = 0`（e18 已加 reserve init）。
- `python/sglang/srt/managers/scheduler.py` — 恢复/新增 `restore_success` 事件：
  `pop_prefetch_loaded_tokens` > 0 的 admit 点（真实用恢复 KV 服务请求处）发
  `[P2A] evt=restore_success rid= n_tokens=`——issued→satisfied 服务时间戳等价物。
- `3090-dev/metrics/metric_compare.py` — 双口径支持 `restore_success` 为 finish/满足来源：
  守恒 invariants + `per_finish_spans`/episode 配对纳入 satisfied，新增 `[B_sat issued->satisfied]`
  统计行。e5 历史基线逐值复现（B_fin n=15 p50=1.158s / B_ep n=8 p50=1.146s）。
- `3090-dev/test_writeback_reserve_unit.py` — +2 测试（RED→GREEN）：
  `test_alloc_writeback_stops_at_margin`（writeback 可吃 reserve 但停在 margin）、
  `test_group_alloc_writeback_consumes_reserve`（控制器 `getattr` fallback 正确走 writeback 通道）。

## evidence
- **根因核查（用户要求的"修复前 writeback 是否真被 reserve 挡"）**：是。三个独立证据：
  1. `HostPoolGroup` 无 `alloc_writeback`（grep group.py 仅 alloc/resolve_host_transfers）；
     controller `write()` 的 `getattr(mem_pool_host, "alloc_writeback", mem_pool_host.alloc)`
     （cache_controller.py:892、hybrid_cache_controller.py:335）在组上回退到 reserve 封锁的 alloc。
  2. 内联复现：margin 注入后 `group.alloc_writeback` fallback 返回 None（RED 复现）。
  3. e7h 引擎日志因果链：`write_back: KV subtree dropped`=843（写回失败）、`extent_write`=135、
     `prefetch_revoke ... storage_hit=0`=330 → reserve 挡写回 → 链没落 L3 → 后续 restore 全 miss。
  结论：真 bug = writeback 通道被 reserve 挡。Z3/extent 核心零改动。
- **Fix 1（B_ep/B_fin 可测）核查**：prefetch_issued/prefetch_io_finished/prefetch_revoke 三事件
  在 HEAD 与工作树**都在且可达**（HEAD-vs-工作树事件逐字符 diff 一致；restore_ready 亦在，
  无 `enable_ready_horizon` 门控）。e7h 的 n=0 是**容量事实非 instrument 缺口**（330 全 revoke、
  storage_hit=0）——被 Fix 2 根因直接解释。补 add `restore_success` 为 issued→satisfied 等价物并按
  tester 建议让 metric_compare 双口径解析。
- **RED→GREEN（单元）**：`test_group_alloc_writeback_consumes_reserve` 与
  `test_alloc_writeback_stops_at_margin` 在删除该修复（动态 del HostPoolGroup.alloc_writeback /
  打补丁还原 alloc_writeback）时真实失败，修复后通过。
- **全门 327 OK**：`PYTHONPATH=<repo>/python python3 -m unittest test_storage_regression
  test_hicache_restore test_drain_reentry test_hicache_restore_scheduler_feed
  test_prefetch_budget_split_unit test_ready_horizon_unit test_ready_horizon_partition
  test_writeback_reserve_unit test_capacity_model_unit` → `Ran 327 tests in 0.177s OK`（基线 325 + 2 新）。
- py_compile 4 生产文件 + metric_compare → PY_COMPILE_OK exit=0。
- metric_compare 回归：e5 基线逐值复现；`/tmp/p2io-synth-restore-success.log` 合成日志解析出
  B_sat issued→satisfied 窗口。

## summary
两处 P0 修复完成。Fix 2 根因：writeback 分配经 `getattr(...,"alloc_writeback",...)` 在
HostPoolGroup（无此方法）上静默回退到 reserve 封锁的 alloc，reserve 成黑洞——已加 group facade +
margin floor（writeback cap C−margin，可侵入 reserve；normal 仍 cap C−reserve−margin；RH 不变）。
Fix 1：三事件本就在且可达，B_ep/B_fin 不可测是容量后果；补 `restore_success` issued→satisfied
等价物 + metric_compare 双口径解析。全门 327 绿。

## followups
- Integration（tester，orchestrator 调度）：① 12G 重测验证 B_ep/B_fin 可测（修复后应产生
  prefetch_io_finished/restore_success，守恒 True）；② restore_success 与 prefetch_io_finished
  双口径对比；③ writeback 确实吃 reserve 后 Z3≈0 目标。
- Performance：④ reserve 语义修复后 writeback 通道缓冲能力评估；⑤ 18G 是否仍需（本次无配置改动）。

## open_issues
- `test/registered/unit/mem_cache/test_mem_pool_host.py`（registered 门，非本 task 3090-dev 门）
  预存在失败：`MambaPoolHost.__new__` 跳过 `__init__`，e18 的 `alloc` line 260 读 `_writeback_reserve`
  报 AttributeError。**非我修改引入**（line 260 是 e18 的），超 scope 未改，列为观测项。
