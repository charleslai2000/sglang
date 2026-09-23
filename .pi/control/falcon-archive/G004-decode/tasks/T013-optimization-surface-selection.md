Status: DONE
Work area: experiments
Objective: Select exactly one next optimization frontier from final T012-R7 evidence without running an experiment.
Inputs: T003A, T004, T010, T012-R7, Falcon-H1 source topology, finalized R6 SQLite/kernel symbols.
Completion: Compare BF16/CUTLASS GEMM and uncovered execution/replay gap, close G004 attribution state, and select one frontier.
Result: T013 PASS. Final attribution is MIXED GPU-KERNEL COST + SUBSTANTIAL EXECUTION/REPLAY GAP. Other BF16/CUTLASS GEMM is the largest recovered kernel family but is distributed across attention, Mamba, and other BF16 dense/fused paths; the 31.7661% complement has repeated graph cadence but no sufficiently isolated causal host/API mechanism. Neither is ready for direct optimization.
Remaining: NEXT TARGET: FURTHER DECOMPOSITION REQUIRED. No experiment or production change executed.
