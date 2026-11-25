# T007 C-8 baseline, chunk-size candidate, and Nsight results

Date: 2026-11-25. GPU: RTX 3090, TP1/PP1. All runs used official `benchmark/hicache/bench_multiturn.py`, 40 clients × 20 rounds, 1,024 nominal input / 256 output, Poisson rate 8, seed 42, max-parallel 64, auto-run disabled. All completed 800/800, 0 failures, 204,800 output tokens and 10,547,200 logical prompt tokens. `hashes.jsonl` files for profile baseline and 4096 candidate compare as the exact same multiset of 800 payload hashes. These are independent runs, not paired per-request latency experiments.

## Runs and source/config identity

- Current-source 2048 profile baseline: `/data/sglang-hicache/gemma4/runs/20261125T-t007-c8-profile-r4/` (commit `8a1e3c9e21ad417be6a566d56240f7bdc36df0d1`).
- Current-source unprofiled candidate: `/data/sglang-hicache/gemma4/runs/20261125T-t007-c8-chunk4096/`; sole config delta `--chunked-prefill-size 4096`.
- Current-source profiled candidate repeat: `/data/sglang-hicache/gemma4/runs/20261125T-t007-c8-chunk4096-profile-r2/`; same 4096 delta and 45-second bounded Nsight collection.

Source hashes/import identities, argv, model hash, worker env, pool/GPU samples, request metrics, payload hashes, server logs and bench results reside under each run directory. Candidate used a fresh per-run Extent storage directory, not a replay of the T006 WAL. Owner-only W4A16 / FP8 E5M2 and cache features were held constant. Full/SWA pools stayed 1,441,580/65,536 slots; post-allocation free GPU memory was 1.37 GB, startup available GPU memory 1.12 GB, max-running 32, max-prefill 16,384. These are observed fixture capacities, not certified safe maxima.

## End-to-end results

| Metric | 2048 profile baseline | 4096 unprofiled | 4096 profile repeat |
|---|---:|---:|---:|
| Bench duration | 1,719.91 s | 1,590.36 s | 1,544.84 s |
| Output throughput | 119.076 tok/s | 128.776 tok/s (+8.14%) | 132.570 tok/s (+11.33%) |
| Input throughput | 6,132.40 tok/s | 6,631.95 tok/s | 6,827.37 tok/s |
| Request throughput | 0.4651/s | 0.5030/s | 0.5179/s |
| TTFT mean / p90 / p99 | 46.37 / 74.51 / 104.23 s | 39.54 / 69.20 / 83.78 s | 37.95 / 69.88 / 97.60 s |
| ITL mean / p90 / p99 | 0.1219 / 0.1213 / 0.9805 s | 0.1145 / 0.1576 / 1.2936 s | 0.1118 / 0.1244 / 1.0841 s |
| E2E mean / p90 / p99 | 77.46 / 132.75 / 190.81 s | 68.74 / 115.02 / 143.80 s | 66.46 / 119.75 / 150.47 s |
| GPU NVML mean / p95 / max | 18.53 / 96 / 100% | 19.90 / 96 / 100% | 20.75 / 96 / 100% |

The 4096 parameter has a measured net throughput improvement on this exact workload. 4096 profile vs unprofiled throughput differs by 2.95%, so profiling/run variance is material; this is not a paired causal estimate. Mean/p90/p99 E2E and TTFT are improved against the 2048 profile baseline; ITL tails are mixed. No output-token equivalence oracle was run (sampling is non-greedy); requests completed successfully and payloads match, but this is not a semantic-output equivalence claim.

## Prefill, cache and timer ledgers

