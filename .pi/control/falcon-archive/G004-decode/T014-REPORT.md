# G004 / T014 — Residual Surface Decomposition

## Result

```text
T014: PASS
NEXT TARGET: NO CLEAN SINGLE SURFACE
```

This was an offline decomposition review only. No workload, serving process, capture, code modification, scheduler change, or optimization was executed.

## Frozen system attribution

```text
SYSTEM-LEVEL ROOT CAUSE:
MIXED GPU-KERNEL COST + SUBSTANTIAL EXECUTION/REPLAY GAP
```

Authoritative R7 interval:

```text
wall interval: 595.439074 ms
kernel union: 406.291281 ms
kernel coverage: 68.2339%
uncovered wall complement: 31.7661%
```

The complement remains a coverage/uncovered-wall measure, not an automatic CPU/runtime attribution.

## A. BF16/CUTLASS decomposition

### Source topology

Falcon-H1 has multiple independent BF16 dense paths:

- Attention `qkv_proj` and `o_proj` are explicitly constructed with `quant_config=None` in `falcon_h1.py`.
- Mamba has separate `in_proj` and `out_proj` layers in `mamba.py`.
- The Falcon FFN `gate_up_proj` and `down_proj` are the GPTQ-Marlin path, not the BF16 candidate surface.
- The same decode graph also contains distinct fused normalization, activation, attention, state, and reduction kernels.

Therefore `other BF16/CUTLASS GEMM` is an accounting family, not one model operation.

### Largest kernel families

The R6 marked interval's largest resolved symbols were:

```text
ampere_bf16_s16816gemm_bf16_64x64_sliced1x2_ldg8_f2f_stages_64x6_tn
  971 calls, approximately 69.001 ms raw

ampere_bf16_s16816gemm_bf16_64x64_ldg8_f2f_stages_64x5_tn
  971 calls, approximately 31.465 ms raw

ampere_sgemm_64x32_sliced1x4_tn
  22 calls, approximately 44.290 ms raw

CUTLASS BF16 tensor/WMMA variants
  multiple 971-call families, approximately 36.144 ms combined for the two largest listed CUTLASS variants
```

The repeated 971-call patterns show stable per-replay/per-layer work, but the kernel symbol and chronology do not carry a module/operator label. Source execution order establishes that attention projections and Mamba projections are separate producers; it does not uniquely assign each generic BF16 GEMM symbol to one producer. The 22-call SGEMM family is also not enough to identify a single optimization path from this artifact alone.

The aggregate remains:

```text
other BF16/CUTLASS GEMM: 190.608 ms
46.91% of recovered kernel time
32.01% of marked wall interval
```

### BF16 decision

No single BF16 operator satisfies all required conditions:

- sufficiently concrete operator identity: **no**
- uniquely known shape-to-module mapping: **no**
- independent isolation from attention/Mamba paths: **no**
- safe first targeted experiment: **no**

A new operator-level marker capture could improve attribution, but it would be a new diagnostic capture rather than a clean optimization target. The current evidence does not justify selecting one operator before that additional step.

## B. Uncovered-gap decomposition

### Kernel busy-union gap distribution

The 406.291281 ms kernel union consists of 15,981 merged busy intervals. Internal gaps between adjacent merged kernel intervals are:

```text
count: 15,980
total: 4.429648 ms
mean:  0.000277 ms
p50:   0.000064 ms
p95:   0.001184 ms
max:   0.107582 ms
```

The distribution is overwhelmingly tiny fragments. Only 6 internal gaps are at least 0.1 ms, totaling 0.613205 ms. No internal gap reaches 0.5 ms.

This means the 31.7661% complement is not primarily a large collection of repeated replay-internal kernel gaps. Most of it is at the interval edges / portions not covered by recovered kernel rows, not a clean periodic hole between every kernel sequence.

### Runtime and CUDA activity chronology

Within the marker interval:

```text
cudaGraphLaunch:       21 records, 61.295 ms summed API elapsed time
cudaEventSynchronize:   21 records, 234.653 ms summed API elapsed time
cudaMemcpyAsync:       153 records, 3.247 ms summed API elapsed time
cudaStreamWaitEvent:    64 records, 0.200 ms summed API elapsed time
cudaEventRecord:       151 records, 1.159 ms summed API elapsed time
```

The interval also contains:

```text
CUPTI_ACTIVITY_KIND_MEMCPY overlap rows: 1,125
CUPTI_ACTIVITY_KIND_SYNCHRONIZATION overlap rows: 545
```

These records cannot be summed into the 31.7661% complement: host API elapsed intervals overlap GPU work and one another, and the API rows are not a disjoint critical-path partition. In particular, the 234.653 ms `cudaEventSynchronize` sum is not proof of 234.653 ms GPU idle time.

The repeated graph launch cadence is known from R7, but no single launch/synchronization/memcpy mechanism accounts for the uncovered complement without double counting or conflating host elapsed time with device idle time.

### Gap decision

The gap has:

- a repeatable graph-launch cadence: **yes**
- a clean repeated uncovered gap per replay: **no**
- a disjoint causal mapping to one API mechanism: **no**
- an independently isolatable runtime optimization target: **no**

## Candidate comparison

| Surface | Evidence-backed size | Concrete mapping | Isolation quality | Decision risk |
|---|---:|---|---|---|
| Aggregate BF16/CUTLASS GEMM | 46.91% recovered kernel time / 32.01% wall | Several attention/Mamba/other producers | Insufficient | High; may change multiple paths |
| Uncovered wall complement | 31.77% wall | Mostly edge/coverage complement; API rows overlap | Insufficient | High; mechanism not isolated |

Neither surface reaches a clean single execution path suitable for the next optimization frontier.

## Final selection

```text
NEXT TARGET:
NO CLEAN SINGLE SURFACE
```

G004 attribution remains closed at the system level. Optimization exploration should also be closed for now rather than selecting an unsupported target. A future goal would need explicit owner authorization for a new diagnostic decomposition step, such as a minimal operator-level marker capture or a separately designed runtime critical-path measurement; neither is executed or selected here.

## Final state

```text
SYSTEM-LEVEL ROOT CAUSE:
MIXED GPU-KERNEL COST + SUBSTANTIAL EXECUTION/REPLAY GAP
NEXT TARGET: NO CLEAN SINGLE SURFACE
```
