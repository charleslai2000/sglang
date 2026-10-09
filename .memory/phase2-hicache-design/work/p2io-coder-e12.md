# P2IO coder e12 — P3 Ready Horizon v0 3.2 (ready_horizon 模块 + READY_HOST 水位维持)

## status

done

## artifacts

- `python/sglang/srt/managers/scheduler_components/ready_horizon.py` (new) — `ReadyHorizonPolicy` 纯函数协作类（frontier / ready_count M6 / ready_resident_tokens / staging_candidates / headroom_fits / refill_plan / should_refill）+ `ReadyHorizonView` / `RefillPlan`（msgspec.Struct）。领域逻辑全部在模块内，scheduler.py 只委托。
- `python/sglang/srt/managers/scheduler.py` — ① import ready_horizon；② `init_ready_horizon()`（构造期读三旋钮 + epoch 快照字段，`__init__` 在 init_schedule_policy 后接线）；③ `_ready_horizon_pass(running_batch)` 在 `_reconcile_restore_states()` 之后调用（`_get_new_batch_prefill_raw` :3965 处），内部：frontier views → epoch 签名比对（M3 事件驱动）→ `refill_plan` → 逐个 `_prefetch_kvcache(view.req)` 委托（speculative，demand_restore=False）→ 变化驱动 `[P3] evt=ready_pool` 日志 + 每 issue `[P3] evt=ready_stage`；④ helpers：`_ready_horizon_views`（M6 staged 标记，cache=peek_prefetch_loaded_tokens / buffer=staged_prefetch_tokens）、`_ready_horizon_epoch_sig`（frontier rids / ready_count / inflight_spec / prefetch_occupied / pool available / running_bs；刻意不含逐请求 state——被拒 WAIT 转变不得重新武装检查，M3 防轮询）、`_ready_host_headroom`（= available_size + ready_resident，即 size − working_set，M1 推导）。
- `python/sglang/srt/server_args.py` — 三旋钮（NS("memory")，hicache_prefetch_speculative_fraction 之后）：`ready_horizon_frontier_n=8` / `ready_host_watermark_low=2` / `ready_host_watermark_high=4`。
- `python/sglang/srt/mem_cache/unified_radix_cache.py` — `peek_prefetch_loaded_tokens(req_id)` 只读 helper（M6 驻留标记的非消费读；pop_prefetch_loaded_tokens 旁）。
- `3090-dev/test_ready_horizon_unit.py` (new, 32 tests) — 候选过滤（FRONTIER/BACKUP_PENDING/HOST_ALLOC/REVALIDATE/ongoing/无潜力 NONE/DEVICE_QUOTA host_hit>0 全排除；DEVICE_QUOTA(host_hit==0)/PREFETCH_BUDGET/NONE(eligible) 入选；预算满→空）、水位数学（low 触发/high 截断/单 pass 上限=high−ready）、headroom 可达性（2×20.9K=41,820 ≤ 42,784 成立，旧 inflight cap 21,392 否决——M1 验收）、headroom 不足静默不发、事件驱动（should_refill 三态 + pass 级 epoch 双跑不重复 issue）、M6 严格成员（READY+staged=0 不计）、禁驱逐（headroom 短fall 0 issue + 0 evict_host 调用）、空转（0 命令无变更）、off 模式 no-op、`[P3]` 日志格式、pass 委托经 `_prefetch_kvcache`。

## evidence

- `PYTHONPATH=<repo>/python` 强制本地树：`sglang.__file__` = `/home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache/python/sglang/__init__.py` ✓
- 全门（venv，unittest，绝对 PYTHONPATH）：test_storage_regression 94 OK / test_hicache_restore 69 OK / test_drain_reentry 30 OK / test_hicache_restore_scheduler_feed 7 OK / test_prefetch_budget_split_unit 24 OK / test_ready_horizon_unit 32 OK —— 256 全绿。派发单中的 "104" 与当前树任何文件计数都不符（storage_regression 现为 94），各套件均绿，未深究计数来源。
- RED→GREEN（重建法/等价法）：naive M6（state==READY）计数 2 vs 严格 1；naive 无事件轮询 True vs should_refill False；旧 inflight cap 否决 41,820 vs headroom 模型通过；naive 候选含 FRONTIER/BACKUP_PENDING vs 严格为空。
- pass 级端到端 smoke：真实 Scheduler 源码 + stub tree：`_ready_horizon_pass` 一次发 r1(NONE)/r2(PREFETCH_BUDGET) 均 speculative（demand_restore=False）、跳过 FRONTIER；同 epoch 第二跑 0 issue（M3）。

## summary

3.2 交付齐：ready_horizon 纯函数协作模块 + scheduler orchestration 接线（构造期 init、`_reconcile_restore_states` 后每 pass 调用、委托 `_prefetch_kvcache`、变化驱动 P3 日志）+ server_args 三旋钮 + 32 单测，全门 256 绿。M6 用 staged 标记（finalize 写入、准入 pop 消费的 `prefetch_loaded_tokens_by_reqid`）判定物理驻留，非简单 state==READY。M3 用 epoch 签名（资源计数器 + frontier 组成 + ready_count + running_bs，不含逐请求 state）实现事件驱动，5s safety reconciliation 兜底。M2 禁驱逐：策略/接线路径零 evict 调用，headroom 与预算不足均静默空 plan。headroom 语义：`host_headroom = available_size + ready_resident`（= pool.size − working_set），门 `ready + inflight ≤ headroom` ⟺ inflight ≤ 空闲页——READY 驻留不再被 0.5×pool inflight 预算否决（M1 验收 2×20.9K 成立）。

## followups

- 3.3 READY-first 调度（M4 partition_ready_first）未动；schedule_policy.py 零改动 ✓（本任务约束）。
- 同步 3090 + 冒烟（restore 套件 + 短 M4T）由 orchestrator 执行。
- M4T 完整验证（tester）：`[P3] ready_pool` steady ≥2、PREFETCH_BUDGET 驻留 p90 下降、speculative eviction 计数=0。
- 3.2 代码未 commit（工作树保留，与 3.1 一同由 orchestrator 处理）。

## open_issues

- 派发单全门计数 "104+69+30+7+94+24" 与实际（94+69+30+7+24+32）不符，套件全部绿，无失败。
- `_ready_horizon_epoch_sig` 的 GPU-slot 事件用 `len(running_batch.reqs)` 代理；运行期若发现事件过密/过稀，可调签名项（v0 已含全部五类事件代理项）。
- headroom 门代数上等价于 `inflight ≤ available`（READY 项抵消）——这是 M1 验收（2–4 READY 可达）的必然结果；alloc 失败是 M2 硬执行，门是软预检。tester 验证时若观察到"头 room 不足仍反复尝试"类问题，优先检查 alloc 失败路径而非此门。
- 3090 同步后 `hicache_host_memory_mode=buffer_only` 下 horizon 的 staged 标记走 `staged_prefetch_tokens`，未在真实 buffer 模式冒烟（cache 模式为 M4T 主路径）。
