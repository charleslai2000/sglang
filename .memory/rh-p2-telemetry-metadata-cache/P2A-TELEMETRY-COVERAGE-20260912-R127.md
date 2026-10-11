# P2-A Telemetry Coverage Scout — R127

- Task ID: `P2A-SCOPE`
- Invocation: `ses-p2a-telemetry-coverage-20260912-r127`
- Epoch: `2026-09-12`
- Role: `scout` (private, read-only)
- Status: **done**
- ENTRY: `ACCEPT`

Claim boundary: read-only telemetry-coverage inventory. No product/test/gate/storage/git
change; no server run; no product import; no new IDs created. This report states what is
observable from telemetry the running product already emits, and what marks are absent. It
does not design or implement the missing probe.

Repo bound: `3rdparty/sglang-3090-24g-opt`
Branch `3060-12g-qwen35-4b`, HEAD `4f41f5bab562b99562f30c67540eb05344d13637`
(dirty worktree, 13 modified tracked files + untracked `.memory/`).
Relevant source hashes:

| file | sha256 |
|---|---|
| `python/sglang/srt/disaggregation/decode_hicache_mixin.py` | `9c7775030f97c542024e48da95af001a392f52ee589658a38635ea0303f171b2` |
| `python/sglang/srt/mem_cache/unified_radix_cache.py` | `5d3db1528638dd1c593b9cd62fc1b380d278cac4cc1b4e1319e6bf89c0ac375b` |
| `python/sglang/srt/managers/cache_controller.py` | `a41e623a2d6e462720d6584af992da290ba54e0cb3766df794117b87678b656f` |
| `python/sglang/srt/mem_cache/hybrid_cache/hybrid_cache_controller.py` | `a71acb88d886af1b5ba888828b55aae57156ceb43cd37ef7480da6ffcad06669` |
| `python/sglang/srt/managers/scheduler.py` | `892efc25e2a9ef7c5ebb4afa09cf6914182b1467981d14cd76c53eea5d8de9d7` |
| `python/sglang/srt/observability/req_time_stats.py` | `3a32af2aafbb95366a12aa6b01fa8d0c1b973f0188019ea623c69c7d285ed46f` |
| `python/sglang/srt/observability/metrics_collector.py` | `fc089c8cf08c4c819d0a606e161bcc567df0e466f98c4f4d0d4e61c7ee265063` |
| `python/sglang/srt/mem_cache/hicache_storage.py` | `7c5c7331eda1ded25a25bb5d9938aa76311651b16025f5b8743a17318ff1d1d7` |

(`scheduler.py` hash equals the P1-closure fix hash recorded in `context.md:43-44`.)

## Scope of inspection and search limits

Read-only inspection of product source under
`python/sglang/srt/managers/`, `mem_cache/`, `disaggregation/`, `observability/`, plus the
canonical memory tree `.memory/phase2-hicache-design/` and the coordination worktree
`3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/`.

Existing captured runtime evidence read (no new run):

- `/mnt/data/neuron/sglang-3090-r112-20260911/sglang-server-r112.log` (3,222,484 lines)
- `/mnt/data/neuron/sglang-3090-r112-20260911/sglang-server-r124.log` (6,736,100 lines)
- `/tmp/t38c-probe.log` (58,265 lines; the live `pc_*` / `[B15]` / durability probe sink)
- `/mnt/data/neuron/sglang-3090-r112-20260911/launch-r112.sh` (frozen R112 profile)

Not inspected: any host other than the local read of those files; no server process was
touched; the 3060 remote host was not contacted. Line numbers in the frozen logs are not
cited because the logs are append-across-runs; citations are to source and to sampled
record shapes.

## Authoritative P2-A contract (exact text)

The detailed P2-A definitions live in the coordination worktree, not in the `opt` tree:

`/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/plan.md`

