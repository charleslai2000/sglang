Status: DONE
Work area: experiments
Objective: Review T004 evidence and select at most two Marlin optimization candidates without running experiments or changing production.
Inputs: T004-REPORT.md; B=8/B=16 NCU reports and extracted metrics.
Completion: Summarize decisive metrics, explain MIXED attribution and near-flat aggregate time, rank at most two evidence-backed candidates, and stop for owner decision.
Result: T005 PASS. Candidate #1: investigate shared-memory/tile-staging constraint because ~101.38 KiB/block limits occupancy to ~16.6% and eligible warps are low. Candidate #2: investigate B-dependent template/register/work mapping because B=8 uses 96 versus B=16 148 registers/thread with unchanged 82x256 geometry and higher B16 math-pipe throttle. No candidate was implemented or tested. Report: `T005-REPORT.md`.
Remaining: Owner decision; no optimization authorized.
