Status: DONE
Work area: experiments
Objective: Use T002 evidence to perform minimal B=8/B=16 deep kernel attribution for decode saturation without changing execution behavior.
Inputs: `control/G004-falcon-h1-decode-saturation/T002-ATTRIBUTION-REPORT.md`; T002 raw attribution artifacts; frozen Falcon-H1 runtime.
Completion: Profile only an evidence-selected dominant kernel/path, or record a concrete limitation and stop.
Result: T003A successfully finalized readable Nsight Systems reports for B=8 and B=16 after asynchronous write completion. Both 48/48 workloads completed with cuda graph=True, actual batch full, queue=0, and no runtime failure. Kernel summary selected main GPTQ-Marlin as dominant (~47.7% B8, ~48.1% B16), with BF16 GEMM and Mamba families next. CUDA API summary shows synchronization/memcpy activity but is not a clean steady-window gap accounting. Final attribution: MIXED, Marlin-dominant; internal compute-vs-memory bound and exact steady idle gap remain unresolved. Report: `T003A-REPORT.md`.
Remaining: Owner review; next authorized step is targeted deep profile of the main GPTQ-Marlin family only. No optimization authorized.
