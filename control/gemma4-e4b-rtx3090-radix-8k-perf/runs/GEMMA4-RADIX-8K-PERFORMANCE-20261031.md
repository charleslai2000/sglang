# Gemma4 Radix 8K Performance — 2026-10-31

## Result

Real RTX3090 TP=1 online service matrix completed: BF16 KV, W4A16 checkpoint, Triton attention, Decode CUDA Graph enabled, HiCache L2/L3 disabled, greedy 256-token output, `context_length=8450`, `max_running_requests=16`. Every request was validated from response `cached_tokens=7168` and Scheduler `ReqTimeStats` (`input_len=8192`, `cached_input_len=7168`, `output_len=256`); Prefill batch records show `#new-token=1024, #cached-token=7168`. The full prefix primer was sent as a separate request before validation and the matrix.

Raw run: `/data/sglang-hicache/gemma4/runs/20261031T142335Z-radix8k-prefix-benchmark/` (c2–c32) and `/data/sglang-hicache/gemma4/runs/20261031T141513Z-radix8k-prefix-benchmark/` (c1). Fixture SHA-256 `986a1b06e804a96cdd033367a6175cfd6efe4ccda1847f2e28e632abab10cf58`; checkpoint artifact config SHA-256 `7f0cd2d17bdb0d5adc6db8e7168bb9a9aa68a6c4ad879d80ecf83e6819c893d3`. Source revision at measurement was `cdf57faef38e71c2c7880ba0528df6d7fe541bcb`; final runner hashes are launcher `9a65e572ac3992a4c6aa7512941ce31c9c3b936d1c335a6892abf8a349621e88` and client `de1bd9e65e976e01e173748a23f46fc1e34373a6c2b6b65c3a1847d17911b673`. The run has one warmup and three measured rounds at each concurrency, plus a validation request. All 348 c1–c32 warmup/measured matrix requests passed the 7,168 cached / 256 output checks; no invalid request was included.

## Online measurements

| Client concurrency | GPU decode batch (scheduler) | Output TPS, measured-round mean ± sample SD | Per-request decode throughput mean (tok/s) | TPOT mean (ms) | E2E P50 / P95 (s) | TTFT mean (s) |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 1 | 104.15 ± 0.07 | 110.57 | 9.04 | 2.46 / 2.46 | 0.19 |
| 2 | 2 | 192.09 ± 0.07 | 110.99 | 9.01 | 2.66 / 2.66 | 0.36 |
| 4 | 4 | 333.55 ± 0.67 | 106.10 | 9.44 | 3.05 / 3.06 | 0.65 |
| 8 | 8 | 491.69 ± 6.16 | 85.36 | 11.82 | 4.11 / 4.19 | 1.12 |
| 16 | 16 | 650.85 ± 3.75 | 59.26 | 17.34 | 6.23 / 6.29 | 1.81 |
| 24 | 16 | 585.14 ± 4.03 | 67.66 | 15.60 | 6.36 / 10.49 | 3.69 |
| 32 | 16 | 645.55 ± 0.40 | 58.87 | 17.46 | 9.43 / 12.59 | 4.99 |

Output TPS is the 256×client-concurrency tokens divided by observed round wall time; its numerator includes the required output per request and its wall interval includes all concurrent request completion. Per-request decode throughput and TPOT are API metadata and are not the batch aggregate. c24's lower aggregate TPS versus c16 is an observed measurement; this report does not infer a scheduler cause. Client c24/c32 are distinct from the GPU batch cap 16.

## Timing and resource boundary

Request metadata includes `prefill_finished_time`, `first_token_ts`, E2E, and request receipt, so TTFT/E2E are available per request. Existing DeviceTimer CUDA Events in the archived server logs do provide actual `extend` batch execution intervals. The report below extracts these without apportioning multi-RID batches. `extend` timing brackets runner execution (and for prefill CUDA graph paths can include batch loading); it is not a kernel-only counter or host Scheduler wall time. No per-request time is inferred from a multi-RID batch.

### Newly Prefilled 1,024 Tokens: CUDA Event Time

Scheduler `ReqTimeStats` and Prefill batch lines prove 7,168 cached + 1,024 new tokens for these requests. The `RADIX8K_GPU_FORWARD category=extend` CUDA-event logs correlate by RID and record elapsed GPU-stream time for the batch. For batch=1 events with one RID, the elapsed interval is exactly associated with that one-RID extend batch. For batch=2 events listing two RIDs, the duration belongs to the joint batch and is **not** divided between requests.

