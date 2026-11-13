# Post-RoPE E5M2 quality, capacity and throughput — 2026-11-11

## Quality pair

Frozen QUASAR GGUF SHA `7d6269096c9acbce4422fd1aa3a249436b01288868961e48ca9bb2541997f669`; frozen 1,319-prompt fixture SHA `2e64e8865f9e314eadb3320593a23e65ebc3f01daf6d2f4662c35983df5c3f86`. E5M2 results: `/data/sglang-hicache/g2-quasar-runs/20261110T-g2-postrope-e5m2-quality-run2/results.jsonl` SHA `99bedba639bdae86d5ea608299dc3790483a1c98cf4e7efceea2b90ccdfe327f`; BF16 reference remains `.../20261110T-g2-rope-bf16-quality/results.jsonl` SHA `3e0cdfdce5d2a2c864c6f4ab7f83b4ebe71982306ebf2fafe943601b1a32a8e4`.

Both arms contain ordered doc_id 0–1318 and all 1,319 prompt-text and prompt-token-ID hashes match. Independent strict-last (`####\s+number`, ignore comma/dollar, optional final period only) rescoring agrees with each E5M2 row. BF16 1,091/1,319 (82.714%); E5M2 1,098/1,319 (83.245%): +7 items / +0.531 percentage points. Paired transitions: both correct 1,051; both wrong 181; BF16-only correct 40; E5M2-only correct 47. Paired bootstrap, 20,000 resamples with seed 20261106: 95% CI for delta **[-0.834,+1.895] pp**. First generated token matches 1,272/1,319; complete generated token sequence matches 432/1,319. E5M2 termination: 4 length caps, 38 repeated-4gram flags, 10 no-marker answers, 218 normally stopped wrong answers. The aggregate pair provides no evidence of a systematic quality regression, but the interval includes both modest harm and benefit. No applicable Owner quality threshold was found; therefore **E5M2 remains NOT ACCEPTED**, not GO.

Execution retries: the earliest service attempts did not yield valid quality evidence (one lacked `common_ops`; another hit the shared dirty kernel's undefined `BF16_KV_COMPUTE` before a valid request). The final isolated-overlay quality run completed all 1,319 requests and exited 0. Its shell log's trailing `Killed` is the server process-group cleanup after the result/summary/hash files were written; final GPU/lock checks were clean. The first performance invocation exited 1 because its output `perf/` directory had not been created; it produced no benchmark rows and is not used. The corrected run2 and 5-trial recheck both completed with exit 0 and valid raw/summary data; their `Killed` lines likewise are server teardown, not benchmark failure. The successful quality and performance services used the previously verified isolated HEAD kernel overlay (SHA `69a9f59d6817b3947feb38639d47c690e82947ead0e9af50a0200f02a4b34d4e`) and SM86 ABI package (binary SHA `22c9f5eb84e5e494df31f814aeffe5ba0aafb266fca2b56c99cfb5a3c1dea4c2); no shared source was changed. Historical private Extend overlay remains unrecovered, so no claim is made for that distinct path.

## Capacity and real-service characterization

Both services ran on the RTX3090 under `/tmp/f1-r16b-gpu-exclusive.lock`, TP1, BF16 compute, E5M2 KV, context 8192, Triton, chunked prefill 2048, CUDA graphs and Radix cache disabled, mem fraction 0.88. The max-running-requests=1 quality service allocated Full **1,117,828** / SWA **4,738** slots (K and V each 7.46 GB Full; each 0.08 GB SWA). The separate max-running-requests=16 throughput service allocated Full **1,093,791** / SWA **14,353** slots (K/V each 7.30 GB Full; each 0.24 GB SWA), with 2.46 GB available GPU memory after pool allocation. These are observed settings-specific capacities, not a direct BF16-vs-E5M2 matched capacity ratio.

Throughput workload: 64 random input IDs, exactly 32 generated tokens, concurrency 1/4/8/16, first wave warmup; 3 measured waves on run1, then 5 on recheck because concurrency-8 varied sharply. Aggregate completed output TPS by concurrency:

| Concurrency | Run1 trials (mean ± sample SD) | Recheck trials (mean ± sample SD) |
|---:|---|---|
| 1 | 9.09, 9.07, 9.01 (9.06 ± 0.04) | 8.96, 8.96, 8.97, 8.96, 8.98 (8.96 ± 0.01) |
| 4 | 33.95, 34.05, 34.11 (34.04 ± 0.08) | 33.39, 33.41, 33.25, 33.54, 33.69 (33.46 ± 0.17) |
| 8 | 14.92, 58.65, 65.27 (46.28 ± 27.36) | 17.95, 14.13, 14.08, 14.63, 63.92 (24.94 ± 21.85) |
| 16 | 114.97, 115.61, 115.63 (115.41 ± 0.38) | 115.11, 114.76, 115.49, 115.93, 114.21 (115.10 ± 0.66) |

All requests returned 32 tokens. Client request wall P50/P95, pooled over measured requests: run1 c1 3.528/3.549s, c4 3.756/3.769s, c8 4.355/17.147s, c16 4.421/4.447s; recheck c1 3.571/3.573s, c4 3.828/3.847s, c8 17.481/18.169s, c16 4.440/4.476s. C8 is materially unstable/bimodal across waves; preserve this as measured, do not quote its arithmetic mean as a stable capacity/performance point. Service logs show decode batches at 8 requests sometimes around 14–18 tok/s and sometimes around 53–55 tok/s; no GPU/API error or request failure was observed. The cause of this variation was not isolated. Metrics are client wall-time wave aggregate for a short synthetic request, not decode-only throughput or a product SLO.

## Artifacts, cleanup, limits

- Quality run manifest, prompts, results, model-info, server log, summary and SHA list: `/data/sglang-hicache/g2-quasar-runs/20261110T-g2-postrope-e5m2-quality-run2/`; paired independent summary `paired-summary.json`.
- An initial performance startup with missing output directory exited 1 before benchmarking; its retained directory is not evidence. The valid three-trial performance run is `/data/sglang-hicache/g2-quasar-runs/20261111T-g2-postrope-e5m2-capacity-perf-run2/`; artifact SHA list `artifact-sha256.txt`.
- C8 recheck (five trials): `/data/sglang-hicache/g2-quasar-runs/20261111T-g2-postrope-e5m2-capacity-perf-recheck/`, raw/summary nested under `perf-recheck/perf-recheck/`.
- Quality service exited after all 1,319 rows, then the concurrency-16 service and recheck also exited. Final checks: no listener on ports 31256/31257, GPU 1 MiB / 0%, exclusive lock available.
- Capacity/performance are descriptive only. No product acceptance threshold or quality-owner approval was available, and concurrency-8 performance remains unexplained. Full-set run did not retain per-kernel dispatch traces. No FP8/cache bug was confirmed and no shared dirty code was changed.
