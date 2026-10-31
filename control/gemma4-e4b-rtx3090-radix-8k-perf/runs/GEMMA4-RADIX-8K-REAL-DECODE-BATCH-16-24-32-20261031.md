# Gemma4 Radix 8K — Real Decode Batch 16/24/32 (2026-10-31)

## Result and configuration

This follow-up deliberately overrides the historical service cap of 16 to test real active GPU batches 16, 24, and 32. Single RTX3090, TP=1, W4A16 pinned checkpoint/config, BF16 KV, Triton attention, Decode CUDA Graph FULL, Radix L1 on, HiCache L2/L3 off, greedy 256 output tokens, 8192 prompt (7168 cached + 1024 new), `context_length=8450`, `max_running_requests=32`, `mem_fraction_static=.90`. Decode graph max batch=32, explicit buckets `[1,2,4,8,12,16,24,32]`. For each client concurrency 16/24/32: one warmup and three measured rounds; 16/24/32 requests are sent concurrently per round.

Run directory: `/data/sglang-hicache/gemma4/runs/20261031T145717Z-radix8k-prefix-benchmark/`. Source checkout/branch as recorded locally; base source revision used by previous accepted matrix: `cdf57faef38e71c2c7880ba0528df6d7fe541bcb`; the run includes local dirty event-timer instrumentation, so base SHA alone is not a full source identity. Fixture copied from prior accepted run, SHA-256 `986a1b06e804a96cdd033367a6175cfd6efe4ccda1847f2e28e632abab10cf58`. Model `config.json` SHA-256 `7f0cd2d17bdb0d5adc6db8e7168bb9a9aa68a6c4ad879d80ecf83e6819c893d3`. Exact resolved launch args, including graph buckets, are archived in `server.log`'s `server_args` record.

## Acceptance evidence

- Startup captured CUDA Graph batches `bs=32` and `bs=24` successfully; capture ended normally. Runtime resolution reports `max_running_requests=32`, `max_total_num_tokens=141471`. Full KV pool=141471 tokens; SWA pool=113176; post-capture available GPU memory=2.14 GiB.
- Scheduler log distribution for requested c16/c24/c32: real Decode batches 16/24/32 each occurred with `cuda graph: True` (26/25/26 log records, respectively); no eager Decode record was observed. Thus these are GPU execution batches, not merely client concurrency or padded-only claims. CUDA Event records also report batch sizes 16/24/32.
- All 216 matrix requests (3 concurrencies × 4 rounds × concurrency) returned 200 with exactly 256 output tokens and response `cached_tokens=7168`. All report `num_retractions=0`. The server log has 288 unique matrix RID records (including 72 validation requests): every matrix RID has Scheduler `ReqTimeStats` `input_len=8192`, `cached_input_len=7168`, `output_len=256`; Prefill records show actual cached/new batches. Thus each prompt has exactly 1,024 newly prefetched tokens. Parser summarizes forward events for requested RIDs; no CUDA Event is apportioned across requests.
- No OOM, capacity reduction, request failure, or runtime `cuda graph: False` appears. The server's final asyncio `SystemExit`/`CancelledError` traceback followed intentional SIGTERM after all requests drained (`Remaining number of requests 0`); classify as shutdown noise, not an inference failure. CUDA-event extension instrumentation reports an unrelated local TorchCodec/FFmpeg shared-library diagnostic at import; it did not prevent model initialization, graph capture, requests, or telemetry.
- Peak sampled GPU memory was 23,437 MiB across 355 samples in `gpu-samples.csv`; post-run GPU state in `gpu-after.csv` (1 MiB used, 0% utilization). Service stopped and exclusive lock released.

## Online measurements

Output TPS is `256 × client concurrency / observed round wall time`, includes request completion wall time, and is not CUDA Event throughput. Values are mean ± sample SD across the three measured rounds; warmup excluded.

| Client concurrency = actual GPU decode batch | Output TPS mean ± sample SD | Request E2E P50 / P95 (s), measured requests | Mean TTFT (s) | Mean API decode throughput (tok/s/request) | Mean TPOT (ms) |
|---:|---:|---:|---:|---:|---:|
| 16 | 653.47 ± 1.76 | 6.19 / 6.23 | 1.78 | 59.35 | 16.85 |
| 24 | 670.44 ± 1.09 | 9.08 / 9.10 | 2.52 | 40.08 | 24.95 |
| 32 | 727.54 ± 0.30 | 11.15 / 11.18 | 3.23 | 33.50 | 29.86 |