- **P2-A1** `:63-71`:

  > `goal`: 用真实 multi-turn agent/session workload 测量 B 入队到 A 完成之间可供 L3→L2
  > staging 使用的 lead time，验证 queue-only RH 的实际时间窗口。
  > `deliverable`: raw + summarized lead-time dataset，含 monotonic timestamps、agent/session
  > IDs、B enqueue、A final compute/completion、B stage start/finish、Host-ready、admission、
  > queue depth、workload/config provenance 和 deadline/miss 分类。
  > `acceptance`: 报告分布和逐条 trace，至少拆出 `B_enqueue -> A_finished` lead、L3→L2 stage
  > duration、Host-ready delay、admission delay、queue-only miss/deadline；声明 workload/window
  > 和复现配置。**不得从 client wall/e2e 推断 lead time**，也不输出未经数据支持的 queue-policy
  > verdict。

- **P2-A2** `:73-81`:

  > `goal`: 在任何 async redesign 前，测量 decode-side `query_storage_hit_length` 是否位于
  > task-switch critical path，并分解其实际等待来源。
  > `deliverable`: timing-audit report，含 caller/path attribution、enter/exit duration、
  > backend wait、lock wait、syscall time、future/event wait、sample count、p50/p95/p99/max、
  > source/profile hashes 和缺失字段。
  > `resource_constraints`: 若已有 telemetry 不足，需要单独 profiling/live authorization；使用
  > **observation-only probe**，独占并串行使用单 3060 service/GPU/storage。**不得把约 38.3s
  > restore e2e 当作该函数的 isolated timing。**
  > `acceptance`: 每个样本有 enter/exit 边界并能分别归因 backend、lock、syscall、future/event
  > wait；按既定解释带给出结论：**p99 < 100µs 可忽略，100µs–1ms 仅观察，≥1ms 或 disk
  > syscall/future wait 为 optimization candidate，约 10ms 为 clear blocker**。无法分辨组件时
  > 记录 gap，禁止未经新决策和授权 redesign。

`opt plan.md:35-37`: "P2-A — lead-time and storage-query measurement. Measure lead time and
storage-query behavior. `query_storage_hit_length` is measurement-only at this stage; do not
change it."

`opt plan.md:59-63`: scenario-specific TTFT P95 `<1s` for (a) L1 hit, (b) an L2 restore,
(c) an RH-staged-to-Host-ready L3 request; cold L3 excluded.

`ledger.md:43-46` (user ruling): "The P2 scorecard must include cache-induced idle and split
timing into `restore_wait/queue_wait/compute/decode`." / "`query_storage_hit_length` is
measurement-only for now."

R65 readiness rows (`.memory/.../work/P2P3Q-READINESS-20260911-R65.md`):

- `:66` P2-A1 = **[PARTIAL]**: "No `B_enqueue`/`A_final_compute` monotonic marks; no
  queue-depth, stage start/finish, Host-ready, or admission-delay fields."
- `:67` P2-A2 = **[MISSING timing]**: "No enter/exit instrumentation on this function; no
  component decomposition. The only nearby histogram is a *whole* `load_back` timer
  (`metrics_collector.py:2236-2307`), which the contract explicitly forbids treating as
  isolated query time (`plan.md:78`)."

R71 scorecard analysis (`.memory/.../work/P2-B0-CONTRACT-20260911-R71.md:154-230`) freezes the
`cache-induced idle` semantic as "GPU idle while runnable work exists because cache/state is
not ready", requires (i) a runnable-but-not-computable classifier and (ii) a GPU busy/idle
timeline "at a resolution fine enough to locate idle intervals (5 s `nvidia-smi` sampling is
*not* sufficient)" (`:188-199`), and records all of `restore_wait/queue_wait/compute` as
**not computable** from current telemetry (`:207-210`).

## Per-quantity findings

Clock/join key legend:

- **mono-ns** = `time.monotonic_ns()` in the same process monotonic domain.
- **mono-f** = `time.perf_counter()` float seconds, same process monotonic domain.
- **wall-ms / wall-s** = `time.time()` derived; not subtractable from mono values.
- **join** = fields available to correlate a record to a request/attempt.

### Quantity 1 — `queued -> switch` lead time (per request: enqueue → switch-in)

**Verdict: PARTIALLY** (derived per-request queue duration is obtainable through an existing
opt-in; the raw monotonic marks and the cross-request lead are not emitted).

