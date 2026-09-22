Status: BLOCKED
Work area: experiments
Objective: Controlled isolated A/B of the Marlin shared-memory/tile-staging path using the reproduced T006 baseline.
Inputs: T006 isolated harness and reports; Marlin template source.
Completion: One minimal shared-memory intervention passes compile, correctness, and NCU A/B metrics for B=8/B=16, or exact blocker is recorded and source restored.
Result: BLOCKED before execution. Source mapping found coupled `sh_b`, act-order `sh_g_idx`, `sh_s`, `sh_a`, reduction overlay, async pipeline, `cp.async_wait<stages-2>`, and `__syncthreads()` regions. The smallest single-axis attempt, global `pipe_stages` 4→3, failed the existing compile-time assertion in `marlin_template.h:648` across 22 template instantiations. No experimental kernel executed; no correctness or performance result was inferred. Source was restored to `pipe_stages=4`. Report: `T007-REPORT.md`.
Remaining: Owner review and explicit decision on a different shared-memory intervention or moving to Candidate #2. No optimization authorized.
