# G004 / T011 — System-Level Residual Decode Attribution

## Verdict

```text
T011: BLOCKED
SYSTEM-LEVEL ROOT CAUSE: NOT YET RESOLVED
```

The existing T003A SQLite artifacts were sufficient to rank residual GPU kernel
families, but not sufficient to produce a defensible steady-decode GPU-busy vs
CPU/replay-gap accounting. No workload was rerun, no serving configuration was
changed, and no optimization was executed.

## Artifact analysis

Used existing:

```text
runs/t003a/B8/server.sqlite
runs/t003a/B16/server.sqlite
```

The `CUPTI_ACTIVITY_KIND_KERNEL` table contains exact kernel chronology,
start/end timestamps, launch geometry, dynamic shared-memory metadata, and
kernel names. The capture has no explicit per-decode-step marker that cleanly
separates warmup, prefill, steady decode, request drain, and polling/lifecycle
intervals.

## Residual GPU-time ranking

The whole-capture kernel aggregation reproduces T003A and remains the strongest
reliable residual ranking:

### B=16

```text
Main GPTQ-Marlin:
  3.5870 s, 1936 calls, 48.1%

CUTLASS BF16 GEMM 256x128:
  0.9078 s, 1848 calls, 12.2%

BF16 GEMM ampere_bf16_s16816 256x128:
  0.5945 s, 440 calls, 8.0%

Mamba:
  _chunk_scan_fwd:       0.5646 s, 792 calls
  _chunk_state_fwd:      0.3244 s, 792 calls
  _state_passing_fwd:    0.1314 s, 792 calls
  _chunk_state_varlen:   0.0864 s, 792 calls
  additional Mamba:      approximately 0.10 s

Other visible residuals:
  act_and_mul:            0.1017 s, 1320 calls
  elementwise/multiply:   ~0.18 s combined across several families
  fused norm:             0.0729 s, 2640 calls
  FlashInfer ragged KV:   0.0771 s, 704 calls
  additional CUTLASS:     ~0.10 s combined
```

### B=8

```text
Main GPTQ-Marlin:
  3.5750 s, 1936 calls, 47.7%

CUTLASS BF16 GEMM 256x128:
  0.8403 s, 1760 calls

BF16 GEMM ampere_bf16_s16816 256x128:
  0.6750 s, 528 calls

Mamba:
  _chunk_scan_fwd:       0.5327 s, 792 calls
  _chunk_state_fwd:      0.3262 s, 792 calls
  _state_passing_fwd:    0.1291 s, 792 calls
  _chunk_state_varlen:   0.0815 s, 792 calls
  additional Mamba:      approximately 0.13 s
```

## Approximate component accounting

The following is a whole-capture GPU-kernel accounting, not a clean steady-step
accounting:

| Component | B=8 | B=16 | Interpretation |
|---|---:|---:|---|
| Main Marlin | 47.7% | 48.1% | stable dominant family |
| Other linear/BF16 GEMM | ~20% | ~20% | second-largest residual surface |
| Mamba families | ~17–20% | ~17–20% | stable substantial component |
| Attention/FlashInfer | remainder, individually small | remainder, individually small | no single Attention family dominates |
| Norm/elementwise/misc | remainder, distributed | remainder, distributed | many small kernels |
| runtime/graph gaps | not reliably separable | not reliably separable | artifact lacks clean step markers |

The largest residual surface after main Marlin is the combined BF16/CUTLASS GEMM
path, approximately 20% of whole-capture GPU kernel time. Mamba is substantial
but distributed and does not overtake the combined residual GEMM family.
Attention kernels visible in the ranking are individually much smaller.
Elementwise/norm work is nontrivial in aggregate but fragmented across many
small launches.

The exact mapping of every CUTLASS kernel to Falcon Attention versus Mamba/FFN
cannot be established solely from symbol names; the report therefore does not
claim a finer model-component attribution than `other linear/BF16 GEMM`.

## Timeline/gap analysis and limitation

A read-only kernel interval analysis was attempted over the middle 60% of each
capture. It showed that raw wall-span gap percentages are dominated by long
unlabeled intervals and capture lifecycle/request-drain structure rather than a
clean repeated decode-step boundary. Depending on treating overlapping/serial
intervals and lifecycle gaps, the apparent idle fraction changes materially.

Therefore these values are not accepted as steady decode gap measurements:

```text
B=8/B=16 raw timeline gap estimate: contaminated by lifecycle/step-boundary ambiguity
CPU→CUDA graph replay gap: not defensibly quantified
GPU idle ratio for steady decode: not established
```

This is consistent with T003A's warning that process-wide CUDA API summaries
cannot be converted directly into critical-path timing. `cudaGraphLaunch`,
`cudaEventSynchronize`, and memcpy summaries remain process-wide observations,
not a per-step replay accounting.

What can be stated:

```text
CUDA graphs are active.
The kernel chronology is available.
A clean steady-decode marker/interval is missing.
The artifact cannot distinguish short replay gaps from request/lifecycle gaps
with the required confidence.
```

The approximately 98% `nvidia-smi` GPU-utilization evidence also does not close
this distinction: it excludes long starvation as the dominant explanation but
does not quantify high-frequency short gaps.

## B=8 → B=16 scaling

Reliable whole-capture observations:

```text
Main Marlin aggregate:
  approximately flat: 3.575 s → 3.587 s
  same 1936 calls

Other GEMM:
  remains approximately 20% combined

Mamba:
  remains approximately 17–20%
  individual chunk families have similar call counts and comparable aggregate
  time across B values

Attention/elementwise/norm:
  remain distributed residuals
```

The throughput change:

```text
B=8:  approximately 397 tok/s
B=16: approximately 460 tok/s
```

is therefore not explained by a single newly dominant residual component in the
available whole-capture artifacts. The supported system-level model remains a
mixed/distributed GPU roof:

```text
Marlin ~48%
combined other GEMM ~20%
Mamba ~17–20%
remaining distributed Attention/norm/elementwise/misc
```

Runtime/graph-gap contribution remains unresolved, not demonstrated as
significant.

## Candidate selection

No single residual component meets the evidence threshold for an optimization
handoff with clean critical-path attribution:

- Combined BF16/CUTLASS GEMM is the largest residual GPU-time surface, but its
  exact Falcon component mapping and steady-step share are not isolated.
- Mamba is substantial, but no evidence shows it is the next dominant surface
  after accounting for the combined GEMM path.
- Attention is not individually dominant in the available ranking.
- Norm/elementwise work is distributed across many small kernels.
- Runtime/graph gaps cannot be separated from lifecycle intervals in this
  artifact.

Therefore no next optimization surface is authorized by T011.

## Final status

```text
T011: BLOCKED
SYSTEM-LEVEL ROOT CAUSE: NOT YET RESOLVED
```

The next useful evidence would require a separately authorized minimal capture
with an explicit steady-decode marker/interval or equivalent per-step telemetry;
this task does not perform that capture.
