# G004 Plan

## State
G004 DONE. T001 baseline DONE; T002 first-layer attribution DONE; T003A DONE; T004A-R1 DONE; T004A-R2 DONE; T004 DONE; T012-R7 DONE; T013 DONE; T014 DONE. Attribution and current optimization exploration are closed. Final system classification is MIXED GPU-KERNEL COST + SUBSTANTIAL EXECUTION/REPLAY GAP. No optimization was authorized or executed. See `FINAL-REPORT.md`.

## Established inputs
- Production: Falcon-H1 mixed GPTQ/BF16 topology, Mamba `extra_buffer`, prefill graph disabled, full decode graph, HiCache OFF, speculative decoding OFF.
- T012-R7 authoritative B=16 steady interval: 595.439074 ms wall, 406.291281 ms recovered kernel union, 68.2339% kernel coverage, 31.7661% uncovered wall complement.
- Recovered kernel composition: other BF16/CUTLASS GEMM 190.608 ms / 46.91% kernel time; Marlin 82.934 ms / 20.41%; Mamba 71.526 ms / 17.60%; Attention 26.874 ms / 6.61%; remainder norm/elementwise/misc.
- T014 offline decomposition: BF16 aggregate spans several attention/Mamba/other BF16 producers; kernel-union internal gaps total only 4.429648 ms and are mostly sub-microsecond fragments; runtime/API chronology overlaps and is not a disjoint causal partition.

## Decisive frontier
T001–T014 authorized attribution work is complete. T013 selected decomposition; T014 found neither aggregate BF16/CUTLASS nor uncovered wall complement is a clean, independently isolatable surface. Final selection: `NEXT TARGET: NO CLEAN SINGLE SURFACE`. G004 is intentionally terminal; no further decomposition or optimization is active.

## Final attribution
```text
SYSTEM-LEVEL ROOT CAUSE:
MIXED GPU-KERNEL COST + SUBSTANTIAL EXECUTION/REPLAY GAP
```

The 31.7661% complement is not automatically CPU/runtime overhead. Marlin template tuning remains closed; current template was Pareto-best in the bounded existing-template search.

## Closure
Stop and close G004 at the current conclusion. A future goal requires explicit owner authorization and a materially changed evidence/target boundary; no production change or experiment is implied by this plan.
