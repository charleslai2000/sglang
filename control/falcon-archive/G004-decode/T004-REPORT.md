# G004 / T004 — GPTQ-Marlin Targeted Deep Profile

## 1. Verdict

```text
T004: PASS
MARLIN ROOT CAUSE: MIXED
```

The selected Marlin kernel was captured at B=8 and B=16 with Nsight Compute
2025.2.1, while decode CUDA graphs remained active. Both workloads completed
normally. No optimization or production execution change was made.

## 2. Target kernel

The T003A-selected family was used exclusively:

```text
sglang::device::marlin::Marlin<__nv_bfloat16, ...>
```

Representative exact demangled forms in the reports:

```text
B=8:
void Marlin<__nv_bfloat16, 1125899907892224, 256, 1, 8, 8, 1, 4, 8, 0>(...)

B=16:
void Marlin<__nv_bfloat16, 1125899907892224, 256, 1, 8, 8, 0, 4, 8, 0>(...)
```

Filter:

```text
--target-processes all
--kernel-name-base demangled
--kernel-name 'regex:.*sglang::device::marlin::Marlin.*'
--launch-count 2
```

Sections collected:

```text
SpeedOfLight
LaunchStats
Occupancy
ComputeWorkloadAnalysis
MemoryWorkloadAnalysis
SchedulerStats
WarpStateStats
```

Reports:

```text
runs/t004-B8.ncu-rep: 14,249,148 bytes
runs/t004-B16.ncu-rep: 14,251,774 bytes
```

## 3. Workload and runtime evidence

Both captures used the frozen runtime configuration:

```text
Falcon-H1-7B-Instruct-GPTQ-Int4
GPTQ-Marlin
Mamba extra_buffer
prefill CUDA graph disabled
decode CUDA graph full
HiCache off/default
speculative decoding off
```

Workload results:

```text
B=8:
  48/48 completed
  client errors: 0
  output tokens: 12288
  workload wall time under NCU: 391.63 s

B=16:
  48/48 completed
  client errors: 0
  output tokens: 12288
  workload wall time under NCU: 224.69 s
```

Runtime logs retained the intended graph path:

```text
B=8:  Decode batch ... #running-req: 8 ... cuda graph: True ... queue=0
B=16: Decode batch ... #running-req: 16 ... cuda graph: True ... queue=0
```

The long profiled wall times are expected from replay-based NCU collection and
are not performance benchmark results.

## 4. Representative NCU comparison

The reports contain two representative matched Marlin invocations per batch.
The values below show both samples where duration varied materially; they are
not collapsed into a misleading single average.

| Metric | B=8 sample 1 | B=8 sample 2 | B=16 sample 1 | B=16 sample 2 |
|---|---:|---:|---:|---:|
| Kernel duration (us) | 56.35 | 34.11 | 69.86 | 39.55 |
| Grid | 82x1x1 | 82x1x1 | 82x1x1 | 82x1x1 |
| Block | 256x1x1 | 256x1x1 | 256x1x1 | 256x1x1 |
| Registers/thread | 96 | 96 | 148 | 148 |
| Dynamic shared memory/block | 101.38 KiB | 101.38 KiB | 101.38 KiB | 101.38 KiB |
| Theoretical occupancy | 16.67% | 16.67% | 16.67% | 16.67% |
| Achieved occupancy | 16.66% | 16.58% | 16.66% | 16.58% |
| Active warps/SM | 8.00 | 7.96 | 8.00 | 7.96 |
| DRAM throughput | 81.45% | 70.25% | 66.88% | 61.52% |
| Approx. DRAM bandwidth | 741.34 GB/s | 639.06 GB/s | 609.36 GB/s | 559.74 GB/s |
| L2 throughput | 42.13% | 35.37% | 41.10% | 37.16% |
| Compute/SM throughput | 29.15% | 25.74% | 30.51% | 27.13% |
| HMMA tensor instruction activity | 10.81% | not separately retained | 16.46% | not separately retained |
| Eligible warps/cycle | 0.39 | not separately retained | 0.30 | not separately retained |

The exact B=8/B=16 launch geometry is unchanged in these captures. The kernel
variant changes a template parameter and B=16 uses substantially more registers
(148 vs 96), but shared memory remains the occupancy limiter in both cases.

Dominant sampled stall values:

