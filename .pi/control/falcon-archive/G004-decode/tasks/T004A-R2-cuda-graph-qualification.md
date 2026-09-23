Status: DONE
Work area: experiments
Objective: Confirm Nsight Compute can capture the selected main Marlin kernel while production decode CUDA graph remains active, using the smallest authorized diagnostic serving run.
Inputs: T004A-R1 privileged counter access PASS; T003A target symbol and frozen production configuration.
Completion: Target Marlin kernel is matched and basic NCU metrics are collected with decode CUDA graph active, without formal B=8/B=16 profiling or optimization.
Result: PASS. A clean minimal NCU launch qualification retained frozen decode CUDA graph execution (`backend=full`, runtime `cuda graph: True`), completed one short request with HTTP 200 and no errors, matched the exact Marlin family with `--target-processes all` and demangled regex filter, and generated a 13.5 MiB report containing numeric duration, launch, occupancy, compute, and memory metrics. Formal B=8/B=16 profiling was not run. Report: `T004A-R2-REPORT.md`.
Remaining: T004 is READY to resume as a separate authorized task; do not infer formal attribution from this qualification.
