Status: DONE
Work area: experiments
Objective: Correct T001 B=12 semantics and perform first-layer synchronized resource attribution at B=8/12/16 without optimization.
Inputs: T001 baseline artifacts; frozen Falcon-H1 runtime; `attribution_run.py`.
Completion: B=12 partial-drain interpretation resolved; B=8/12/16 full-batch resource evidence collected; root cause classified or explicitly unresolved; no behavior patch.
Result: B=12 is initial/final partial-drain artifact (`8 → 12 → 8`) from 32 requests at B=12, not demonstrated oscillation. A 48-request attribution workload produced full actual batches 8/12/16. Mean aggregate TPS was 335.54/409.27/464.40. GPU utilization was ~98% at all points, memory utilization 70.31/67.39/66.33%, power 345.87/344.85/344.11 W, memory clock stable 9501 MHz, SM clock 1788/1753/1741 MHz, VRAM ~21.6 GiB. GPU/kernel root cause is not uniquely resolved; scheduler underfill and simple DRAM ceiling are not supported as primary causes. Report: `control/G004-falcon-h1-decode-saturation/T002-ATTRIBUTION-REPORT.md`.
Remaining: Owner review; next authorized step is separate low-intrusion timeline/kernel attribution. No optimization authorized.
