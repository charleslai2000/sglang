Status: DONE
Work area: experiments
Objective: Bounded offline search of existing legal Marlin template configurations for exact M=16 shape; no new kernel design or serving integration.
Inputs: T006/T009 controls; Marlin existing small-batch template family.
Completion: Correctness-first test 3–6 meaningful existing candidates, measure complete-operation timing/resources, targeted NCU only for fastest candidate, and decide whether current production template is beaten.
Result: PASS. Tested existing `(thread_k,thread_n,threads)=(64,128,128)` and `(128,64,128)` candidates plus current `(128,128,256)` control. Both alternatives deterministic and numerically correct (relative mean abs error 2.001e-6 / 2.043e-6), but timing was 120.65 us and 113.89 us control respectively. Targeted NCU on fastest distinct candidate showed registers 148→132 and math throttle 3.52→1.55, but occupancy 16.66→8.33%, eligible warps 0.29→0.23, DRAM/L2 slightly higher, and complete timing not improved beyond noise. Final: `MARLIN EXISTING-TEMPLATE SEARCH: CURRENT TEMPLATE PARETO-BEST`. Report: `T010-REPORT.md`.
Remaining: Owner review; end current Marlin template-tuning branch or authorize a new hypothesis. No production canary recommended.