Existing marks:

- **Enqueue/queue-entry mark (internal, mono-f, per request)**:
  `SchedulerReqTimeStats.wait_queue_entry_time` is set by
  `req.time_stats.set_wait_queue_entry_time()` in `_add_request_to_queue`
  (`scheduler.py:6057-6072`, NULL mode `:6072`; disagg decode `decode.py:2207`;
  disagg prefill `prefill.py:449,459,1352`). Definition `req_time_stats.py:738-757`
  (`time.perf_counter()`).
- **Switch-in / forward-entry mark (internal, mono-f, per request)**:
  `SchedulerReqTimeStats.forward_entry_time` set via
  `set_time_batch(can_run_list, "set_forward_entry_time")` (`scheduler.py:6934`;
  decode path `decode.py:2639`). Definition `req_time_stats.py:759-791`.
- **Derived duration already exists**:
  `get_queueing_time()` = `forward_entry_time - wait_queue_entry_time`
  (`req_time_stats.py:1047-1048`), exposed as `queue_time` in
  `convert_to_output_meta_info()` (`req_time_stats.py:1167-1182`) and as
  `queue_duration=` in `convert_to_duration()` (`:1050-1064`).
- **Existing per-request emission path (opt-in, no new code)**: on request finish,
  `output_streamer.py:232-238` (`_maybe_log_time_stats`) calls `req.log_time_stats()`
  (`schedule_batch.py:1882-1902`) when `enable_request_time_stats_logging` is on
  (`server_args.py:1613-1615`, **default False**). The line carries
  `ReqTimeStats(rid=…, type=…): queue_duration=…, forward_duration=…, entry_time=<wallclock>`.
  The `queue_time`/`forward_entry_time` (wallclock-converted) are also emitted in response
  `meta_info` when `enable_metrics` is on (`tokenizer_manager.py:2214-2217,2445-2460`).
- **Switch-in monotonic mark (emitted, mono-ns)**:
  `[P3] ts_ns=… evt=admission.v2 schema=rh_admission.v2 rid=… admission_monotonic_ns=%d`
  (`scheduler.py:6819-6836`).
- **Per-pass admission trace (emitted, wall-ms, debug-gated)**: 
  `[P2A] ts_ms=… evt=admission rid=… pos=%d qlen=%d running_bs=%d can_run=%d`
  (`scheduler.py:6736`), gate `_p2a_trace` requires `/tmp/t38c-on` (`scheduler.py:402-404`).
  It carries queue position/depth but **no matching enqueue timestamp**.
- **Enqueue sequence, not a time**: `hicache_request_enqueue_seq` is assigned at
  `_add_request_to_queue` (`scheduler.py:6063-6066`; field `schedule_batch.py:1056`) and
  emitted by `[P3] rh_preadmission_decision … request_enqueue_seq=` (`scheduler.py:4699-4710`)
  — an integer ordering key only.

Runtime evidence (R112 profile): `enable_request_time_stats_logging=False` and
`enable_metrics=False` in `launch-r112.sh`, so **no per-request `queue_duration` line exists**
in the captured logs. `[P2A] evt=admission` *is* present heavily because `/tmp/t38c-on`
existed (3,213,667 occurrences in `sglang-server-r112.log`); sample:
`[P2A] ts_ms=1789135200038 evt=admission rid=ea112b3a… pos=0 qlen=1 running_bs=0 can_run=0`.

Missing marks for the P2-A1 definition (monotonic timestamps + `B_enqueue -> A_finished` lead):

1. an **emitted, mono-ns enqueue timestamp per rid** (the internal `wait_queue_entry_time` is
   never logged raw; the existing line logs only the derived duration, and only when the flag
   is on);
2. an **emitted, mono-ns switch-in timestamp** joinable to the same rid in the same event
   family (the `admission.v2` mono-ns mark exists, but the enqueue mark does not);
3. **cross-request** `B_enqueue` and `A_finished` (`A_final_compute`/completion) marks —
   the per-request `queue_duration` is single-request only;
