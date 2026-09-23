Status: DONE
Work area: experiments
Objective: Correctness-first isolated A/B of current M=16 Marlin versus complete M=16 decomposition into two existing M=8 specializations.
Inputs: T006 harness/shapes; T008 existing specialization analysis.
Completion: Verify complete row coverage/correctness, then compare complete-operation cost and targeted NCU metrics without serving integration.
Result: PASS with negative result. Alternative computes rows 0–7 and 8–15 via two existing `m_block_size_8=true` calls, passes deterministic correctness with relative mean absolute error 2.068e-6, and no indexing/race symptoms. Current one-call M=16 mean total event time 124.50 us; alternative two-call total 269.90 us (~2.17x). Alternative reduces registers 148→96/thread, eligible warps 0.29→0.38, and math throttle ~3.52→~1.20 per launch, but requires two launches, has higher DRAM (72–74% vs 62.6%), and does not recover total cost. Final: `ALTERNATIVE SPECIALIZATION: REGRESSIVE`; no production canary. Report: `T009-REPORT.md`.
Remaining: Owner review; no further specialization forcing recommended without a different existing work mapping.
