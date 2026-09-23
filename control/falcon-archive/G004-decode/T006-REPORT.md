# G004 / T006 — Marlin Isolated Baseline Reproduction

## Verdict

```text
T006: PASS
ISOLATED MARLIN BASELINE: REPRODUCED
```

The isolated benchmark invoked the existing production
`gptq_marlin_gemm` binding and did not modify or copy the Marlin kernel. No
serving integration, scheduler change, graph-policy change, or optimization was
performed.

## Exact reconstructed object

Source/runtime reconstruction:

```text
Falcon hidden size K: 3072
Falcon FFN output size N: 12288
Decode M: B=8 and B=16
compute dtype: BF16
weight type: uint4b8 / GPTQ symmetric packed INT4
GPTQ group size: 128
desc_act / act-order: true
is_k_full: true
```

The existing production binding was called as:

```text
sglang.kernels.ops.quantization.gptq_marlin.gptq_marlin_gemm
```

with:

```text
size_m = 8 or 16
size_n = 12288
size_k = 3072
use_atomic_add = false
use_fp32_reduce = true
is_zp_float = false
```

Deterministic isolated inputs used the repository's existing `marlin_quantize`
helper and reference output (`a @ w_ref`). Weight/layout shapes:

```text
qweight:       [192, 24576]
scales:        [24, 12288]
g_idx:         [3072]
sort_indices:  [3072]
```

This corresponds to the production GPTQ-Marlin packed layout:

```text
K / 16 = 192
N * (32 / 4) = 24576
K / group_size = 24
```

The kernel dispatcher source explains the observed variants:

```text
M=8:  m_block_size_8 = true
M=16: m_block_size_8 = false
```

The exact captured symbols and launch geometry were:

```text
B=8:
void Marlin<__nv_bfloat16, 1125899907892224, 256, 1, 8, 8, 1, 4, 8, 0>(...)
82 x 1 x 1 blocks, 256 x 1 x 1 threads

B=16:
void Marlin<__nv_bfloat16, 1125899907892224, 256, 1, 8, 8, 0, 4, 8, 0>(...)
82 x 1 x 1 blocks, 256 x 1 x 1 threads
```

## Correctness and isolated timing

The harness performed 20 warmup calls and 50 timed calls through the same
binding. Reference comparison:

| Metric | B=8 | B=16 |
|---|---:|---:|
| Max absolute error | 0.5 | 1.0 |
| Relative mean absolute error | 1.90e-6 | 2.07e-6 |
| Harness mean event time | 0.895 us | 0.853 us |
| Harness min/max event time | 0.820–1.095 us | 0.778–1.055 us |

The isolated CUDA-event times are not comparable to serving or NCU kernel
durations and are not used as performance claims. The correctness gate passes:
relative error is approximately 2e-6 and matches the expected BF16/quantized
reference behavior.

## Production T004 vs isolated NCU baseline

NCU was run with privileged counters and the same basic/deep sections used for
T004. The first B=8 attempt used `application-only` and correctly produced no
report because the binding ran in a child process; it was discarded. The valid
runs used `--target-processes all`.

| Metric | T004 serving B=8 | T006 isolated B=8 | T004 serving B=16 | T006 isolated B=16 |
|---|---:|---:|---:|---:|
| Exact symbol variant | m_block_size_8=true | same | m_block_size_8=false | same |
| Grid/block | 82x256 | 82x256 | 82x256 | 82x256 |
| NCU kernel duration | 34.11–56.35 us | 32.96 us | 39.55–69.86 us | 39.52 us |
| Registers/thread | 96 | 96 | 148 | 148 |
| Dynamic shared memory | 101.38 KiB | same signature | 101.38 KiB | same signature |
| Achieved occupancy | 16.58–16.66% | same signature | 16.58–16.66% | same signature |
| Active warps/SM | ~7.96–8.00 | ~8.00 | ~7.96–8.00 | ~8.00 |
| DRAM throughput | 70.25–81.45% | 73.60% | 61.52–66.88% | 62.86% |
| Approx. DRAM bandwidth | 639–741 GB/s | 670.04 GB/s | 560–609 GB/s | 572.39 GB/s |
| L2 throughput | 35.37–42.13% | 36.86% | 37.16–41.10% | 37.44% |
| SM throughput | 25.74–29.15% | 26.64% | 27.13–30.51% | 26.72% |
| Eligible warps/scheduler | ~0.39 | 0.38 | ~0.30 | 0.29 |

Additional isolated NCU values:

```text
B=8:
  L2 hit rate: 22.63%
  memory busy: 36.86%
  issue slots busy: 31.58%

B=16:
  L2 hit rate: 35.60%
  memory busy: 37.44%
  issue slots busy: 24.70%
```

The isolated profiles reproduce the important production signature:

```text
same exact B-dependent Marlin symbols
same 82x256 geometry
same 96 vs 148 registers/thread split
same ~101.38 KiB shared-memory allocation
same ~16.6% occupancy
same ~8 active warps/SM
same substantial DRAM pressure
same B=16 lower DRAM percentage than B=8
same low eligible-warps behavior
same B-dependent duration increase relative to B=8
```

The isolated reports therefore reproduce the production resource behavior
closely enough to support controlled A/B kernel work.

## Reproduction decision

```text
ISOLATED MARLIN BASELINE: REPRODUCED
```

No mismatch requiring investigation remains. The discarded first B=8
`application-only` NCU attempt was a profiler child-process selection issue,
not a kernel or shape mismatch; the valid `target-processes all` rerun resolved
it without changing the benchmark invocation.

## T007 recommendation

The single first controlled optimization axis should be:

```text
shared-memory / tile-staging footprint and its occupancy consequence
```

Reason: both exact production variants allocate approximately 101.38 KiB per
block and are capped at approximately 16.6% occupancy, while the isolated
benchmark now provides a trustworthy correctness and resource-signature gate.
Any T007 change must remain offline first and preserve exact numerical parity
for both M=8 and M=16 before serving integration.

T007 was not executed.
