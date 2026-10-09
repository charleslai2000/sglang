# p2io-coder-e18 — P3 Ready Horizon capacity model refactor（token/bytes 容量核算：user adjudication + e7g accounting）

## status
done

## artifacts
- `python/sglang/srt/managers/scheduler_components/ready_horizon.py` — capacity-model RH policy：
  - 类默认 `token_mode: bool = False`（legacy count fallback，直接策略构造保持 count 语义）；调度器经 `init_ready_horizon` 用新 server_args 启用 token 语义。
  - `_issue_budget(ready_count, ready_tokens)` 签名改（count 模式仍 `max(0, watermark_high - ready_count)`）；`refill_plan` call site 改 `budget = self._issue_budget(ready, tokens)`。
  - `describe_watermarks` 恒 `f"{low}/{high}"`（不再 append "count"，保持现有 `watermark=[2/4]` 日志）。
- `python/sglang/srt/managers/scheduler.py` — 容量核算接线：
  - `init_ready_horizon`（1357-1406）：`ready_horizon_reserve_tokens = hicache_writeback_reserve_state_tokens or state_p95`；`ready_horizon_margin_tokens = ready_horizon_margin_state_tokens or 0`；count 模式 iff 两个 `*_count` arg 都设（`ready_horizon_token_mode=False`，watermark=count 值）；否则 token 模式（`watermark_low = low if state_p95==0 else state_p95`，`watermark_high = high if state_p95==0 else 2*state_p95`）。
  - `_ready_reserve_floor_tokens(cc)`（3516-3543）：token 模式 → `reserve_tokens + margin_tokens`；count 模式 → pool writeback_reserve + GB margin 转 token。
  - `_hicache_capacity_stats(views, cc)`（3545-3614）：9-key dict（下表）。`usable_tokens = kv_pool - reserve - margin`。
  - `_ready_horizon_pass`（3320-3425）：refill 带 `reserve_floor=self._ready_reserve_floor_tokens(cc)`；`[P3] evt=ready_stage` 与 `evt=ready_pool size=%d tokens=%d watermark=[%s]` 日志保留。
- `python/sglang/srt/observability/metrics_collector.py` — SchedulerStats 9 新字段 + 9 `sglang:hicache_*` gauge（`if self.enable_hierarchical_cache:` 门内创建@664+ / 记录@1503-1538）。
- `python/sglang/srt/managers/scheduler_components/metrics_reporter.py` — `_log_hicache_stats`（1085）：既有 host_total/used + 新 P3 block（1098-1130）：`hasattr(ready_horizon)` 守卫建 frontier/views → `_hicache_capacity_stats(views, cc)` 于 try/except + `logger.exception` → 填 9 字段。
- `python/sglang/srt/mem_cache/hybrid_cache/hybrid_pool_assembler.py` — `attach_hybrid_pool_to_unified_cache`（1729+）：`state_reserve_tokens → reserve_bytes = int(state_reserve_tokens * anchor.size_per_token)` 否则 GB fallback；`set_writeback_reserve_bytes`；margin 经 `set_writeback_reserve_margin_bytes`；每 pool `logger.info("P3 write-back reserve/margin as %s of %s host pool: reserve=%.1f%% margin=%.1f%%")`。
- `python/sglang/srt/server_args.py` — 新 token knobs（末参值表）+ 语义迁移注释：
  - `ready_host_watermark_low = 43_513`（1×State_p95）、`high = 87_026`（2×State_p95）。
  - `ready_host_watermark_low_count`/`high_count`（Optional[int]，None；同时设才进 count 模式）。
  - `ready_horizon_margin_state_tokens`（Optional[int]，None）、`hicache_writeback_reserve_state_tokens`（Optional[int]，None）、`ready_horizon_state_p95_tokens`（默认 0）。
  - GB knob（`hicache_writeback_reserve_gb`/`ready_horizon_safety_margin_gb`）标记 LEGACY：token 值未设时才生效（0 禁用）。
- `3090-dev/test_capacity_model_unit.py`（新告，14 tests）— 六守卫类：
  - `UsableTokensTests`：`KV_usable = pool - reserve - margin` 正确、per-pool（kv/mamba）与 aggregate；`working = used - ready_resident`；`spec_inflight`；`ready_state_max`；mamba 独立 usable。
  - `CapacityAdmissionTests`：`working + ready + spec > usable` → RH stage 全 NO_HEADROOM decline；under-usable → 全 admit（refill headroom + reserve_floor 门）。
  - `TokenWatermarkTests`：同 token watermark 跨 state length 一致（count 模式 24K vs 87K 同 count=2 都触发——adjudication #1 的激励场景；token 模式小 state 48K 触发 / 大 state 174K 不触发，state size 可见）。
  - `ReserveTokenSemanticsTests`：≥1-state reserve 不被动用——reserve=1 state 时 usable 仍容 working + 2 READY。
  - `SixGaugeSmokeTests`：容量 stats dict 九 key 全 int。
  - `LegacyGbCompatTests`：count 模式走 pool.writeback_reserve + GB margin；token 模式用 state_tokens 无视 GB knob。