4. a **queue-depth time series** and **deadline/miss classification** correlated to each
   request (only per-pass `pos/qlen/running_bs` snippets exist, wall-ms, debug-gated).

### Quantity 2 — `L3 -> L2` stage duration (issue → host-ready/finalize)

**Verdict: PARTIALLY** (RH-origin issue→Host-ready is mono→mono and per-rid joinable;
eager RH-off / disagg / demand-retry issues have no monotonic start mark; attempt identity is
not consistent across the two ends).

Existing start marks (issue):

- `[P2A] ts_ms=… evt=prefetch_issued rid=… prefetch_length=%d` — **wall-ms**, per rid, no
  attempt id (`unified_radix_cache.py:5543`).
- `[P3] ts_ns=… evt=ready_stage schema=rh_stage.v2 rid=… attempt_id=… issue_origin=… result=…
  reason=…` — **mono-ns**, per rid + `rid:prefetch:N` attempt id, but emitted only inside
  `_ready_horizon_pass` for `READY_HORIZON` origin (`scheduler.py:5364-5388`).
- `[P2A] ts_ms=… evt=restore_retry rid=… cause=capacity attempt_id=…` — **wall-ms**
  (`scheduler.py:4296-4299`).

Existing end marks (host-ready/finalize):

- `[P3] ts_ns=… evt=ready_host schema=rh_ready_host.v1 rid=… attempt_id=… issue_origin=…
  completed_kv_tokens=… finalize_result=… ready_monotonic_ns=%d …` — **mono-ns**, per rid +
  prefetch attempt id, emitted on `RestoreEvent.FINALIZED` (`scheduler.py:4437-4485`;
  `ready_monotonic_ns` at `:4464`).
- `[HAE] {… "evt":"restore_hybrid_finalize", "ts_mono_ns":…, "attempt_id":"<rid:N>",
  "kv_expected":…, "kv_fetched":…, "result":"accepted|discarded", …}` — **mono-ns**, per rid +
  host-alloc attempt id (`unified_radix_cache.py:5682-5699` discard, `:5717-5737` accept;
  base emitter adds `ts_mono_ns` at `:180`).
- `[P2A] ts_ms=… evt=prefetch_finalize rid=… completed_tokens=%d mode=%s` — **wall-ms**
  (`unified_radix_cache.py:5647`).
- `[P2A] ts_ms=… evt=prefetch_io_finished rid=… n_tokens=%d` — **wall-ms**
  (`cache_controller.py:1248`).
- `[P2A] ts_ms=… evt=restore_ready rid=…` — **wall-ms** (`scheduler.py:4535-4539`).

Runtime evidence: in `sglang-server-r112.log`, `ready_stage` 118, `ready_host` 116 (10 in the
grep-of-`evt=` census), `prefetch_issued` 132, `prefetch_finalize` 10,
`restore_hybrid_finalize` 10, `restore_success` 10. Sample pair is real:
`ready_stage ts_ns=5271726154365 attempt_id=…:prefetch:1 issue_origin=READY_HORIZON` vs
`ready_host ready_monotonic_ns=5325622701790 attempt_id=…:prefetch:2 issue_origin=DEMAND_RETRY`
(same rid `9ec37547…`; the two ends are **different attempts**).

Missing marks / indistinguishability:

1. a **mono-ns issue mark for non-RH origins** (EAGER_RH_OFF, EAGER_DISAGG_PREFILL,
   DEMAND_RETRY) carrying the attempt id; today only `ready_stage` is mono, and only RH;
2. **one consistent attempt identity** across issue and Host-ready: prefetch attempts are
   `rid:prefetch:N` (`scheduler.py:3135`) while `[HAE]` uses a separate
   `rid:<host_alloc_seq>` namespace (`scheduler.py:4279-4281`), and the generic
   `prefetch_issued` line carries no attempt id at all;
3. because of (2), when a rid has multiple prefetch attempts the `prefetch_issued`→
   `ready_host` pair is joinable only by rid + ordering, not per attempt.

### Quantity 3 — `cache-induced idle` (GPU idle while runnable work exists)

