# G3 IQ3 local toolchain scan (2026-09-09)

Status: done (read-only scan). Invocation: INV-G3-IQ3-LOCAL-TOOLCHAIN-SCAN-001; epoch E22.

## Evidence

Complete command transcript is [scan.txt](raw/g3-iq3-toolchain-scan-20260909/scan.txt); hashes are in [hashes.txt](raw/g3-iq3-toolchain-scan-20260909/hashes.txt).

- CMake: `/usr/local/bin/cmake`, version 4.4.3.
- CUDA: `/usr/local/cuda -> /usr/local/cuda-13.0`; `nvcc` exists at `/usr/local/cuda/bin/nvcc` and `/usr/local/cuda-13.0/bin/nvcc` (30,161,576 bytes), but is not on `PATH` (`which nvcc` failed). Explicit `/usr/local/cuda/bin/nvcc --version` reports release 13.0, V13.0.48. Include/lib64 symlinks exist.
- Compilers: `/usr/bin/gcc` and `/usr/bin/g++`, Ubuntu 13.3.0-6ubuntu2~24.04.1.
- Python: `/usr/bin/python3` 3.12.3; pip 24.0 system package. `uv` absent.
- System Python import probes found no `torch`, `sglang`, `sgl_kernel`, `triton`, or `ninja`; filtered pip list likewise had no relevant packages. No `/mnt/data/qwen3-g3-baseline/venv`, `wheels`, or `wheelhouse` directories were present.
- `/mnt/data/qwen3-g3-baseline` remains with `artifacts`, `build`, `locks`, `models`, and `toolchain`; model present at `models/Qwen3.8-27B-GSQ-RCO-IQ3_S.gguf`, 11,771,546,784 bytes. SHA-256: `64b53b64c7aa39f20a7e54bd80582fe595b1d745624ee8a72e92508c0326d810`.
- GPU 1 is an NVIDIA GeForce RTX 3090, UUID `GPU-2e3ed202-3655-d919-0a64-259209bc6587`, 24,576 MiB total / 53 MiB used / 0% utilization at scan time. GPU 0 is a GT 1030 and reported 885 MiB used.
- `/mnt/data/gpu/3090.lock` exists, empty, mode 0660, owner `root:dev`; it was only inspected and not acquired.

## Recommendation

A dedicated `/mnt/data/qwen3-g3-baseline/venv` and wheelhouse are needed before any isolated SGLang/sgl-kernel build or benchmark: the system Python has none of the required runtime/build packages, and `uv` is unavailable. Creating or populating them is outside this read-only invocation. CUDA is installed but should be invoked by explicit path or after an authorized PATH setup; no installation or environment mutation was performed.

## Changed resources / verification

Only the authorized raw logs and this report were created. No services, processes, GPU kernels, lock ownership, packages, or repository product files were changed. `git status --short --branch` was captured in the transcript; pre-existing worktree changes remain untouched.

Followup: dispatch an authorized executor to create/populate the dedicated environment and wheelhouse, then independently verify installation before G3/MMQ work.

Open issues: `nvcc` is not on PATH; launch procedures must use the explicit CUDA path or an authorized environment setup.
