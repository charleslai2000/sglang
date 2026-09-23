# G004 / T009 — M=16 Alternative Marlin Specialization A/B

## Verdict

```text
T009: NEGATIVE
ALTERNATIVE SPECIALIZATION: REGRESSIVE
```

The existing B=8 specialization can legally cover a complete M=16 operation by
splitting the activation rows into two independent M=8 operations and
concatenating rows 0–7 and 8–15. Correctness passed, but the complete-operation
cost was substantially worse than the current M=16 specialization. No serving
integration or production dispatch change was made.

## 1. Alternative work mapping

Current path:

```text
one call:
  A shape = [16, 3072]
  existing m_block_size_8=false specialization
  output rows = [0:16, 12288]
```

Alternative path:

```text
call 1:
  A[0:8] shape = [8, 3072]
  existing m_block_size_8=true specialization
  output rows 0:8

call 2:
  A[8:16] shape = [8, 3072]
  existing m_block_size_8=true specialization
  output rows 8:16

final output = cat(output0, output1, dim=0)
```

Both calls reuse the existing production binding, quantized layout, scale/
act-order tensors, and `is_k_full=true` semantics. No new kernel was designed.

## 2. Correctness gate

Deterministic T006-equivalent M=16 shape:

```text
M=16, N=12288, K=3072
BF16 activation
uint4b8 GPTQ
group_size=128
act_order=true
```

Results:

| Metric | Current M=16 | Alternative 2×M=8 |
|---|---:|---:|
| Max absolute error | 1.0 | 1.0 |
| Relative mean absolute error | 2.068e-6 | 2.068e-6 |
| Repeated runs exact deterministic | yes | yes |
| Complete rows covered | rows 0–15 | rows 0–7 + 8–15 |
| Work units | 1 | 2 |

Correctness gate:

```text
PASS
```

No illegal access, race, overwrite, missing row, or duplicate accumulation was
observed.

## 3. Complete-operation cost

The comparison includes all work needed to produce the complete M=16 output.

Isolated CUDA-event timing over 30 iterations:

| Metric | Current M=16 | Alternative 2×M=8 |
|---|---:|---:|
| Mean total time | 124.50 us | 269.90 us |
| Minimum | 102.40 us | 219.14 us |
| Maximum | 200.61 us | 376.35 us |
| Relative cost | 1.00× | 2.17× |

These event timings are isolated-operation comparisons only; they are not
serving throughput claims.

## 4. NCU comparison

Current M=16 captured one Marlin launch:

```text
symbol: Marlin<..., 256, 1, 8, 8, false, 4, 8, false>
grid/block: 82x1x1 / 256x1x1
registers/thread: 148
dynamic launch allocation: 101.38 KiB
duration: 39.62 us
achieved occupancy: 16.66%
active warps/SM: 8.00
eligible warps/scheduler: 0.29
SM throughput: 26.62%
DRAM throughput: 62.58%
DRAM bandwidth: 569.24 GB/s
L2 throughput: 37.37%
```

Alternative captured two Marlin launches, one per M=8 work unit:

```text
symbol: Marlin<..., 256, 1, 8, 8, true, 4, 8, false>
grid/block: 82x1x1 / 256x1x1 per launch
registers/thread: 96
dynamic launch allocation: 101.38 KiB per launch
durations: 33.41 us and 32.86 us
achieved occupancy: 16.66% per launch
active warps/SM: 8.00 per launch
eligible warps/scheduler: 0.38 per launch
SM throughput: 25.70–26.58%
DRAM throughput: 72.49–73.69%
DRAM bandwidth: 659.50–670.43 GB/s
L2 throughput: 36.37–37.05%
```

Dominant stalls:

| Stall | Current M=16 | Alternative M=8 units |
|---|---:|---:|
| Math-pipe throttle | ~3.52 | ~1.20 each |
| Long scoreboard | ~0.57 | ~1.17–1.20 each |
| Barrier | ~0.92 | ~1.24–1.26 each |
| Wait | ~0.94 | ~0.88 each |
| Not selected | ~0.16 | ~0.21 each |

The alternative does reduce registers and math-pipe throttle per launch, and
raises eligible warps from ~0.29 to ~0.38. However, it requires two complete
M=8 operations, doubles the launch/work-unit count, raises aggregate DRAM
traffic exposure, and has higher barrier/long-scoreboard pressure per unit.
Those gains do not compensate for the two-unit decomposition cost.

## 5. Final conclusion

```text
ALTERNATIVE SPECIALIZATION: REGRESSIVE
```

The existing `m_block_size_8=true` specialization is legally reusable for M=16
only through a two-work-unit decomposition. That decomposition is numerically
correct and improves the local per-launch register/eligibility signature, but
its complete M=16 cost is approximately 2.17× the current one-launch path.

Therefore it is not a candidate for production-dispatch canary in its tested
form. Candidate #2 is resolved negatively for this straightforward legal
mapping; no further specialization forcing is recommended without a different
existing work mapping that avoids the two-unit cost.

No production code or dispatch was modified.
