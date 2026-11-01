# Gemma 4 G1 performance convergence — 2026-11-01

## Decode timeline correlation

The offline join is in `analyze_same_run_graph_timeline.py`. For each accepted c16/c24/c32 profiler trace it joins Scheduler NVTX (`thread`, `step`, actual `batch`, `bucket`, RID set) to the same-thread `cudaGraphLaunch` runtime correlation ID and then CUPTI graph execution. Each cohort has 256/256 unique Decode steps, and each step RID set equals that batch's cohort. Host launch time, GPU replay interval, request queue/Prefill/E2E intervals remain separate timing domains; no multi-RID batch GPU time is divided among requests.

| Batch | GPU graph replay P50/P95 (ms) | Scheduler NVTX start → graph API submit P50/P95 (ms) | Same-run profiler request queue P50/P95 (ms) | Prefill forward P50/P95 (ms) | Prefill done − request received P50/P95 (ms) | E2E P50/P95 (ms) |
|---:|---:|---:|---:|---:|---:|---:|
| 16 | 12.593/13.077 | 8.698/9.491 | 1,012/2,201 | 571/673 | 1,755/2,681 | 6,294/6,337 |
| 24 | 18.079/18.360 | 13.890/14.455 | 1,710/3,238 | 572/677 | 2,415/4,012 | 9,110/9,219 |
| 32 | 20.419/21.187 | 16.208/17.085 | 2,285/4,493 | 521/674 | 3,129/5,365 | 11,175/11,378 |

Profiler request timestamps are instrumentation/cohort dependent; `prefill_done − request_received` includes both queue and Prefill and is not comparable to request forward duration alone. Use the accepted *non-Profiler* baseline for online service timing: 48/72/96 requests at c16/c24/c32 have TTFT P50/P95 **1.832/2.688, 2.544/4.095, 3.250/5.483 s**; TPOT P50/P95 **17.117/21.908, 25.597/32.384, 31.000/40.523 ms**. Do not subtract profiler and baseline percentiles or make per-request attribution of graph replay time.

## Prefill cohort accounting

From Scheduler Prefill batch records and unique `RADIX8K_FWD` NVTX labels, c16/c24/c32 initial Prefill phases contain **8/12/16** unique forwards. Each NVTX-labeled forward is actual batch 2, lists two distinct RIDs, and processes 2,048 new tokens; its set partitions the 16/24/32 request RIDs exactly. These counts describe the RID-labeled target cohort forwards; they do not claim every cohort-associated scheduler Prefill batch during client arm/capture startup was NVTX-labeled. Thus target-window c16 count is eight forwards, not four. A separate exact-hit c16 batch8 run has 16 RIDs processed in two batch8 forwards (two waves), not four. It does not establish Prefill batch16/24/32.

- Accepted batch2 profile: eight forwards; summed kernel duration P50/P95 **134.686/135.662 ms**; enclosing NVTX P50 **138.533 ms**.
- Accepted chunk-8192 batch8 follow-up: two forwards; summed kernel duration per step about **272.16 ms** (two samples), enclosing NVTX about **276 ms**.
- Decode-profiler cohorts have no request `first_token_ts`; profiler-cohort TTFT is **UNKNOWN**. The no-profiler online TTFT above is authoritative for those accepted runs.
- Profiler sampled whole-device memory peaks: c16/c24/c32 **22,952/23,102/23,350 MiB**. Accepted no-profiler baseline sampled 22,957 MiB. Different sampling and profiler instrumentation prevent interpreting these as incremental Prefill memory or a controlled perturbation estimate.
- Independent 1K/4K/8K CUDA Event Prefill measurements and raw evidence are detailed in `PREFILL-SIZE-MEASUREMENTS-20261101.md`.

## One-request Prefill-size CUDA Event run

Archive: `/data/sglang-hicache/gemma4/runs/20261101T-prefill-sizes/`. BF16 KV, context 8450, Radix cache disabled, one request at a time, safe `chunked_prefill_size=8192`, exact natural token IDs, each prompt uncached (`cached_tokens=0`), one output token. CUDA Event `DeviceTimer` rows match request RID and `category=extend`; separate one-token `decode` events are excluded.

| New prompt tokens | RID suffix | Prefill CUDA Event | Input tokens/s | Scheduler `ReqTimeStats` forward | HTTP client wall |
|---:|---|---:|---:|---:|---:|
| 1,024 | `n1024-222199_0` | 147.599 ms | 6,937.71 | 160.65 ms | 211.00 ms |
| 4,096 | `n4096-222199_0` | 490.839 ms | 8,344.90 | 500.96 ms | 514.66 ms |
| 8,192 | `n8192-222199_0` | 1,043.633 ms | 7,849.50 | 1,053.25 ms | 1,062.02 ms |

NVML sampled at 100 ms recorded max **23,529 MiB** device memory, including resident model and KV pools; this is sampled whole-device occupancy, not incremental Prefill allocation. NSYS GPU counter sampling was unavailable (`ERR_NVGPUCTRPERM`); no counter-based utilization/bandwidth claim is made. Its `.nsys-rep` is retained; the installed 2025.1.3 SQLite export provides no Prefill kernel-activity table, so CUDA Event timing is the per-RID GPU stream evidence. Event elapsed is not exclusive SM-active time. Full run methods, responses, server log, sample series and fixture hash reside in the archive.

## Five diagnostic issues and disposition

1. **GPU time at 1K/4K/8K Prefill:** measured independently above with RID-linked CUDA Events; accepted cache-hit cohort profiles also measure batch2 and batch8. Cache-hit Prefill batch16/24/32 remains unmeasured; 16,384 chunk OOM is excluded and not retried.
2. **Decode graph vs online TPOT:** same-run step/API/replay correlation and separate online TPOT percentiles are above. They are distinct timing domains; causal decomposition and per-request graph GPU time are unsupported.
3. **Dominant kernels:** Prefill aggregate kernel duration identifies Marlin GEMM (513.6 ms) and `_fwd_kernel` (496.0 ms) over eight batch2 forwards; sums may overlap. Graph-internal Decode kernel shares are not established; NCU not run because kernel-level attribution is not required to support the batch-level replay measurement.
4. **Graph/eager:** 256/256 Decode forwards each batch are graph=1 with matching bucket 16/24/32. Prefill forwards are eager/graph disabled per model auto-rule.
5. **Capture failure / exit 137:** signal-triggered CUDA-owning Scheduler capture obtained full target graph windows. Separate reported invocation exit 137: one permitted read-only log check found no usable log/artifact; cause **UNKNOWN**, not inferred to be OOM.

G1 remains **FAILED / NOT ACCEPTED** for its independent frozen numerical and quality gates. GPU work was under `/tmp/f1-r16b-gpu-exclusive.lock`; service/profiler exited and NVML returned 1 MiB / 0%. No batch32 validation was repeated. No production math, KV, cache or performance path changed. Preserve unrelated dirty work; selectively integrate only the standalone owned analysis/report files and verify remote SHA after push.
