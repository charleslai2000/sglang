# Gemma4 Radix 8K — c16/c24/c32 Percentile Closure (2026-10-31)

## Provenance and method

Offline reanalysis only; no GPU or service rerun. Source run: `/data/sglang-hicache/gemma4/runs/20261031T145717Z-radix8k-prefix-benchmark/`; base measurement configuration and identity are in `../gemma4-e4b-rtx3090-radix-8k-perf/runs/GEMMA4-RADIX-8K-REAL-DECODE-BATCH-16-24-32-20261031.md`.

Request latency percentiles use all measured-round request samples (warmup excluded), with linear interpolation at `(n-1)q`. GPU per-step CUDA Event timing has 768 events per concurrency (256 decode events × 3 measured rounds). Individual Event timings are *not* step observations for percentile claims: the event queue can report overlapping/queued execution intervals and does not expose scheduler launch-step identity. The archived CUDA Events therefore only support aggregate Decode-only TPS and per-round mean GPU Event time / 256 steps. The P50/P95 values below for GPU Forward are percentiles across the **three round-level mean times**, not across 768 event times; `n=3` is explicitly shown and has limited statistical resolution. They estimate a sustained mean decode-step event interval per round, not a per-step latency distribution. No per-step Scheduler Forward wall latency samples were archived.

## Performance and latency percentiles

| Actual GPU Decode batch | Output TPS mean ± sample SD | Decode-only CUDA Event aggregate TPS | GPU Decode Forward event mean per step (ms; n=3 round means) | Round-mean P50 / P95 (ms) | TPOT P50 / P95 (ms; n requests) | TTFT P50 / P95 (s; n requests) | E2E P50 / P95 (s; n requests) |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 16 | 653.47 ± 1.76 | 1,200.07 | 13.333 | 13.335 / 13.355 | 17.117 / 21.908 (48) | 1.832 / 2.688 (48) | 6.195 / 6.226 (48) |
| 24 | 670.44 ± 1.09 | 1,270.32 | 18.893 | 18.897 / 18.914 | 25.597 / 32.384 (72) | 2.544 / 4.095 (72) | 9.079 / 9.107 (72) |
| 32 | 727.54 ± 0.30 | 1,496.71 | 21.380 | 21.373 / 21.400 | 31.000 / 40.523 (96) | 3.250 / 5.483 (96) | 11.153 / 11.184 (96) |

TPOT P50/P95 is the response-metadata `tpot_s` distribution over measured requests. TTFT is `first_token_ts - request_received_ts`. E2E uses `e2e_latency`. Output TPS remains round wall completion throughput; Decode-only TPS remains sum(decode-token positions)/sum(CUDA Event seconds), not wall-time throughput.

## Batch and graph shape evidence

- Scheduler emitted active decode batch 16, 24, and 32 with `cuda graph: True` for 26, 25, and 26 log records respectively; no `cuda graph: False` record at these sizes. These log counts include warmup, validation-side effects where applicable, and measured work; they are execution-step records, not unique graph counts.
- Request-linked Decode CUDA Event logs show exactly 768 measured events at each target batch: c16 `{16: 768}`, c24 `{24: 768}`, c32 `{32: 768}`. Thus observed decode event batch distributions are exact target-size only for the measured rounds.
- Resolved capture buckets were `[1,2,4,8,12,16,24,32]`, graph max batch 32. The base runner's decode code pads raw batch size to the smallest capture bucket >= raw size; for observed raw sizes 16/24/32 this selects 16/24/32, so graph batch padding is 0 requests (`padded_bs == raw_bs`). Startup log confirms capture at 24 and 32 completed successfully. These run logs establish scheduler graph eligibility (`cuda graph: True`), batch identities, and that captures succeeded; they do not expose an individual opaque CUDA graph handle/ShapeKey ID or per-replay graph pointer. We therefore do not claim a graph identity beyond the exact bucket selected by the inspected source logic and recorded batch.
- c24/c32 are actual scheduler/GPU batches, not client concurrency alone. No queued aggregate is substituted.

## Resources and boundaries

The same run reports KV full pool=141,471 tokens, SWA pool=113,176 tokens, effective `max_running_requests=32`, and post-capture available memory 2.14 GiB. GPU polling sampled 23,437 MiB peak used (355 samples), leaving at least 1,139 MiB below 24,576 MiB total at the sampled peak; sampling is every 500 ms, so a shorter transient may be missed. After shutdown it returned to 1 MiB used. No OOM, retraction, request failure, or eager Decode fallback was observed.

No Nsight profiling was conducted; do not infer a bottleneck from these metrics. G1 remains **FAILED / NOT ACCEPTED**.

## Reproducibility

Run `python3 control/gemma4-e4b-rtx3090-radix-8k-perf-percentiles/runs/derive_real_batch_percentiles.py /data/sglang-hicache/gemma4/runs/20261031T145717Z-radix8k-prefix-benchmark/` to recompute request percentiles and the measured round-level event summaries. Event summary is independently reproducible with the existing event parser at the path documented in the real-batch report.
