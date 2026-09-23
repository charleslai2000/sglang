# G004 / T001 — Decode Saturation Baseline

## Status

```text
BASELINE COMPLETE
ATTRIBUTION NOT STARTED
```

No production behavior or scheduler code was modified. No GPU/kernel attribution
profiler was run.

## 1. Harness

Runtime:

```text
Falcon-H1-7B-Instruct-GPTQ-Int4
RTX 3090 24GB
GPTQ-Marlin
BF16 Attention and Mamba
Mamba extra_buffer
prefill CUDA graph disabled
decode CUDA graph full
HiCache OFF
speculative decoding OFF
context 8192
seed 20260921
```

Workload:

```text
fixed materialized prompt: approximately 405 tokens after server tokenization
max_new_tokens: 256
sampling: temperature=0, top_p=1, skip_special_tokens=false
request count: 32 per run
client concurrency B: 1, 2, 4, 8, 12, 16
one warmup + three measured repetitions per B
```

`B` is client-side active concurrency. It is not assumed to equal the actual
scheduler decode batch. A 100 ms poller sampled `/metrics` throughout each
run and persisted timestamped values for:

```text
decode_batch_size
decode_sum_seq_lens
num_running_reqs
num_queued_reqs
```

Every measured run completed 32/32 requests with zero client errors and 8192
total output tokens.

## 2. Steady decode window

For this first baseline, the analysis window is the contiguous active decode
observation set: samples with `decode_batch_size > 0`, from the first observed
active decode sample through the final active sample before the gauge returned
to zero. Samples with zero decode batch were excluded as idle before admission
or after final drain.

This is a gauge-sampled approximation, not a per-decode-step trace. The 100 ms
sampling interval can miss short transitions. It is sufficient for the large
B=1/2/4/8/16 batch modes and, after offline sequence analysis, identifies the
B=12 initial/final partial waves. It should not be used as kernel attribution
evidence.

## 3. Baseline table

Aggregate output throughput is `8192 / wall_time`.

| B | rep1 tok/s | rep2 tok/s | rep3 tok/s | mean tok/s | run-to-run range |
|---:|---:|---:|---:|---:|---:|
| 1 | 68.73 | 68.70 | 68.66 | 68.69 | 0.07 |
| 2 | 116.15 | 117.02 | 122.86 | 118.68 | 6.72 |
| 4 | 236.22 | 222.08 | 222.49 | 226.93 | 14.14 |
| 8 | 395.77 | 401.41 | 393.93 | 397.04 | 7.48 |
| 12 | 433.35 | 438.50 | 425.58 | 432.48 | 12.92 |
| 16 | 460.96 | 459.77 | 457.86 | 459.53 | 3.10 |

All values are aggregate output tok/s over the complete 32-request run. They
are not profiler-disturbed measurements.

## 4. Actual decode-batch evidence

| B | steady samples / rep | batch mean | median | min | max | distribution |
|---:|---:|---:|---:|---:|---:|---|
| 1 | 995–1005 | 1.00 | 1 | 1 | 1 | 100% B=1 |
| 2 | 572–588 | 2.00 | 2 | 2 | 2 | 100% B=2 |
| 4 | 298–309 | 4.00 | 4 | 4 | 4 | 100% B=4 |
| 8 | 174–175 | 8.00 | 8 | 8 | 8 | 100% B=8 |
| 12 | 154–160 | 10.95–11.06 | 12 | 8 | 12 | B=8: 36–42 samples; B=12: 118 samples |
| 16 | 148–149 | 16.00 | 16 | 16 | 16 | 100% B=16 |

`decode_sum_seq_lens` ranges across the three measured repetitions:

| B | mean range across reps | observed min–max range |
|---:|---:|---:|
| 1 | 951.25–951.46 | 817–1065 |
| 2 | 1905.02–1917.04 | 1634–2130 |
| 4 | 3815.65–3836.29 | 3268–4260 |
| 8 | 7657.65–7693.89 | 6536–8520 |
| 12 | 10605.99–10809.61 | 6600–12780 |
| 16 | 15695.14–15894.05 | 13072–17040 |

The B=12 sequence is a request-count shape artifact, not established scheduler
oscillation. Each measured rep has the same structure: an initial partial batch
of 8, then a contiguous full-load batch of 12, then a final partial batch of 8.
This matches 32 requests at client concurrency 12 (`12 + 12 + 8`). There is no
observed mid-run `12 → 8 → 12` recovery. The correct steady full-load batch is
12. B=16 does not show underfill in this baseline; it remains at actual batch 16
throughout the full-load portion.

## 5. B=12 → B=16 finding

Configured concurrency and observed batch behavior:

```text
B=12:
  actual batch: 8 or 12
  mean: approximately 11.0
  oscillation: present

B=16:
  actual batch: 16
  mean: 16.0
  underfill: not observed
  oscillation: not observed in sampled gauge
```

Therefore:

```text
B=12 → B=16 does continue to increase actual decode batch.
```

The throughput increase from this fixed baseline is nevertheless modest:

```text
B=12 mean: 432.48 tok/s
B=16 mean: 459.53 tok/s
change: approximately +6.3%
```

This baseline does not support a scheduler-underfill explanation for the B=16
plateau. It does show that B=12 has a batch-formation/lifecycle oscillation,
which should be separated from GPU saturation in later analysis.

The baseline does not establish whether the B=16 limit is compute-bound,
bandwidth-bound, launch-bound, or a mixed GPU/runtime effect. No attribution
was performed by instruction.

## 6. Observability verdict

```text
BATCH OBSERVABILITY: SUFFICIENT for baseline batch-shape classification
```

The existing gauge time series is sufficient to establish:

```text
B=1/2/4/8: full configured batch
B=12: oscillation between 8 and 12
B=16: full configured batch
```

It is not per-decode-step telemetry and is not sufficient for precise short-lived
batch transitions or GPU/kernel attribution. No source telemetry patch was
added because the requested baseline question is answerable with the existing
poll sequence.

## 7. Runtime checks

```text
all measured points: 32/32 requests completed
client errors: 0
CUDA/runtime errors observed: 0
scheduler crash/deadlock observed: 0
```

## 8. Next step recommendation

```text
proceed to GPU/kernel attribution
```

The next attribution should focus on B=8, B=12, and B=16 with synchronized
steady-window GPU utilization, memory-controller/DRAM utilization, clocks,
power, VRAM, kernel mix, and scheduler/CPU gap evidence. The B=12 initial/final batch-8 partial waves are a request-count lifecycle
artifact, not established scheduler oscillation. No scheduler change is
authorized from this baseline.

## Artifacts

```text
control/G004-falcon-h1-decode-saturation/decode_baseline.py
control/G004-falcon-h1-decode-saturation/runs/baseline/B1/
control/G004-falcon-h1-decode-saturation/runs/baseline/B2/
control/G004-falcon-h1-decode-saturation/runs/baseline/B4/
control/G004-falcon-h1-decode-saturation/runs/baseline/B8/
control/G004-falcon-h1-decode-saturation/runs/baseline/B12/
control/G004-falcon-h1-decode-saturation/runs/baseline/B16/
```
