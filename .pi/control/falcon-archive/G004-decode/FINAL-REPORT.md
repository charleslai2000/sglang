# G004 Closure — Falcon-H1 Decode Saturation Attribution

## Final status

```text
G004-falcon-h1-decode-saturation: DONE
T014: PASS
NEXT TARGET: NO CLEAN SINGLE SURFACE
```

No further profiling, decomposition, optimization, benchmark, or production-code change is authorized under G004.

## What was established

The authoritative decode-heavy baseline on one RTX 3090 is:

```text
B=1    68.69 tok/s
B=2   118.68 tok/s
B=4   226.93 tok/s
B=8   397.04 tok/s
B=12  432.48 tok/s
B=16  459.53 tok/s
```

At B=16:

- actual decode batch reaches 16;
- scheduler underfill is not observed;
- waiting queue is 0 in the marked steady interval;
- full decode CUDA graph is active.

The throughput plateau is therefore not explained by failure to form the requested decode batch.

Authoritative marked steady interval:

```text
wall interval:             595.439074 ms
recovered kernel union:    406.291281 ms
GPU kernel coverage:       68.2339%
uncovered wall complement: 31.7661%
```

The 31.7661% value is only marked wall time not covered by recovered GPU kernel execution. It is not identified wholesale as CPU overhead, scheduler overhead, CUDA graph overhead, or GPU idle time.

## Final system classification

```text
SYSTEM-LEVEL ROOT CAUSE:
MIXED GPU-KERNEL COST + SUBSTANTIAL EXECUTION/REPLAY GAP
```

Falcon-H1 decode saturation on RTX 3090 is a distributed system roof rather than a single isolated bottleneck under the tested configuration. The steady B=16 interval contains substantial BF16/CUTLASS GEMM, Marlin, Mamba, and uncovered execution/replay wall time.

This is not a claim of an absolute RTX 3090 hardware roof, Marlin absolute roof, DRAM-bandwidth roof, scheduler roof, or CUDA-graph-overhead roof.

## Steady GPU-kernel accounting

Within the marked interval:

| Surface | GPU time | Share of recovered kernel time | Share of marked wall interval |
|---|---:|---:|---:|
| Other BF16/CUTLASS GEMM | 190.608 ms | 46.91% | 32.01% |
| Main GPTQ-Marlin | 82.934 ms | 20.41% | 13.93% |
| Mamba | 71.526 ms | 17.60% | 12.01% |
| Attention / FlashInfer | 26.874 ms | 6.61% | 4.51% |
| Norm / elementwise / misc | distributed remainder | distributed remainder | distributed remainder |

The authoritative steady-state ranking is:

- BF16/CUTLASS GEMM aggregate is the largest recovered GPU surface;
- Marlin remains substantial but is not the largest steady-decode surface;
- Mamba is also substantial;
- no single residual component satisfies the evidence and isolation requirements for a low-risk optimization experiment.

The earlier whole-capture description `MARLIN-DOMINANT` is superseded for steady-state optimization ranking. Whole-capture Marlin evidence remains valid historical profiling evidence, but is not the authoritative marked-interval ranking.

## Optimization branches tested and rejected

### Marlin branch

```text
MARLIN EXISTING-TEMPLATE SEARCH:
CURRENT TEMPLATE PARETO-BEST
```

Established evidence:

- main Marlin kernel was deeply profiled;
- shared-memory-only intervention was not cleanly separable;
- the correct 2xM=8 decomposition was approximately 2.17x slower for complete M=16 work;
- bounded existing-template search found no candidate with clear complete-operation improvement.

No production dispatch change is recommended. All experimental source changes were restored. No pending Marlin optimization task remains under G004.

### BF16/CUTLASS branch

The aggregate spans multiple paths, including:

- Attention qkv/o projections;
- Mamba in/out projections;
- other BF16 dense, fused, and reduction paths.

Existing artifacts do not uniquely map the dominant generic GEMM symbols to one operator. No clean isolated BF16 optimization target was identified.

### Execution/replay-gap branch

Replay cadence is measurable, but the uncovered complement is not attributable to one causal mechanism:

- internal kernel gaps are tiny and distributed;
- CUDA API and synchronization intervals overlap GPU activity;
- process-wide or overlapping API elapsed times cannot partition the marked wall interval;
- no single repeatable host submission, synchronization, memcpy, or event mechanism was isolated.

## Why decomposition stopped

T013 selected decomposition rather than optimization. T014 established that neither candidate meets the required isolation threshold:

```text
NEXT TARGET:
NO CLEAN SINGLE SURFACE
```

Selecting either aggregate BF16/CUTLASS or the uncovered complement would conflate multiple execution paths and create an unsupported optimization target. This is an intentional terminal result for G004, not an unresolved failure.

## Preserved future-work notes

A future owner-authorized goal may revisit the conclusion only if new evidence changes the isolation boundary, for example:

- operator-level labeling becomes available for BF16 GEMMs;
- a new SGLang/Falcon-H1 kernel implementation changes execution composition;
- CUDA graph/runtime instrumentation becomes more precise;
- a new quantization topology moves Attention/Mamba projections off BF16;
- a materially different workload shifts the steady-state component mix.

These are hypotheses, not active tasks. No new goal is opened automatically.

## Production state

- production configuration unchanged;
- production source restored;
- all temporary marker changes removed;
- no scheduler, CUDA graph policy, Marlin, Mamba, Attention, quantization, or serving behavior change remains.
