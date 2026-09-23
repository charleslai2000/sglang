# G004 / T004A — Nsight Compute Toolchain Qualification

## Verdict

```text
T004A: BLOCKED
T004: remains BLOCKED
```

The blocker is profiling permission, not SGLang, model, scheduler, or CUDA
runtime behavior. No benchmark, Nsight Systems rerun, serving run, production
change, or optimization was performed.

## Current environment

```text
OS: Ubuntu 24.04.5 LTS
GPU: NVIDIA GeForce RTX 3090
PCI bus: 00000000:00:10.0
driver: 580.178.04
nvidia-smi reported CUDA compatibility: 13.0
CUDA toolkit: /usr/local/cuda-12.9
nvcc: 12.9.86
```

Relevant layout:

```text
/usr/local/cuda -> /etc/alternatives/cuda
/usr/local/cuda-12 -> /etc/alternatives/cuda-12
/usr/local/cuda-12.9: present
/opt/nvidia/nsight-compute/2025.2.1: present
```

The default shell did not expose `nvcc` or `ncu` in `PATH`; this was only a
PATH visibility issue for the executable, not an absent installation.

No symlink, PATH, LD_LIBRARY_PATH, CUDA runtime, driver, Python environment, or
production installation was changed.

## Nsight Compute

```text
source: /opt/nvidia/nsight-compute/2025.2.1
executable: /opt/nvidia/nsight-compute/2025.2.1/ncu
version: 2025.2.1.0 (build 35987062) (public-release)
```

The same version is also available under:

```text
/usr/local/cuda-12.9/bin/ncu
```

Installed package evidence:

```text
nsight-compute-2025.2.1 2025.2.1.3-1
cuda-nsight-compute-12-9 12.9.2-1
```

## Minimal probe

A standalone CUDA probe was compiled with the existing CUDA 12.9 toolkit and
ran successfully:

```text
probe-ok
```

Nsight Compute connected to the process, proving the executable can launch and
attach:

```text
==PROF== Connected to process ...
```

However, basic metric collection failed:

```text
ERR_NVGPUCTRPERM - The user does not have permission to access NVIDIA GPU
Performance Counters on the target device 0.
```

The driver parameter audit reported:

```text
RmProfilingAdminOnly: 1
```

Therefore RTX 3090 performance counters are not accessible to the current
user. This is exactly the permission blocker covered by T004A stop conditions.

## CUDA graph qualification

Not attempted. The minimal counter-access qualification failed first. Starting
an SGLang server or changing CUDA graph behavior would not resolve the
permission issue and would violate the scoped qualification objective.

Consequently these PASS conditions remain unmet:

```text
RTX 3090 performance counters accessible: NO
Marlin kernel capture with basic metrics: NOT TESTED
CUDA graph compatibility: NOT TESTED
```

## Required unblock

An authorized administrator must provide profiling-counter access, likely by
changing the applicable NVIDIA profiling permission policy for this machine.
No global security setting or driver configuration was changed by this task.

After that authorization/change, rerun only the minimal probe first; then test
Marlin capture on the existing CUDA-graph-enabled path. Do not proceed to the
formal T004 B=8/B=16 deep profile until the qualification passes.