| Client concurrency | Actual extend batch | Requests/RIDs in event | Event count across warmup + 3 rounds | Mean CUDA-event time (ms) | Observed range (ms) |
|---:|---:|---:|---:|---:|---:|
| 1 | 1 | 1 | 4 | 168.743 | 168.572–169.059 |
| 2 | 1 | 1 | 8 | 168.759 | 167.819–169.824 |
| 4 | 1 | 1 | 8 | 169.555 | 168.697–171.150 |
| 4 | 2 | 2 | 4 | 324.571 | 323.365–327.145 |
| 8 | 1 | 1 | 8 | 178.054 | 169.612–233.748 |
| 8 | 2 | 2 | 12 | 325.325 | 323.376–331.334 |
| 16 | 1 | 1 | 4 | 170.994 | 169.980–171.668 |
| 16 | 2 | 2 | 30 | 326.238 | 324.146–329.044 |
| 24 | 1 | 1 | 2 | 173.123 | 172.644–173.603 |
| 24 | 2 | 2 | 47 | 328.226 | 325.262–335.786 |
| 32 | 1 | 1 | 8 | 172.833 | 172.344–173.605 |
| 32 | 2 | 2 | 60 | 329.363 | 327.870–331.932 |

These are observed extend-forward batch times, not decomposed attention-only time. Batch=2 means about twice the single-batch interval in this workload, but it remains one measured batch interval for two requests. The c1 run had four accepted c1 matrix extends, all batch=1 and one RID. The matrix run contributes c2–c32 entries. The separate long-prefix primer's chunked uncached Prefill comprised four batch=1 extend events; it is not the 1,024-token new-suffix event and is excluded from the table.

### Decode-only Aggregate TPS

Define decode-only aggregate TPS as `sum(batch_size for measured decode CUDA Events) / sum(gpu_s for those same decode CUDA Events)`. The numerator is the number of generated decode-token positions represented by the events; the denominator is summed event intervals, **not wall time**. Warmup rounds and extend/prefill events are excluded. The event includes the runner's Decode execution interval (the timer wraps `load_batch` plus execution; the model log says Gemma4 prefill CUDA Graph is disabled by its multimodal auto-disable rule, while Decode CUDA Graph is enabled); it does not add host Scheduler queue/dispatch duration as a separate numerator or wall-time denominator. Host work can affect when events are enqueued, so this is not a claim that the GPU was continuously busy throughout each interval. It is distinct from round Output TPS and response-metadata per-request decode throughput.

| Client concurrency | Decode batch size(s) | Decode tokens, measured rounds | Summed CUDA Event seconds | Decode-only aggregate TPS |
|---:|---:|---:|---:|---:|
| 1 | 1 | 768 | 6.804835 | 112.86 |
| 2 | 2 | 1,536 | 6.867755 | 223.65 |
| 4 | 4 | 3,072 | 7.015306 | 437.90 |
| 8 | 8 | 6,144 | 8.048942 | 763.33 |
| 16 | 16 | 12,288 | 10.277258 | 1,195.65 |
| 24 | 8 and 16 | 18,432 | 18.460615 | 998.45 |
| 32 | 16 | 24,576 | 20.629183 | 1,191.32 |

The c24 denominator includes batches of 8 and 16 as actually recorded. At c32 the scheduler emitted batch-16 events that represent tokens across the active requests; numerator counts 16 token positions per event. This metric does not amortize requests against concurrent wall time.

GPU sampling every 500 ms recorded peak memory 22,957 MiB and peak utilization 100%. The serving scheduler's decode GPU batch never exceeded 16; client concurrency reached 32. GPU and service were cleanly stopped after the run and the exclusive lock released.

## Evidence and limitations

- Scheduler request stats and per-response `cached_tokens` are request-linked; aggregate FPM is corroborative only.
- The Prefill stats event is batch-level and was isolated to each request at c1 validation; for matrix requests, request-linked stats establish exact cache-hit/new-input lengths. Do not interpret batch device timing as per-request timing.
- Existing 64-token baseline is reused, not rerun. It is not a matched 8K prompt comparison; this report gives descriptive 8K measurements only.
- G1 numerical/GSM8K acceptance remains **FAILED / NOT ACCEPTED** and is independent of this performance result.

## Artifacts

- c2–c32 `records.json`, `raw.jsonl`: `/data/sglang-hicache/gemma4/runs/20261031T142335Z-radix8k-prefix-benchmark/`; c1 equivalents: `/data/sglang-hicache/gemma4/runs/20261031T141513Z-radix8k-prefix-benchmark/`.
- `server.log`: Scheduler `ReqTimeStats`, Prefill cache/new-token evidence and runtime settings.
- `gpu-samples.csv`, `gpu-after.csv`: resource samples and cleanup snapshot.
- `fixture.json`, `fixture.sha256`: exact natural-token-ID prefix/suffix fixture.
- Runner sources: `../runs/launch_radix8k.sh`, `../runs/radix8k_benchmark.py`.
- Existing-event postprocessor (no GPU, no new tracing): `../runs/analyze_radix8k_events.py`.