- 2048: 573 logged Prefill batches; sequence histogram 1/2/3 = 181/252/140; 1,013,761 logged `#new-token`, mean 1,769.2, max 2,048.
- 4096 unprofiled: 493 batches; sequence histogram 1/2/3/4 = 328/38/25/102; 1,013,761 `#new-token`, mean 2,056.3, max 4,096.
- 4096 profiled: 515 batches; histogram 1/2/3/4 = 358/41/27/89; 1,013,761 `#new-token`, mean 1,968.5, max 4,096. Four-sequence batches rise, but single-sequence prefill remains dominant (69.5% of logged batches in the profiled 4096 run). Thus 4K is only a partial batching constraint.
- Each run’s request ledger accounts for L1=9,533,440, L2=0, L3=0, newly-prefilled=1,013,760 tokens. Every request’s HiCache telemetry is marked `partial`; durable restore/recompute correctness is not established by these performance runs. HOST_ALLOC/FRONTIER wait-state event counts are not time-attributed. No `prefill_deny_summary` appeared. The small current-run one-token scheduler/request-ledger difference is not pursued, per explicit instruction not to investigate the inherited 12-token delta.
- DeviceTimer activation is proven end-to-end in current service: `SGLANG_ENABLE_METRICS_DEVICE_TIMER=1` and NVTX scheduler opt-ins reached the worker; category counters increased and finite occupancy samples were exported. FPM was not enabled. 2048 profile baseline counters: extend 647.63 s + decode 270.23 s / 1,772.11 s = 51.79% aggregate DeviceTimer duty. Initial 4096 unprofiled: 520.77 + 255.55 / 1,632.12 = 47.57%; 4096 profile: 559.69 + 271.07 / 1,596.1 = 52.05%. This is not GPU kernel+copy union.

## Baseline Nsight window

Valid original baseline capture: `20261125T-t007-c8-profile-r4/t007-c8-window.nsys-rep`; SQLite export `profile-window-original.sqlite`; analysis `profile-window-original-analysis.txt`. The wrapper’s first start attempt was invalid because trace options were repeated. The usable report is from recovery via existing Nsight session interface; a later small probe must not be confused with it.

The baseline CUDA event span is 24.306 s (574,696 kernels, 119,777 memcpys, 530 memsets). GPU busy union, counting overlap once, is 10.714 s = 44.08% (kernel union 10.567 s / 43.48%; memcpy 0.151 s / 0.62%; memset negligible), with 13.592 s gaps (55.92%). Nsight copy-type device duration: D→H 146.8 ms / 117,019 rows; D→D 3.57 ms; H→D 0.22 ms. CUDA runtime host-call time: `cudaStreamSynchronize` 2.125 s / 1,993 calls (max 10.84 ms); `cudaGraphLaunch` 1.011 s / 512; `cudaMemcpyAsync` 0.509 s / 119,265; `cudaEventSynchronize` 5.64 ms / 646. These host API durations are not device-copy or idle time.

Largest measured kernel-name summed device time: Marlin BF16×quantized GEMM variants 2.502 s (5,279 launches), 2.134 s (64,768 launches), and 1.108 s (64,768 launches); Triton `_fwd_kernel` 1.379 s (731 launches) and `_fwd_grouped_kernel_stage1` 1.326 s (21,504 launches). Summed kernel duration overlaps across streams and is not union.

Summed inclusive host-thread NVTX duration (ranges overlap):
- `scheduler.get_next_batch_to_run`: 38.908 s / 10,919 calls.
- `scheduler.run_batch`: 15.513 s / 529 calls.
- `scheduler.process_batch_result`: 3.190 s / 531 calls.
- `scheduler.recv_requests`: 0.830 s / 10,919 calls; `process_input_requests`: 0.167 s / 10,919.
GPU-gap intersections overlap: 7.635 thread-s of run_batch, 3.291 of get_next, 2.357 of result processing. By enclosing NVTX, stream-sync host time mostly sits inside `run_batch` (1,075 calls / 2.094 s), with result processing 1,337 calls / 35 ms and get_next 227 / 3 ms. These are not exclusive attribution. Source review: get_next’s prefill path polls `check_hicache_events`, reconciles restore, and performs ready-count/digest synchronization; admission is in `PrefillAdder.add_one_req`; blocking write-through checks are limited to explicit write-back eviction/demotion paths; WAR barrier uses stream/event waits, not host synchronize. Method-level spans do not expose the responsible Python subcall.

## 4096 Nsight window and interpretation

