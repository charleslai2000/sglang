# G004 / T002 — Decode Saturation Attribution

## Status

```text
T001 baseline: PASS
T002 first-layer attribution: COMPLETE
ROOT CAUSE: NOT YET RESOLVED
```

No optimization or execution-behavior change was made. Nsight kernel tracing was
not run because this first resource layer does not yet uniquely distinguish
compute, bandwidth, and kernel/runtime causes.

## 1. Correction to B=12 baseline semantics

The existing B=12 traces were reanalyzed offline. All three measured reps have
this same shape:

```text
initial partial batch 8
contiguous full-load batch 12
final partial batch 8
```

Observed runs:

```text
rep1: 8×10, 12×118, 8×31
rep2: 8×7,  12×118, 8×29
rep3: 8×8,  12×118, 8×34
```

This is explained by the 32-request workload at client concurrency 12:

```text
12 + 12 + 8
```

There is no observed mid-run `12 → 8 → 12` recovery. The previous report's
“oscillation” wording is corrected to:

```text
final/initial partial-drain artifact
steady full-load batch = 12
```

This correction does not change the main B=16 finding: B=16 reached actual
full batch 16 without observed underfill.

## 2. Attribution workload and window

For attribution only, the request count was changed to 48 so B=8/12/16 all have
full-batch waves without a final remainder:

```text
48 requests
approximately 405-token fixed prompts
max_new_tokens=256
same generation parameters and production-safe runtime
one warmup + three measured reps per B
```

The low-intrusion resource poller sampled every 100 ms:

```text
decode_batch_size
decode_sum_seq_lens
num_running_reqs
num_queued_reqs
GPU utilization
memory-controller utilization
power
SM clock
memory clock
VRAM usage
```

The reported resource values are the samples for the full configured decode
batch (`decode_batch_size == B`) during the active decode window. They are not
whole-server lifetime averages.

All attribution measured reps completed:

```text
B=8:  48/48 × 3, errors=0
B=12: 48/48 × 3, errors=0
B=16: 48/48 × 3, errors=0
```

## 3. Aligned resource table

Values are means across the three measured reps and the full-batch steady
samples.

| B | aggregate output tok/s | actual batch | decode_sum_seq_lens | GPU util | memory util | power | SM clock | memory clock | VRAM |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 8 | 335.54 | 8 | not reduced to single summary | 98.59% | 70.31% | 345.87 W | 1788 MHz | 9501 MHz | 21618 MiB |
| 12 | 409.27 | 12 | not reduced to single summary | 97.87% | 67.39% | 344.85 W | 1753 MHz | 9501 MHz | 21620 MiB |
| 16 | 464.40 | 16 | not reduced to single summary | 97.96% | 66.33% | 344.11 W | 1741 MHz | 9501 MHz | 21622 MiB |

`decode_sum_seq_lens` was recorded in the raw samples but is not collapsed here
because its value varies with prompt/output lifecycle and is not itself a
resource-utilization metric. Raw aligned samples are retained in the run
artifacts.

Relative to B=8, throughput rises approximately:

```text
B=8 → B=12: +21.99%
B=12 → B=16: +13.48%
```

The 48-request attribution workload is not directly comparable in absolute TPS
to the 32-request T001 baseline because its full-wave lifecycle is different;
its resource comparisons are the intended output.

## 4. Resource interpretation

Observed:

```text
GPU utilization: approximately 98% at all B
memory-controller utilization: approximately 66–70%
power: approximately 344–346 W at all B
memory clock: stable at 9501 MHz
SM clock: decreases from approximately 1788 MHz at B=8 to 1741 MHz at B=16
VRAM: stable at approximately 21.6 GiB
```

Consequences:

1. Scheduler underfill is not the leading explanation in this window: actual
   batches are full at 8/12/16.
2. The GPU is clearly busy at all three batch sizes; this is not an idle-GPU
   or obvious CPU starvation result.
3. Memory-controller utilization is not near an apparent 100% ceiling, while
   GPU utilization is near 98%. This points away from a simple DRAM-bandwidth
   saturation claim, but does not prove compute-bound behavior: `nvidia-smi`
   utilization is too coarse to identify tensor/SM issue mix or stalls.
4. Power is near the observed 344–346 W throughout, and SM clock falls as batch
   increases. This is consistent with a power/thermal/clock-limited or mixed
   compute/runtime regime, but the samples alone do not establish the exact
   limiting mechanism.
5. VRAM capacity is not the active limiter in these samples.

## 5. Kernel/runtime attribution

Not run in this stage.

Therefore the following shares are not available:

```text
GPTQ-Marlin FFN GPU-time share: not collected
Attention decode GPU-time share: not collected
Falcon-H1 Mamba GPU-time share: not collected
norm/elementwise/other kernel share: not collected
CPU→CUDA launch gap: not collected
CUDA graph replay timeline: not collected
GPU idle gap: not collected
```

The current evidence cannot distinguish uniquely between:

```text
compute-bound
kernel/runtime-bound
mixed compute + runtime
```

It does not support declaring memory-bandwidth-bound or scheduler/batching-bound
as the primary cause.

## 6. Root cause

```text
ROOT CAUSE NOT YET RESOLVED
```

Supported findings:

```text
actual full batch grows 8 → 12 → 16
B=16 has no observed scheduler underfill
GPU utilization is approximately 98%
power is approximately 344–346 W
memory-controller utilization is approximately 66–70%
SM clock declines as batch grows
```

The remaining decisive evidence is a low-intrusion timeline/kernel breakdown for
B=8/12/16, separated from benchmark TPS. It must show whether the dominant
execution time is GPTQ-Marlin FFN, Mamba, attention, or launch/idle/runtime gap.

## 7. Next candidates — not executed

1. Run a separate low-intrusion Nsight Systems/timeline attribution on B=8/12/16
   using the 48-request full-wave workload, focusing on CUDA graph replay,
   CPU→CUDA gaps, GPU idle gaps, and component-level scheduling intervals.
2. If one dominant kernel family is identified but its bound is ambiguous, run
   the smallest targeted kernel profile at B=8 and B=16 only, inspecting SM
   issue/utilization, DRAM bandwidth, occupancy, and stall reasons.

No optimization should be attempted until that attribution evidence exists.

## Artifacts

```text
control/G004-falcon-h1-decode-saturation/attribution_run.py
control/G004-falcon-h1-decode-saturation/runs/attribution/B8/
control/G004-falcon-h1-decode-saturation/runs/attribution/B12/
control/G004-falcon-h1-decode-saturation/runs/attribution/B16/
```