**Verdict: NEEDS_NEW_PROBE** (GPU-timeline metric; not derivable from any existing runtime
counter).

What exists today:

- The scheduler sets a boolean when the next-batch plan is `None`:
  `self._sched_idled = True` (`scheduler.py:2134` normal loop; `:2196` overlap loop) and
  carries it to the next forward as `batch.after_idle_gap = self._sched_idled`
  (`scheduler.py:7182-7184`).
- `_record_step_counters` explicitly **excludes** the gap from the step time:
  `if prev is None or batch.after_idle_gap: return` before `step_us = int((batch.launch_ts -
  prev_ts) * 1e6)` (`scheduler.py:7576-7597`). `launch_ts = time.monotonic()` (`:7182`).
  `decode_moment_totals` (`:589-605`, `:2521`) therefore measures **only non-idle** decode
  steps.
- `is_fully_idle()` (`scheduler.py:7717-7769`) distinguishes "no batch" from "queues
  non-empty" (waiting queue, prefill bootstrap/inflight, decode prealloc/transfer; HiCache
  `ongoing_write_through`/`ongoing_load_back`). This is a state predicate, not a timed
  interval, and `on_idle()` (`:7650-7715`) early-returns on `not is_fully_idle()` with no
  duration emission.
- A windowed **GPU** occupancy gauge exists but is not per-idle-interval and is not in the
  frozen profile: `fwd_occupancy = gpu_time/cpu_time*100` from the CUDA-event
  `forward_pass_device_timer`, gated by `SGLANG_ENABLE_METRICS_DEVICE_TIMER`
  (`metrics_reporter.py:1192-1213`, `:47`; gauge `metrics_collector.py:595-596`). The R112
  profile has `enable_forward_pass_metrics=False`; `fwd_occupancy` is NaN unless the env is set.
- `ForwardPassMetrics` (per-iteration `wall_time` + `queued_requests` counts) is ZMQ-only and
  gated by `enable_fpm` (`forward_pass_metrics.py:82-120`), off in R112.

Missing marks: a GPU busy/idle timeline at sub-5s resolution plus a "runnable but not
computable because cache/state is not ready" classifier, correlated to `cache-induced idle`
duration and to the `restore_wait/queue_wait/compute/decode` residual. R71 `:188-199` already
freezes that these two inputs are required and that 5 s `nvidia-smi` sampling is insufficient.
No existing request counter or timestamp yields GPU idle-while-runnable.

### Quantity 4 — `query_storage_hit_length` critical-path cost

**Verdict: NEEDS_NEW_PROBE** (no enter/exit timing and no component attribution exists on the
synchronous decode-side query path; the only nearby timer is the forbidden whole `load_back`
timer).

Confirmed call path:

- Caller: `DecodeHiCachePreallocMixin._build_decode_prefix_match`,
  `disaggregation/decode_hicache_mixin.py:61-99`, call at **`:84`**
  (`self.tree_cache.query_storage_hit_length(...)`); reached from `DecodePreallocQueue`
  (`decode.py:319`, `:661`).
- Tree impl: `unified_radix_cache.py:5230-5273` `query_storage_hit_length`:
  builds `PrefetchOperation("__storage_hit_query__", ...)` (`:5260-5265`), calls
  `self.cache_controller._storage_hit_query(operation)` (`:5266`), then a TP/CP
  `MIN` all-reduce `self._all_reduce_attn_groups(...)` (`:5268-5270`).
  The `HiRadixCache` twin is `hiradix_cache.py:1507-1544` (same shape; may pass
  `pool_transfers`).
- Controller impl: `HybridCacheController._storage_hit_query`
  (`hybrid_cache/hybrid_cache_controller.py:864-932`) calls
  `storage_backend.batch_exists(...)` (`:886`, for the plain-op path; reached via `:910`) or
  `batch_exists_v2(...)` (`:906`). Base `HiCacheController._storage_hit_query`
  (`cache_controller.py:1293-1316`) batches over `STORAGE_BATCH_SIZE` calling
  `batch_exists` (`:1308`). Backends for the frozen `--hicache-storage-backend file` profile:
  `HiCacheFile` (`backend_factory.py:196-199`) with `batch_exists` (`hicache_storage.py:316-327`
  → `exists()` `:568-577`, `os.path.exists`), `batch_exists_v2` (`:609-657` →
  `_collect_existing_component_keys` `:579-607`, `os.scandir`/`os.path.exists`), and a
  `MetadataCache` `threading.Lock` (`hicache_storage.py:336-365`).
  `PrefetchOperation` also owns a `threading.Lock` and a **`start_time = time.monotonic()`**
  (`cache_controller.py:299-314`) that is **not emitted**.

