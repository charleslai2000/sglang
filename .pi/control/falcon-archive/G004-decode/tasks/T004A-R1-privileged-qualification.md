Status: DONE
Work area: experiments
Objective: Run the same minimal CUDA probe under sudo ncu and determine whether admin-only GPU performance-counter policy is the sole blocker.
Inputs: T004A probe; RTX 3090; driver 580.178.04; Nsight Compute 2025.2.1.0.
Completion: Normal-user ERR_NVGPUCTRPERM recorded; sudo ncu either collects basic numeric metrics or exact privileged failure recorded; no driver/module changes.
Result: Normal-user control reproduced `ERR_NVGPUCTRPERM`; the same probe under authorized `sudo ncu` completed 8 passes, produced `/tmp/g004_t004a-privileged.ncu-rep` (83K), emitted numeric basic metrics, and exited 0 with `probe-ok`. The permission blocker is confirmed to be admin-only counter access. No driver/module policy, SGLang, or production change was made. CUDA-graph/Marlin qualification was intentionally not attempted. Report: `T004A-R1-REPORT.md`.
Remaining: Separate authorization for CUDA-graph-compatible target Marlin capture; stop before formal T004.
