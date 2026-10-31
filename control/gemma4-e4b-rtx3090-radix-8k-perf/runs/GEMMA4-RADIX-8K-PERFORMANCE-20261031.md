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

Request metadata includes `prefill_finished_time`, `first_token_ts`, E2E, and request receipt, so TTFT/E2E are available per request. There is no standalone per-request Prefill-only elapsed interval: `ReqTimeStats.forward_duration` covers the combined request forward work and is not a prefill-only measure. The added CUDA-event timing records batch GPU time, not per-request attribution. Consequently no standalone Prefill TPS or per-request GPU-forward time is claimed here.

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
