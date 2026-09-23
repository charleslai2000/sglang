Status: DONE
Work area: experiments
Objective: Audit whether a legal minimal shared-memory/tile-staging variant exists for the exact T006 Marlin B=8/B=16 shapes without compiling or running experiments.
Inputs: T006 exact symbols; Marlin source template, dispatch macros, and shared-memory expressions.
Completion: Evaluate invariants numerically, break down storage, enumerate legal candidates, and choose whether Candidate #1 remains cleanly separable.
Result: PASS. Exact variants use thread_m_blocks=1, thread_n_blocks=8, thread_k_blocks=8, stages=4, group_blocks=8, threads=256. Assertion LHS=256 int4 units; RHS=2048 at stages=4 and 1536 at stages=3, so exact variants pass either value, but global stages=3 fails 22 other eagerly instantiated configurations. Exact template-addressed storage is estimated at 35,840 bytes (B8) and 37,888 bytes (B16); T004's 101.38 KiB is the launch dynamic-allocation ceiling, not direct addressed bytes. Existing alternate tile/template combinations change work mapping/register behavior; launch-allocation-only reduction is a separate high-risk contract change; further reuse is new kernel design. Decision: `SHARED-MEMORY PATH NOT CLEANLY SEPARABLE — move to Candidate #2`. Report: `T007A-REPORT.md`.
Remaining: Owner review; authorize Candidate #2 or a separately designed assertion-preserving kernel experiment. No compile/NCU/serving run performed.
