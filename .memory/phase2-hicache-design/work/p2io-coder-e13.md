# p2io-coder-e13 — P3 Ready Horizon v0 3.3 (M4 READY-first 调度)

## status
done

## artifacts
- `python/sglang/srt/managers/scheduler_components/ready_horizon.py` — 新增 `ReadyHorizonPolicy.partition_ready_first()` + `_req_is_ready_resident()`（M4 稳定分区，显式优先级 > READY > 原 policy）+ 模块 docstring 追加 M4 说明。实现：按 `req.priority` 等值最大连续 run 分组（`priority=True` 时），run 内 READY（M6：state==READY && staged 标记>0）稳定前置，run 间保原序；`priority=False` 时整队列一个 run。返回新列表，输入不动。
- `python/sglang/srt/managers/scheduler.py` — `_get_new_batch_prefill_raw` 内 calc_priority（:4022）之后、TEST_RETRACT 块之后、PrefillAdder 构造（:4052）之前，插入一行门控调用：`if self.enable_ready_horizon: self.waiting_queue = self.ready_horizon.partition_ready_first(...)`（传 tree/buffer_mode/enable_priority_scheduling）。schedule_policy.py 零改动。
- `3090-dev/test_ready_horizon_partition.py` — 新单测 18 个（六组：StablePartition / ExplicitPriority / OffModeAndIdleNoop / PolicyOrderPreservation（跑真实 `SchedulePolicy._sort_by_priority_and_fcfs` / `_sort_by_longest_prefix`）/ HeadOfLineGuard / SchedulerGateWiring（跑真实 `_get_new_batch_prefill_raw` 门控））。

## evidence
- RED：临时改名 `partition_ready_first` 后跑新测试 → `Ran 18 tests ... FAILED (errors=18)`，全部 `AttributeError: 'ReadyHorizonPolicy' object has no attribute 'partition_ready_first'`（无分区代码时新测试失败）；恢复后 GREEN。
- 全门：`PYTHONPATH=<repo>/python python3 -m unittest discover -s 3090-dev -p 'test_*.py'` → `Ran 274 tests ... OK` exit=0。分文件计数（TestLoader）：storage_regression 94 / hicache_restore 69 / drain_reentry 30 / scheduler_feed 7 / prefetch_budget_split 24 / ready_horizon_unit 32 / ready_horizon_partition 18 = 274（94+69+30+7+24+32+18 与门一致）。独立复跑三次 exit=0。
- `python3 -m py_compile` 三个改动文件 OK；`import sglang; sglang.__file__` = `<repo>/python/sglang/__init__.py`（PYTHONPATH 强制本地树）。

## summary
M4 交付完成：调度链变为 calc_priority → partition_ready_first（稳定分区）→ PrefillAdder 准入。显式优先级判定：`enable_priority_scheduling` 开时以 `req.priority` 等值最大连续 run 为组（calc_priority 的排序键是 `priority * priority_sign`，sign 每次 pass 恒定，等值分组不受方向影响），READY 永不越过分组边界（两个方向都不越——run 边界双向成立），组内稳定前置；flag 关时 policy 根本不读 priority，整队列一个 run。off 门控在 scheduler 单点（`if self.enable_ready_horizon:`），零调用即逐字节等于今日。⑥ 验证：既有 continue 语义（ongoing/WAIT skip）不新增，分区只前置 READY。M6 标记复用 `_ready_horizon_views` 同一 lookup（buffer_only → staged_prefetch_tokens，否则 peek_prefetch_loaded_tokens）。

## followups
- 3090 同步（引擎文件 ready_horizon.py / scheduler.py + 测试，md5 双侧、.bak-v0 备份）由 orchestrator 执行。
- 3.4 集成验证：M4T 完整 run（READY_HORIZON=1）、B≤1.2s 硬门（R1：READY-first 若破坏 LPM 批处理则评估"READY 且前缀足够长才前置"变体，不在 v0）。

## open_issues
- 无。注意点（非问题）：LPM+priority 模式下列会按优先级 run 保守限制 READY 前置（run 多单例），这是"READY 不得越过高优先级请求"在 policy 不按优先级排序时的保守正确解读，符合 M4 用户定案方向。