| Stall metric (per active issue) | B=8 | B=16 |
|---|---:|---:|
| Math-pipe throttle | ~1.21 | ~3.63 |
| Long scoreboard | ~1.26 | ~0.49 |
| Barrier | ~1.13 | ~0.77 |
| Wait | ~0.83 | ~0.90 |
| Not selected | ~0.21 | ~0.16 |
| LG throttle | 0.00 | 0.00 |

The B=16 result shifts toward math-pipe throttling, while B=8 shows more long
scoreboard pressure. Neither result shows a single exclusive stall class that
would justify a pure compute or pure memory label.

## 5. Explanation of T003A near-flat aggregate time

T003A reported:

```text
B=8:  3.575 s / 1936 instances
B=16: 3.587 s / 1936 instances
```

The targeted profile shows why this must not be interpreted as batch-independent
Marlin cost:

```text
1. The per-invocation durations are not flat:
   B=8 samples: 34.11–56.35 us
   B=16 samples: 39.55–69.86 us

2. Grid and block geometry remain 82 blocks x 256 threads for both B values.
   Therefore configured batch doubling does not double the reported grid.

3. The B=8 and B=16 symbols are different template variants. B=16 uses 148
   registers/thread versus 96 at B=8, while both variants use the same
   101.38 KiB dynamic shared-memory allocation and one wave per SM.

4. The T003A totals are whole-capture Nsight Systems aggregation over the same
   1936 matched instances, including lifecycle/prefill/drain context. They are
   not a steady-decode-only integral. Equal instance counts and unchanged grid
   shape make near-flat aggregate totals plausible even though individual
   launches have different duration and resource behavior.
```

Thus the evidence supports a fixed/quantized tile and work-mapping shape with
B-dependent kernel variant/resource behavior, combined with whole-capture
aggregation effects. It does not support the claim that Marlin work is
independent of batch size.

## 6. Final Marlin attribution

```text
MARLIN ROOT CAUSE: MIXED
```

Decision evidence:

```text
Occupancy/latency constraint:
  achieved occupancy is only ~16.6%
  active warps are ~8/SM
  shared memory is ~101.38 KiB/block and is the occupancy limit
  eligible warps are low (~0.39 B8, ~0.30 B16)

Memory pressure:
  DRAM is substantial (~61.5–81.5% of sustained peak)
  L2 throughput is ~35–42%
  long-scoreboard stalls exist, especially at B8

Compute pressure:
  SM throughput is only ~25.7–30.5%
  B16 math-pipe throttle rises to ~3.6
  HMMA activity is visible but not near a demonstrated device-wide ceiling
```

Because low occupancy/shared-memory pressure, substantial DRAM activity, and
B-dependent math-pipe/scoreboard stalls coexist, the strongest supported label
is mixed. The data does not justify declaring Marlin purely
memory-bandwidth-bound or purely compute-bound.

## 7. G004-level implication

```text
Marlin is sufficient to explain the main decode roof as the dominant internal
component, but it is not proven to be the sole system-level limiter.
```

Basis:

```text
main Marlin family: ~47.7–48.1% of GPU kernel time in T003A
Marlin + related linear/GEMM paths: ~60–65%
T004 confirms low occupancy and material DRAM/compute pressure inside Marlin
```

This makes Marlin the highest-value next optimization surface for the
approximately 460–500 tok/s saturation region, while leaving the remaining
linear/GEMM, Mamba, and runtime contributions unresolved.

## 8. Evidence-backed candidates — not executed

Only these candidates are justified for later owner-authorized work:

1. **Investigate shared-memory/occupancy constraints in the selected Marlin
   variant.** Both B values allocate ~101.38 KiB dynamic shared memory and are
   limited to ~16.6% occupancy; any change must preserve the production graph
   and be validated rather than assumed beneficial.

2. **Investigate the B-dependent Marlin template/register/work mapping.** B=8
   uses 96 registers/thread while B=16 uses 148, with identical 82x256 launch
   geometry and a near-flat whole-capture aggregate. This is the strongest
   concrete lead for explaining batch scaling and should be tested with a
   separate authorized experiment.

No candidate was implemented or benchmarked in T004.

## Final status

```text
T004: PASS
formal B=8/B=16 targeted Marlin profile complete
no optimization executed
stop for owner review
```
