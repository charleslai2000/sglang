Status: DONE
Work area: experiments
Objective: Trace B=8/B=16 Marlin template/work-mapping differences and select one existing legal candidate without executing it.
Inputs: T004 NCU metrics; T006 isolated shapes; Marlin dispatch/template source.
Completion: Explain dispatch, concrete code/resource differences, 96→148 registers, T004 behavior, and identify one existing legal candidate or reject separability.
Result: PASS. `m_block_size_8` is derived from `prob_m_split <= 8`: B8 M=8→true, B16 M=16→false. It changes effective M tile (8 vs 16), A `ldsm` fragment width (2 vs 4), MMA path (`mma_trans` vs two `mma`), accumulator/reduction layout, scale handling, masks, and global stores. This explains the strategy-dependent register increase and B16 math-pipe/eligible-warp behavior; classification is `TEMPLATE/WORK-MAPPING DEPENDENT`, not purely inherent to shape. Existing legal `m_block_size_8=true` specialization exists in the same macro family, but routing M=16 through it requires an isolated dispatch/work-mapping experiment and exact correctness proof. No code, compile, NCU, serving, or benchmark was run. Report: `T008-REPORT.md`.
Remaining: Owner review; authorize one isolated M=16 existing-specialization A/B experiment if desired.
