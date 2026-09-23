Status: DONE
Work area: experiments
Objective: Use existing T003A Nsight Systems artifacts to rank Marlin-external residual GPU time and quantify steady-decode runtime/graph gaps.
Inputs: B8/B16 server.sqlite, T003A report, T004/T010 results.
Completion: Defensible B8/B16 steady-step component/gap accounting and next target selection, or exact artifact limitation.
Result: DONE via T012-R7 and T014 supersession. The original T003A-only artifact limitation was resolved by the marked node-level capture and offline semantics review. Final steady accounting is recorded in `T012-R7-REPORT.md`; T014 found no clean single BF16 or gap surface for optimization. No optimization executed.
Remaining: None under G004; closure is recorded in `FINAL-REPORT.md`.