E2E and TTFT are response request statistics; wall and metadata have different boundaries. No causal claim is made about throughput change between concurrency settings.

## Prefill and Decode CUDA Events

`RADIX8K_GPU_FORWARD` CUDA Events bracket runner execution on the CUDA stream; they are not isolated kernel time and exclude host Scheduler queue/dispatch as a separate interval. Batch=1, one-RID extend intervals belong to that one-RID batch; batch=2 times remain joint batch intervals. Primer's chunked Prefill events are excluded by RID filtering. Values below use measured rounds only (warmup excluded).

| Concurrency | Extend batch | RIDs/event | Events | Mean CUDA-event time (ms) | Range (ms) |
|---:|---:|---:|---:|---:|---:|
| 16 | 1 | 1 | 6 | 169.584 | 168.758–170.233 |
| 16 | 2 | 2 | 21 | 322.352 | 320.967–323.509 |
| 24 | 1 | 1 | 6 | 171.409 | 170.302–172.996 |
| 24 | 2 | 2 | 33 | 325.690 | 323.803–328.158 |
| 32 | 1 | 1 | 6 | 171.854 | 171.502–172.282 |
| 32 | 2 | 2 | 46 | 328.163 | 326.158–329.869 |

Decode-only aggregate TPS is defined as `sum(batch_size across measured decode CUDA events) / sum(gpu_s across those same events)`. It is event-denominator throughput, not service wall throughput; each event represents one decode-token position per active request. Warmup and Prefill events are excluded. The timer wraps runner Decode execution including batch loading, not Scheduler queue/dispatch as a separate interval.

| Concurrency / actual batch | Decode-token positions | CUDA-event seconds | Decode-only aggregate TPS |
|---:|---:|---:|---:|
| 16 | 12,288 | 10.239405856 | 1,200.07 |
| 24 | 18,432 | 14.509729755 | 1,270.32 |
| 32 | 24,576 | 16.420001497 | 1,496.71 |

## Historical comparison and scope

Prior accepted c24/c32 measurements used `max_running_requests=16`, Decode graph max_bs=16, and active batches capped at 16. Their output TPS (585.14 and 645.55) are historical cap-16 context, not real batch-24/32 data. The follow-up 653.47/670.44/727.54 numbers use changed request capacity and graph buckets; compare descriptively only. G1 numerical/GSM8K remains **FAILED / NOT ACCEPTED**.

## Artifacts

- Raw run: `/data/sglang-hicache/gemma4/runs/20261031T145717Z-radix8k-prefix-benchmark/` (`records.json`, `raw.jsonl`, `server.log`, `gpu-samples.csv`, `gpu-after.csv`, fixture and validation responses).
- Runner: `../runs/launch_radix8k.sh`; client: `../runs/radix8k_benchmark.py`; event parser: `../runs/analyze_radix8k_events.py`.
- Exact postprocessing invocation: `python3 control/gemma4-e4b-rtx3090-radix-8k-perf/runs/analyze_radix8k_events.py /data/sglang-hicache/gemma4/runs/20261031T145717Z-radix8k-prefix-benchmark/server.log --concurrency 16 24 32 --measured-only`. Event counts are joined across multiple RIDs in one GPU forward; the extend table reports shared batch intervals, not per-RID duration.
- Raw SHA-256: server.log `e21d39edf87b7082eac100d4241849879e353a25c91d97ed62b7ba9ee9ca6351`; records.json `c6a3498a03e8547a4ad215f3c09e43451e771a477b47cec038ce3c5acdb3022e`; raw.jsonl `2d518e5821522d36c07bbb13d3b648d7da5688faf05e1dfe727d56c2008c9998`; fixture `986a1b06e804a96cdd033367a6175cfd6efe4ccda1847f2e28e632abab10cf58`; gpu-samples `5ffd70999248bcfa98585b60c5de66d1f98e236545475a65169a323fefd7bb63`; gpu-after `ce70767cd352fd75f7a3f20cfaa9d3bd62d0703977bb3c99395fe8cf685d1362`.
