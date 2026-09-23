Status: DONE
Work area: experiments
Objective: Targeted deep profile of the dominant GPTQ-Marlin kernel at B=8 and B=16.
Inputs: T003A Nsight Systems reports; frozen runtime; selected main `sglang::device::marlin::Marlin` family.
Completion: Obtain Nsight Compute metrics sufficient to classify Marlin compute, bandwidth, occupancy/latency, dependency, or mixed bound without changing production semantics.
Result: PASS. Formal B=8/B=16 targeted NCU profiles completed with frozen decode CUDA graph execution, 48/48 workload completion at each batch, zero client errors, and exact Marlin-family capture. Reports collected geometry, registers, shared memory, occupancy, compute, DRAM/L2, warp eligibility, and stall metrics. Final attribution: `MARLIN ROOT CAUSE: MIXED`; low occupancy/shared-memory constraint, substantial DRAM pressure, and B-dependent math-pipe/scoreboard behavior coexist. T003A near-flat aggregate is explained by fixed 82x256 launch geometry, B-dependent template/register variants, and whole-capture aggregation over equal instance counts; it is not proof of batch-independent work. Report: `T004-REPORT.md`.
Remaining: Owner review. No optimization executed.
