# G004 / T013 — Final Optimization Surface Selection

## Result

```text
T013: PASS
NEXT TARGET: FURTHER DECOMPOSITION REQUIRED
```

No experiment, serving run, production-code change, profiler capture, or optimization was executed.

## Frozen final attribution

```text
SYSTEM-LEVEL ROOT CAUSE:
MIXED GPU-KERNEL COST + SUBSTANTIAL EXECUTION/REPLAY GAP
```

Authoritative T012-R7 steady interval:

```text
wall interval: 595.439074 ms
actual batch: 16
waiting queue: 0
CUDA graph: active
recovered kernel union: 406.291281 ms
recovered GPU busy: 68.2339%
uncovered wall-time complement: 31.7661%
```

The 31.7661% value is only the wall-time complement of recovered kernel execution. It is not relabeled wholesale as CPU/runtime overhead.

## Candidate A — BF16/CUTLASS GEMM surface

The source and symbol evidence does not identify one coherent BF16/CUTLASS operation. Falcon-H1 has several independent BF16 dense paths:

1. **Attention projections**
   - `FalconH1HybridAttentionDecoderLayer.qkv_proj`
   - `FalconH1HybridAttentionDecoderLayer.o_proj`
   - Both are explicitly constructed with `quant_config=None` in `falcon_h1.py`, so they remain BF16/unquantized.

2. **Mamba projections**
   - `MambaMixer2.in_proj`
   - `MambaMixer2.out_proj`
   - These are separate dense projection operations around the Mamba scan path. The Mamba implementation constructs the projection layers independently from the Falcon FFN and uses the BF16/unquantized topology for this checkpoint path.

3. **Other surrounding BF16/fused linear work**
   - Kernel symbols include multiple distinct CUTLASS/CUBLAS BF16 shapes and fused norm/activation/elementwise operations.
   - The exact steady interval contains, among others, separate `ampere_bf16_s16816...64x64...` variants, CUTLASS BF16 GEMMs, split-K reduction kernels, and fused normalization/activation work.

The recovered `other GEMM` family is therefore an accounting family, not a single dispatch target. The largest named symbols include:

```text
ampere_bf16_s16816gemm_bf16_64x64_sliced1x2_ldg8_f2f_stages_64x6_tn
  69.001 ms raw, 971 calls

ampere_bf16_s16816gemm_bf16_64x64_ldg8_f2f_stages_64x5_tn
  31.465 ms raw, 971 calls

ampere_sgemm_64x32_sliced1x4_tn
  44.290 ms raw, 22 calls

CUTLASS BF16 GEMM and WMMA variants
  multiple distinct symbols and shapes
```

The 971-call repetition is consistent with repeated per-layer/per-replay execution, but kernel names alone do not establish which specific model projection each shape implements. The source topology proves multiple eligible producers; the artifact does not contain a reliable operation-name or module attribution for each kernel launch.

Steady-interval aggregate:

```text
other BF16/CUTLASS GEMM: 190.608 ms
46.91% of recovered kernel time
32.01% of marked wall interval
```

Conclusion: Candidate A has the largest recovered GPU-kernel surface, but it is distributed across attention projections, Mamba projections, and other BF16 linear/fused paths. It is not sufficiently coherent for one isolated optimization experiment without another attribution step.

## Candidate B — uncovered execution/replay gap

The same interval contains repeated CUDA graph launches:

```text
21 cudaGraphLaunch_v10000 calls
mean start-to-start gap: 18.6169 ms
p50: 18.6739 ms
p95: 19.0260 ms
range: 18.0094–19.0291 ms
```

This establishes a repeated replay mechanism and makes the gap a real system-level surface. However, existing evidence does not separate the 31.7661% complement into:

- host launch/submission time;
- synchronization/API wait time;
- inter-replay idle time;
- asynchronous CUDA work not represented in kernel rows;
- profiler coverage limitations.

T003A process-wide API summaries show synchronization and memcpy activity, but they are not marker-interval-specific and cannot be used to assign this complement to a concrete critical-path mechanism. The R6/R7 kernel chronology also does not provide a complete causal join from every uncovered segment to a specific API or synchronization event.

Conclusion: Candidate B has substantial wall-time leverage and repeated cadence, but its optimization mechanism is not isolated well enough to justify a runtime/graph experiment.

## Candidate comparison

| Candidate | Maximum evidence-backed share | Mechanism clarity | Isolation quality | Likely leverage | Risk |
|---|---:|---|---|---|---|
| BF16/CUTLASS GEMM family | 46.91% recovered kernel time / 32.01% wall interval | Low–medium; multiple producers | Low without module-to-kernel mapping | Potentially high | High; may affect attention, Mamba, or mixed paths differently |
| Execution/replay gap | 31.77% wall complement | Medium at envelope level, low at causal mechanism level | Low; API summaries are not interval-specific | Potentially high | High; scheduler/graph behavior is sensitive |

Neither candidate meets the required isolation threshold for a first optimization experiment. Ranking one merely by percentage would create an unsupported optimization target.

## Final decision

```text
NEXT TARGET:
FURTHER DECOMPOSITION REQUIRED
```

This is Option C. The next optimization frontier must first split one of the two aggregate surfaces into an experimentally isolable mechanism. No optimization target is selected in T013.

Marlin status remains closed for the existing-template branch:

```text
current template: Pareto-best in bounded existing-template search
no production candidate
```

## G004 attribution closure

G004 attribution is no longer marked unresolved. The final state is:

- Other BF16/CUTLASS GEMM is the largest recovered GPU-kernel surface.
- Steady-state Marlin is substantial but not dominant in the authoritative marked interval.
- Mamba is also substantial and distributed.
- The 31.7661% wall-time complement remains only partially attributed and is not automatically called CPU overhead.
- Existing Marlin template tuning produced no useful production candidate.
- No next optimization experiment was executed or authorized by T013.