Existing timing (what is and is not there):

- **No enter/exit timing, no duration, no components** on either
  `query_storage_hit_length` or `_storage_hit_query`. Neither function calls `time.*`.
- The **only** query-shaped probe is `pc_storage_query`
  (`hybrid_cache_controller.py:917-927`), emitted **after** the backend call completes, with
  `"ts": <time.time() seconds>` (via `_t38c_log`, `cache_controller.py:70-81` /
  `hybrid_cache_controller.py:60`), no `ts_mono_ns`, no enter mark and no duration.
  `PrefetchOperation.request_id = "__storage_hit_query__"` for the synchronous path
  (`unified_radix_cache.py:5261`), whereas the async prefetch path uses the real rid — so
  the probe record's `rid` is the only current discriminator, and it does not encode a
  duration.
- The async prefetch path's probes (`pc_prefetch_enter` entry/gate `scheduler.py:3272,3380`;
  `pc_outcome` issue/drain `unified_radix_cache.py:5321…6787`) are wall-s, different phase
  records, not the sync query.
- `pc_*` records carry **no** `ts_mono_ns` (verified: `pc_storage_query` 198, `pc_get_v2`
  812, `pc_l3_host` 35, `pc_outcome` 572, `pc_prefetch_enter` 413 rows; 0 with `ts_mono_ns`).
  `/tmp/t38c-probe.log` contains 50,873 `ts_mono_ns` rows, but they belong to other event
  families (`backup_*`, `residency_*`, `storage_persisted`, `durability_barrier`), not `pc_*`.
- The **forbidden** whole-operation timer is the CUDA-event
  `sglang:load_back_duration_seconds` (`metrics_collector.py:2236-2241,2306-2307`), observed
  from `ack.start_event.elapsed_time(ack.finish_event)` in `loading_check`
  (`unified_radix_cache.py:7680-7684`; `hiradix_cache.py:1150-1154`). It brackets the DMA
  load-back, not the query, and `plan.md:78` forbids using it as isolated query time.

Missing marks: per-sample enter/exit mono-ns around the synchronous
`query_storage_hit_length` / `_storage_hit_query` call, plus component attribution for
backend (`batch_exists`/`batch_exists_v2`), lock (`MetadataCache.lock`,
`PrefetchOperation._lock`), syscalls (`os.path.exists`/`os.scandir`), and the collective /
future-like wait (`_all_reduce_attn_groups`). No enter/exit boundary exists today, so the
`p99 < 100µs / 100µs–1ms / ≥1ms / ~10ms` interpretation bands cannot be assigned.

Runtime/profile note: `decode_hicache_mixin.py` is the **PD-disaggregation decode** path
(`DecodePreallocQueue`); the frozen R112 profile is `disaggregation_mode: 'null'` (from
`server_args` in `sglang-server-r112.log`), so this synchronous caller is **dormant in the
frozen profile**. The 198 `pc_storage_query` rows in `/tmp/t38c-probe.log` all have real
request rids (e.g. `r121-p3-R-F1`), i.e. they came from the async prefetch path, not this
sync decode query.

## Summary table