- `3090-dev/test_ready_horizon_unit.py`（既有，2 处改）— zero-regression：`_pass_scheduler` server_args SimpleNamespace 显式设 `*_count` + `*_state_tokens=None` + `state_p95_tokens=0`（legacy count 显式 opt-in 兼容路径）；`test_ready_pool_log_on_change` 断言改 `watermark=[2/4]`。

## evidence
- RED→GREEN（新告）：14 新测试初跑 `FAILED (failures=5, errors=2)` → 修 7 处后 `OK`。逐次真实失败→修复（test_usable 占位行、mamba fake pool 缺 `can_use_write_back_jit=True`、CapacityAdmission watermark 1/2 tok 预算封顶无 decline、TokenWatermark 缺 NONE 候选、CHAIN_TOKENS>pool 致 working<0、harness POOL_LOGICAL=66）。
- 全门 RED→GREEN：full gate 初跑 `failures=10, errors=12`（325 tests，其中 15 在 test_ready_horizon_unit：`token_mode=True` 类默认破坏 count-era 测试 + pass-harness 缺新 server_args）→ 设计决策修复（类默认回 `token_mode=False` legacy fallback + 既有测试显式 `*_count` opt-in）→ 全绿。
- 全门最终：`cd 3090-dev && PYTHONPATH=<repo>/python python3 -m unittest test_storage_regression test_hicache_restore test_drain_reentry test_hicache_restore_scheduler_feed test_prefetch_budget_split_unit test_ready_horizon_unit test_ready_horizon_partition test_writeback_reserve_unit test_capacity_model_unit` → `Ran 325 tests in 0.116s OK` exit=0（GATE_RC=0，全文存 `.memory/phase2-hicache-design/work/e18-gate.txt`）。
- 单测复跑：`python -m unittest test_capacity_model_unit` → `Ran 14 tests in 0.006s OK` exit=0。
- `python3 -m py_compile` 9 个改动生产文件 → `PY_COMPILE_OK` exit=0。
- on-disk 确认：token_mode 类默认 line 173；`init_ready_horizon` token 选择 1368-1394；server_args 末参值（grep 逐行比对 vs 上表）；9 gauge 名 `sglang:hicache_*` + 9 stats 字段（metrics_collector grep）。metrics pipe 连贯：gauge 创建+记录同在 `enable_hierarchical_cache` 门内，reporter 填 9 字段含 try/except。
- anti-pattern 扫描 clean：无新增 TODO/FIXME/print；`[P3]` 埋点 intact（scheduler.py 2 evt 处、extent_file_backend.py 1、unified_radix_cache.py 1）。base.py `set_writeback_reserve_margin_bytes` 正确写 `self._writeback_margin`（前 summary 疑点 on-disk 不存在，无需修复）。

## summary
P3 Ready Horizon 容量模型重构完成：RH 由 request-count 驱动的 READY_HOST 池维护改为 **KV-host TOKEN 容量核算**。核心模型 `KV_usable = KV_pool - writeback_reserve - margin`，RH 仅当 `working + ready + inflight_spec <= KV_usable` 才 admit；write-back reserve 语义从固定 GB 份额（22%/0.75GB）改为"至少一个目标写回态的 KV tokens"（runtime 按 state size 计算）。九 gauge 以 token 空间发布容量模型（无 GB 猜测）。迁移双轨：token 语义为生产默认（Watermark 1/2×State_p95），count 语义经显式 `*_count` args 保留（legacy 兼容），GB knobs 标记 LEGACY 仅在 token 值未设时生效。既有 311 测试零回归 + 14 新测试全绿（325 OK）。

## followups（整合/性能要求 → orchestrator 调度）
- 3090 同步（ready_horizon.py / scheduler.py / metrics_collector.py / metrics_reporter.py / hybrid_pool_assembler.py / server_args.py + 测试，md5 双侧、.bak 备份）由 orchestrator 执行（非本 task）。
- Integration（tester）：① synthetic `working + ready + spec > usable` 负载下 RH stage 拒绝行为在真实引擎；② 混合 state-length（p50/p90/max）下 token watermark 一致触发 + `[P3] evt=ready_pool tokens=` 观测；③ 实时引擎上六 gauge 发布 smoke（metrics gather log 含九 `sglang:hicache_*` 值）。
- Performance：④ 12G/0.75G/0.3G（新模型 = `--ready-horizon-state-p95-tokens 43513` + 1×State_p95 reserve + margin 相当）回归对比 e7g 的 8G config（kv host usable 13,447→102,730 tok）；⑤ RH 在 token 门下的 refill 频率与 issue 量对比旧 count 门。

## open_issues
- `ready_horizon_state_p95_tokens` 默认 0：State_p95 未测量时，token watermark 回落为配置的裸 `ready_host_watermark_low/high`（=43,513/87,026 仍是 token），reserve 经 `or state_p95` 落到 0——配合 GB knob 生效。无阻塞。
- 每 pool reserve % drift（e7g followup 2）：构造期已逐 pool log `reserve/margin as % of host pool`；运行时容量核算以 state-token 绝对值为准（track 的是状态 size 而非 pool 份额），不算 drift-blocker，列为观测项。
- `init_ready_horizon` 对 `*_count` 半设（只设一个）不报错、静默进 token 模式（arg help 已注明 mutually exclusive），保守但不阻塞。