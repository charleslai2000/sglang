Status: DONE
Work area: experiments
Objective: Obtain one marked B=16 steady-decode Nsight Systems interval and quantify GPU busy versus runtime/graph gaps.
Inputs: T003A artifacts; temporary default-off marker; frozen production configuration.
Completion: Finalized marked `.nsys-rep` with same-interval kernel composition and gap accounting.
Result: DONE via T012-R2 through T012-R7. Marker observability and report finalization were qualified; node-level graph tracing recovered per-replay kernel timestamps through `CUPTI_ACTIVITY_KIND_KERNEL.start/end + graphNodeId`. Final marked steady accounting is recorded in `T012-R7-REPORT.md`; T013/T014 selected no clean optimization surface. The temporary marker was reverted.
Remaining: None under G004; closure is recorded in `FINAL-REPORT.md`.