| # | Quantity | Verdict | Start mark (today) | End mark (today) | Monotonic? | Per rid/attempt? | Missing mark(s) |
|---|---|---|---|---|---|---|---|
| 1 | `queued -> switch` lead | **PARTIALLY** | enqueue: `wait_queue_entry_time` internal mono-f only (`scheduler.py:6072`; `req_time_stats.py:738-757`); emitted `[P2A] evt=admission` wall-ms (`scheduler.py:6736`) and `[P3] …request_enqueue_seq` (counter) | switch-in: `admission.v2 admission_monotonic_ns` mono-ns (`scheduler.py:6820-6836`); `forward_entry_time` internal mono-f (`scheduler.py:6934`) | mixed; derived `queue_duration` is mono-f but opt-in/log-derived | rid yes; attempt n/a | emitted mono-ns enqueue per rid; cross-request `B_enqueue`/`A_finished`; queue-depth series; deadline/miss class |
| 2 | `L3 -> L2` stage duration | **PARTIALLY** | `ready_stage ts_ns` mono-ns RH-only (`scheduler.py:5365`); `prefetch_issued`/`restore_retry` wall-ms (`unified_radix_cache.py:5543`; `scheduler.py:4297`) | `ready_host ready_monotonic_ns` mono-ns (`scheduler.py:4437-4485`); `[HAE] restore_hybrid_finalize ts_mono_ns` mono-ns (`unified_radix_cache.py:5682/5717`); `prefetch_finalize`/`prefetch_io_finished`/`restore_ready` wall-ms | RH start mono; other starts wall | rid yes; **attempt namespaces differ** (`:prefetch:N` vs `:N`) | mono-ns issue mark for all origins with attempt id; one consistent attempt identity |
| 3 | `cache-induced idle` | **NEEDS_NEW_PROBE** | none (only `_sched_idled` bool + `after_idle_gap`, `scheduler.py:7182-7184`) | none; `fwd_occupancy` is a windowed GPU gauge, env-gated (`metrics_reporter.py:1192-1213`) | n/a | n/a | GPU busy/idle timeline (<5 s) + "runnable but cache-not-ready" classifier |
| 4 | `query_storage_hit_length` cost | **NEEDS_NEW_PROBE** | none | `pc_storage_query` wall-s only, after the fact (`hybrid_cache_controller.py:918`) | no | rid only, sync path rid=`__storage_hit_query__` | enter/exit mono-ns pair + backend/lock/syscall/future-event component timers |

## Minimum new probe (what would have to be added)

The contract's P2-A2 resource clause already authorizes the shape: "使用 observation-only
probe" (`plan.md:78`). All four gaps can, in principle, be closed by **log emission only** —
no API, scheduler-policy, tree, backend, or control-flow change — because the timestamps and
counters already exist in-process:

1. **`queued -> switch` (#1)** — emit, per rid, the already-captured internal marks at their
   existing set points: `wait_queue_entry_time` (`scheduler.py:6072`) and
   `forward_entry_time` (`scheduler.py:6934`) as `monotonic_ns` (or emit
   `queue_duration` with the two raw marks). For the cross-request lead, pair B's enqueue mark
   with A's completion mark (`completion_time`/`prefill_finished_time` already set in
   `req_time_stats.py:805-918`). Observation-only: `logger.info` at existing call sites.
