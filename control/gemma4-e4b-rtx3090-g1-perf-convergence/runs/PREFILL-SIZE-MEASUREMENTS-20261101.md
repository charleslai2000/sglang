# Gemma4 independent Prefill-size measurements — 2026-11-01

## Scope

Pinned service model/checkpoint and BF16 KV, one request at a time, Radix cache disabled, context 8,450, `chunked_prefill_size=8192`, prompt tokens drawn from accepted natural-ID fixture; output exactly one token. No profiler-internal forwarding flags and no batch32 validation rerun. Run archive: `/data/sglang-hicache/gemma4/runs/20261101T-prefill-sizes/`; sampler: `prefill_sizes_gpu.py`; command wrapper: `measure_prefill_sizes_gpu.sh`.

## Results

| Prompt | RID | Cache hit | Prefill CUDA Event duration | Prefill Event throughput | Client wall |
|---:|---|---:|---:|---:|---:|
| 1,024 | `radix8k-perf-g1-prefill-n1024-222199_0` | 0 | 147.599 ms | 6,937.71 tok/s | 211.00 ms |
| 4,096 | `radix8k-perf-g1-prefill-n4096-222199_0` | 0 | 490.839 ms | 8,344.90 tok/s | 514.66 ms |
| 8,192 | `radix8k-perf-g1-prefill-n8192-222199_0` | 0 | 1,043.633 ms | 7,849.50 tok/s | 1,062.02 ms |

The service accepted all exact prompt lengths; each returned one token, cached zero tokens, and produced RID-matched `DeviceTimer` CUDA Event records with `category=extend`, `batch=1`. The table's Prefill time is the Event elapsed for that extend; TPS is prompt tokens divided by that Event elapsed. Each request also had a separate decode Event of approximately 9.9–10.7 ms for its one output token; excluded from Prefill. Scheduler `ReqTimeStats` and HTTP wall are separately retained in raw evidence. NVML samples every 100 ms during this run recorded peak process-visible GPU usage of 23,529 MiB; this is whole-device sampled usage including resident model/KV, not incremental Prefill allocation.

## Evidence limits

CUDA times are GPU Event elapsed intervals around each DeviceTimer-wrapped ModelRunner forward, joined by exact RID and `category=extend`. They represent GPU-stream execution span for that forward; they are distinct from Scheduler/request wall time and do not claim exclusive SM busy time. The batch is one and no multi-RID time was apportioned. NSYS is retained for corroboration but its 2025.1.3 export contains only CUDA Graph creation/runtime records, no kernel activity table; Nsight GPU metric counters were rejected by driver permission `ERR_NVGPUCTRPERM`. Peak memory is therefore NVML sampled whole-device usage (100 ms cadence), not an instantaneous per-forward allocation peak.

At teardown NVML reported 1 MiB / 0% GPU; service and profiler processes exited. The earlier initial sample without `SGLANG_ENABLE_METRICS_DEVICE_TIMER=1` plus request-filtered `RADIX8K_GPU_FORWARD` logging is superseded and must not be mixed with this final RID-linked run. Archive `/data/sglang-hicache/gemma4/runs/20261101T-prefill-sizes/` contains exact requests/responses, Nsight report, samples, logs, fixture/hash, and run manifest.