Candidate report: `/data/sglang-hicache/gemma4/runs/20261125T-t007-c8-chunk4096-profile-r2/t007-c8-window.nsys-rep`; SQLite `t007-c8-window.sqlite`, analysis `window-analysis.txt`. Capture duration by GPU event span: 45.050 s; 317,578 kernels, 157,342 memcpys, 285 memsets. Busy union 13.180 s = 29.26%; kernel union 12.990 s / 28.83%; memcpy union 0.193 s / 0.43%; idle gaps 31.870 s / 70.74%. Device memcpy: D→H 191.0 ms, D→D 2.02 ms, H→D 0.35 ms. The largest reported gap is 4.377 s; NVTX shows repeated `scheduler.get_next_batch_to_run` activity in that gap, but there is no nested source range or one uniquely identified blocking operation. This gap is not sufficient causal proof of a single scheduler defect.

Candidate CUDA API host time: stream sync 3.051 s / 1,664 calls (one maximum 185.94 ms), graph launch 0.628 s / 256, memcpyAsync 0.639 s / 157,086. A longest 185.94 ms stream-sync invocation overlapped 185.33 ms of GPU kernel activity and was nested in `scheduler.process_batch_result`; it is largely waiting for active GPU work, not an empty-device host stall. Candidate NVTX inclusive totals: `run_batch` 26.385 s / 286; `get_next_batch_to_run` 12.389 s / 1,988; `process_batch_result` 5.364 s / 284. These totals and the 4096/2048 device busy-union fractions cannot be compared as matched-duty estimates: trace windows differ in duration and workload phase/number of operations, and device event span is not the same as service wall span.

## Final T007 continuation: accepted 4096 run and direct longest-gap path