2. **`L3 -> L2` stage (#2)** — emit a mono-ns issue mark with the operation's
   `prefetch_attempt_id`/`host_alloc_attempt_id` at `prefetch_from_storage` (`scheduler.py:3415`,
   where both attempt ids are already passed `:3423-3428`) and at `_prefetch_kvcache`
   entry/retry, so it pairs with the already-mono `ready_host`/`restore_hybrid_finalize`.
   Observation-only.
3. **`cache-induced idle` (#3)** — the missing input is a **GPU timeline**, which is *not* an
   in-process log mark; an observation-only probe here means an external device-busy sampler
   (e.g. sub-second CUDA-event/NVML sampling) plus a runnable classifier emission from
   `on_idle`/`is_fully_idle` (`scheduler.py:7650-7769`) that logs whether the idle window had
   non-empty cache-wait queues. Requires a separate profiling/live authorization
   (`plan.md:78`; R71 `:188-199`). Not derivable from existing runtime counters.
4. **`query_storage_hit_length` (#4)** — wrap the synchronous query with an enter/exit
   mono-ns pair and per-component timers around: `cache_controller._storage_hit_query`
   (`unified_radix_cache.py:5266`), `batch_exists`/`batch_exists_v2`
   (`hybrid_cache_controller.py:886/906`), the `MetadataCache` lock
   (`hicache_storage.py:344-365`), the `os.path.exists`/`os.scandir` calls
   (`hicache_storage.py:573,591-604`), and `_all_reduce_attn_groups`
   (`unified_radix_cache.py:5268-5270`). `PrefetchOperation.start_time`
   (`cache_controller.py:312`) already provides a mono start. Observation-only: emit durations
   to the existing `_t38c_log` / logger; no return-value or call-graph change.

For #1, #2, #4 the additions are observation-only log emission (the existing
`_p2a_trace`/`_t38c_log`/`logger.info` machinery is the precedent). For #3 a new GPU-timeline
sampler is required, which is an instrumentation authorization decision beyond a
log-only change.

## Places where the four quantities cannot be distinguished today without a new mark

1. **#4 sync query vs async prefetch query** share `HybridCacheController._storage_hit_query`
   and both emit `pc_storage_query` (`hybrid_cache_controller.py:918`). Without a new mark the
   only discriminator is `PrefetchOperation.request_id == "__storage_hit_query__"`
   (`unified_radix_cache.py:5261`) appearing as `rid` in the probe record; no phase/scope field
   exists, and no duration exists for either.
2. **#2 per-attempt pairs** cannot be distinguished when a rid has multiple attempts: the
   start side uses `rid:prefetch:N` (`scheduler.py:3135`) and the HAE end side uses
   `rid:<host_alloc_seq>` (`scheduler.py:4280-4281`); `prefetch_issued` carries no attempt id.
   Only rid + time-ordering is available, which is ambiguous under retry.
3. **#1 enqueue timing** cannot be reconstructed from emitted records: the mono-f enqueue mark
   is internal and the emitted `[P2A] evt=admission` is wall-ms only; the mono-ns
   `rh_preadmission_decision` carries `request_enqueue_seq` (a counter), not a time. A
   per-request enqueue-to-switch interval therefore cannot be cross-checked between two
   emitted clocks today.
4. **#3 GPU idle while runnable vs GPU idle with no runnable work** cannot be separated: the
   only existing signals are the `_sched_idled` boolean and `is_fully_idle()` at the moment of
   idling, with no GPU timeline and no interval duration; `after_idle_gap` also suppresses the
   step-time accumulation, so the gap is explicitly unmeasured.
5. **#2 non-RH origins** (eager RH-off, disagg prefill, demand retry) cannot be bounded by
   monotonic marks at all: `ready_stage` exists only for `READY_HORIZON`
   (`scheduler.py:5364`); the other origins only have wall-ms `prefetch_issued`/
   `restore_retry`.

## Followups (for the orchestrator; not started here)

1. Decide whether the existing `--enable-request-time-stats-logging` opt-in is acceptable as
   the #1 vehicle, or whether a dedicated per-rid mono-ns enqueue/switch emission is required
   (it is read-only either way).
2. Decide the authorization class for #3: a GPU-timeline sampler is additional
   instrumentation, not a log-only mark, and R71 already records it as an
   authorization/scope seam.
3. Confirm whether P2-A2's live collection targets the PD-disaggregation decode path
   (`decode_hicache_mixin.py`) at all, given the frozen R112 profile is
   `disaggregation_mode: 'null'` and the sync caller is dormant there.

## Open issues / unknowns

1. The exact frozen profile for P2-A execution may change (P1 closure/new freeze); this report
   uses R112/R124 (`--hicache-storage-backend file`, `disaggregation_mode null`,
   `enable_metrics False`, `enable_request_time_stats_logging False`). If the profile changes,
   the #3/#4 availability statements must be re-checked.
2. `[HAE]` and `[P3]` records are monotonic-ns within one process; the report did not attempt
   cross-process clock reconciliation, and P2-A single-process serialization is assumed.
3. `pc_*` rows in `/tmp/t38c-probe.log` span multiple runs; per-run attribution was not
   attempted, only the record shape and field absence were used.
4. No test/import was performed, per the read-only scope; all claims are source- and
   captured-log-based.
