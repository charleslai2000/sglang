# G004 / T005 — Marlin Optimization Candidate Selection

## Verdict

```text
T005: PASS
No experiment run; no code or production configuration changed.
```

## Decisive B=8 vs B=16 evidence

| Metric | B=8 | B=16 |
|---|---:|---:|
| Kernel duration, captured samples | 34.11–56.35 us | 39.55–69.86 us |
| Grid / block | 82x1x1 / 256x1x1 | 82x1x1 / 256x1x1 |
| Registers/thread | 96 | 148 |
| Dynamic shared memory/block | 101.38 KiB | 101.38 KiB |
| Achieved occupancy | 16.58–16.66% | 16.58–16.66% |
| Active warps/SM | ~7.96–8.00 | ~7.96–8.00 |
| SM throughput | 25.74–29.15% | 27.13–30.51% |
| HMMA activity | ~10.81% sample | ~16.46% sample |
| DRAM throughput | 70.25–81.45% | 61.52–66.88% |
| Approx. DRAM bandwidth | 639–741 GB/s | 560–609 GB/s |
| L2 throughput | 35.37–42.13% | 37.16–41.10% |
| Eligible warps/cycle | ~0.39 | ~0.30 |

Dominant sampled stalls:

```text
B=8:  math-pipe ~1.21, long-scoreboard ~1.26, barrier ~1.13, wait ~0.83
B=16: math-pipe ~3.63, long-scoreboard ~0.49, barrier ~0.77, wait ~0.90
```

## Why the attribution is MIXED

Three visible constraints coexist:

1. **Occupancy/latency constraint:** both variants consume approximately
   101.38 KiB dynamic shared memory per block, making shared memory the
   occupancy limiter. Achieved occupancy is only approximately 16.6%, with
   approximately eight active warps per SM and low eligible-warps values.

2. **Memory pressure:** DRAM activity is substantial, approximately 61.5–81.5%
   of sustained peak, with L2 throughput around 35–42% and measurable
   long-scoreboard stalls. DRAM is not demonstrably at a hard platform ceiling,
   so `MEMORY-BANDWIDTH-BOUND` alone is not supported.

3. **Compute/dependency pressure:** SM throughput is only approximately
   25.7–30.5%, but B=16 shows materially higher math-pipe throttle (~3.63 vs
   ~1.21) and visible HMMA activity. The compute pipeline is not demonstrated
   to be globally saturated, so `COMPUTE-BOUND` alone is not supported.

The evidence therefore supports:

```text
MARLIN ROOT CAUSE: MIXED
```

It does not support a pure compute, pure DRAM-bandwidth, or pure
occupancy/latency label.

## Near-flat T003A aggregate explanation

T003A reported:

```text
B=8:  3.575 s / 1936 instances
B=16: 3.587 s / 1936 instances
```

T004 shows this is not batch-independent Marlin work:

- Per-launch durations differ: B=8 is 34.11–56.35 us; B=16 is 39.55–69.86 us.
- Both use the same 82x256 launch geometry, so doubling configured batch does
  not double this kernel's reported grid.
- The selected symbols are different variants. B=8 uses 96 registers/thread;
  B=16 uses 148, while shared memory remains fixed.
- T003A totals are whole-capture aggregates, including lifecycle/prefill/drain
  context, over equal instance counts. They are not steady-decode-only
  integrals.

The evidence-backed explanation is fixed/quantized tile/work mapping plus
B-dependent variant/resource behavior, combined with whole-capture aggregation.

## Candidate #1 — shared-memory / occupancy path

**Exact path to investigate:** the selected Marlin variant's dynamic shared-memory
tile staging and synchronization path (`~101.38 KiB/block`, one wave/SM).

**Support:** shared memory is the explicit occupancy limiter; achieved occupancy
is only ~16.6%; eligible warps are low.

**Expected mechanism:** reduce staging footprint or improve tile reuse/scheduling
so that more resident warps/blocks can hide DRAM and dependency latency, without
assuming that higher theoretical occupancy automatically improves throughput.

**Main risk:** changing staging/tile behavior can alter numerical correctness,
register/shared-memory tradeoffs, graph-captured launch compatibility, or worsen
DRAM traffic and synchronization overhead.

**Smallest validating experiment:** an offline, isolated Marlin-kernel A/B
microbenchmark using the exact B=8 and B=16 captured variants and representative
shapes, measuring correctness, duration, achieved occupancy, DRAM/L2 traffic,
and end-to-end kernel time. Do not alter serving or production code in the
candidate-selection task.

## Candidate #2 — B-dependent template/register/work mapping

**Exact path to investigate:** the dispatch/template choice that changes the
Marlin parameter and register footprint from 96 registers/thread at B=8 to 148
at B=16 while retaining 82x256 geometry.

**Support:** different exact symbols, 54-register increase at B=16, higher
math-pipe throttle at B=16, and near-flat whole-capture aggregate despite
changed per-launch behavior.

**Expected mechanism:** select or design a work mapping that reduces register
pressure and/or improves tile utilization for the B=16 path, potentially raising
eligible warps and reducing math-pipe/dependency stalls.

**Main risk:** this may be a shape-specific dispatch artifact rather than an
optimization opportunity; changing it can affect quantized correctness,
occupancy, memory traffic, graph replay compatibility, and other batch sizes.

**Smallest validating experiment:** offline comparison of the existing B=8 and
B=16 Marlin dispatch variants on identical representative shapes, recording
registers, occupancy, stall metrics, kernel duration, and exact numerical parity
before any serving integration.

## Decision

Ranked recommendation:

```text
Candidate #1: investigate shared-memory/occupancy constraint first.
Candidate #2: investigate B-dependent template/register/work mapping as fallback.
```

Neither candidate was implemented or tested here. Marlin is the highest-value
optimization surface because it is approximately 48% of GPU kernel time alone
and the related linear/GEMM path is approximately 60–65%, but T004 does not prove
that Marlin is the only system-level roof.

NEXT RECOMMENDED EXPERIMENT:
Offline A/B microbenchmark of the exact captured Marlin variants, first varying only the shared-memory/tile-staging footprint, at representative B=8 and B=16 shapes with numerical parity and NCU occupancy/DRAM/stall metrics.

ALTERNATIVE:
Offline A/B comparison of the existing B=8 versus B=16 Marlin dispatch/template variants, isolating register/work-mapping effects before any serving integration.