The full same-load chunk=4096 repeat at `/data/sglang-hicache/gemma4/runs/20261125T-t007-c8-chunk4096-profile-r3/` completed 800/800 requests with zero failures and the exact same 800-payload hash multiset as the current-source 2048 baseline. Effective startup configuration remained Full pool 1,441,580 slots, SWA 65,536, max running 32, max prefill 16,384; chunk size was 4,096. Output throughput was **132.724 tok/s** (vs 119.076 current-source 2048 profile baseline: **+11.46%**, vs T006's 120.231: **+10.39%**). Bench duration 1,543.05s; mean/p90/p99 TTFT 45.83/66.16/245.51s, mean/p90/p99 ITL 72.9/66.2/317.6ms, and mean/p90/p99 E2E latency 64.43/95.14/302.35s. These are independent full runs, not paired per-request comparisons.

NVML samples over the full run: mean 24.08%, p95 100%, peak 100%; GPU memory mean 23,833.67 MiB and **peak 23,864 MiB** on a 24,576 MiB device (712 MiB below reported physical capacity at the sampled peak; observed headroom, not an OOM-margin guarantee). DeviceTimer category totals were 415.3s extend + 215.6s decode over 1,598.1s sampled wall = 39.48% timer duty. The bounded Nsight window measured 40.809s event span, 14.283s kernel+copy+memset busy union (35.00%), and 26.526s idle gaps (65.00%). Keep these measurement scopes distinct. Request telemetry showed actual L1=9,176,320, L2=167,936, L3=0, newly prefetched=1,202,944 tokens; this is performance telemetry, not a renewed correctness qualification.

The requested 4.377s maximum gap comes from the earlier 4096 trace at device-relative 0.820–5.197s (2026-11-25 02:25:42.57–02:25:46.95 UTC). The existing NVTX trace identifies the active scheduler OS thread (`sglang::schedul`, globalTid 292056099037084): it remained in repeated `scheduler.get_next_batch_to_run` calls for 4.167s cumulative (969 short calls, no single call over 162ms) and `scheduler.recv_requests`/`process_input_requests` for only 0.092/0.010s total. There is no `scheduler.run_batch` or `process_batch_result` range in the gap; CUPTI reports **zero** kernel, memcpy or memset events in the interval, and zero stream/event synchronization or stream-wait APIs. The only CUDA runtime call overlapping the gap was a 55µs `cudaLaunchKernel`, at the end boundary. Thus this was not an in-flight running batch, a CPU thread blocked in a long synchronous call, a CUDA stream dependency, or a blocking HiCache synchronization. Scheduler logs show queued requests in `WAIT_CAPACITY` (`HOST_ALLOC` and `FRONTIER`), followed by three `NONE`/recompute releases near the gap's end; a Prefill launch followed. The concrete path is the normal scheduler loop (`event_loop_normal` → `get_next_batch_to_run` → `_get_new_batch_prefill_raw` / `_reconcile_restore_states` / PrefillAdder admission → no batch → `on_idle`), repeatedly finding no currently admissible Prefill or Decode batch while requests remain parked on restore capacity/frontier. It is active polling rather than a blocked function. Existing NVTX is method-level and does not split `_reconcile_restore_states` vs `PrefillAdder`; the existing log has no request-to-selected-batch decision record for this exact interval, so a narrower attribution among those substeps is not established. No source change to wait policy is made: shortening a 60s restore wait or forcing recompute would change cache service behavior and is not justified by this capture alone.

For this task's performance objective, adopt **chunked prefill 4096 as the measured operating parameter** for the fixed C-8 fixture: same workload, cache features and pool budgets; repeated full-run throughput improved by +8.14% unprofiled and +11.46% on the latest profile repeat over the current-source 2048 profile baseline. The full-run 23,864 MiB peak was observed without request failures or OOM. No theoretical max-chunk claim is made. The long-gap explanation is idle due to no presently runnable batch under active restore-capacity waits, not a synchronous CPU/GPU block; modifying restore admission/timeout semantics remains outside this accepted parameter change.

## Time-aligned restore-wait analysis (historical, not an optimization gate)

The existing per-RID `restore_state` timestamps (`ts_ms`, epoch milliseconds) were joined to each Nsight capture using `TARGET_INFO_SESSION_START_TIME.utcEpochNs`. The revised `runs/t007_analyze_window.py` computes WAIT_CAPACITY intervals until the next state transition for that RID, clips them to the device-event span, merges overlapping RID intervals, and intersects their union with kernel+copy idle gaps. Results:

| Capture | Device span | GPU idle gaps | FRONTIER wait union / idle overlap | HOST_ALLOC wait union / idle overlap | Any unique capacity-wait / idle overlap |
|---|---:|---:|---:|---:|---:|
| 2048 baseline | 24.306 s | 13.592 s | 10.279 / 6.063 s | 7.740 / 4.448 s | 6.072 s (44.7% of idle) |
| 4096 profile repeat | 45.050 s | 31.870 s | 45.050 / 31.870 s | 33.830 / 25.746 s | 31.870 s (100% of idle) |

These are wall-clock interval correlations, **not causal attribution**: waits from multiple RIDs overlap each other and the scheduler can be waiting for cache capacity while unrelated work remains eligible. In the 4096 trace, the longest 4.377-second GPU gap (device-relative 0.820–5.197s) aligns with several RIDs entering `WAIT_CAPACITY` near its start; three other RIDs transition to `NONE` at 4.947–5.302s, followed by the next Prefill log at 5.25s (timestamps rounded to milliseconds). This is consistent with restore/capacity state gating progress in that interval, but does not establish that a particular waiter blocked the selected batch or that the timeout/recompute transitions caused the gap to end. In the candidate trace the sampled workload phase was materially different (many 1-sequence/1,280-token Prefills before batches of four/4,096), so the overlap percentages do not establish a baseline-vs-candidate causal effect. This adds a concrete gap-level temporal sequence, but does not explain idle below `get_next_batch_to_run` or establish that changing capacity/admission policy would improve throughput.

A fixed-pool 4096 chunk parameter produces repeatable net C-8 throughput improvement across two current-source candidate runs, with identical offered load/payloads and no request failures. It is an evidence-backed tested candidate, not a certified safe maximum; no runtime source change has been justified. Both performance traces show substantial GPU idle gaps and method-level source attribution. All request telemetry remains `partial`/L1-only; no L2/L3 correctness or actual saved-recompute ledger is established. T007 remains ACTIVE: use existing source seams and timestamps to refine scheduler decision/idle attribution and complete the requested time/token ledger without investigating the excluded 12-token delta or claiming correctness/capacity beyond observed evidence.
