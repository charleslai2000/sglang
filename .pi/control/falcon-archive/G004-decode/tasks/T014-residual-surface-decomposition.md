Status: DONE
Work area: experiments
Objective: Decompose the aggregate BF16/CUTLASS surface and uncovered steady interval without optimization.
Inputs: T012-R7 SQLite, Falcon-H1 source topology, T013 final selection.
Completion: Determine whether either surface forms a clean independently isolatable execution path.
Result: T014 PASS. BF16/CUTLASS is distributed across Attention qkv/o, Mamba in/out, and other BF16/fused paths; generic symbols and call patterns do not uniquely map to one operator. Kernel-union internal gaps total 4.429648 ms (mean 0.277 us, p50 0.064 us, p95 1.184 us, max 0.107582 ms), so the 31.7661% complement is not a clean repeated replay-internal gap. Runtime/API records overlap and cannot form a disjoint causal partition.
Remaining: NEXT TARGET: NO CLEAN SINGLE SURFACE. G004 attribution and optimization exploration should close at the current system-level conclusion.
