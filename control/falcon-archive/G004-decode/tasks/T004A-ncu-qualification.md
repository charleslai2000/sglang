Status: BLOCKED
Work area: experiments
Objective: Qualify an existing Nsight Compute toolchain without changing production execution semantics, then hand T004 back ready.
Inputs: RTX 3090; driver 580.178.04; CUDA toolkit 12.9; existing `/opt/nvidia/nsight-compute/2025.2.1`.
Completion: `ncu` version recorded, counters accessible, target Marlin capture possible with CUDA graph active, and basic metrics collected.
Result: Existing Nsight Compute was found and launches successfully. Version 2025.2.1.0; `nvcc` 12.9.86; GPU RTX 3090; driver 580.178.04. Standalone CUDA probe ran (`probe-ok`) and ncu attached, but metric collection failed with `ERR_NVGPUCTRPERM`; `/proc/driver/nvidia/params` reports `RmProfilingAdminOnly: 1`. No global permission, driver, symlink, PATH, runtime, Python environment, or production change was made. CUDA-graph qualification was not attempted because counter access failed first. Report: `T004A-REPORT.md`.
Remaining: Authorized administrator must enable profiling-counter access. Then rerun the minimal probe, qualify Marlin capture with CUDA graph active, and stop before formal T004.
