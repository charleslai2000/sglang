# OPS-20260908-3060-KERNEL-CUDA12-NARROW-050

status: blocked
task_id: D3060-KERNEL-CUDA12-NARROW-050
orchestration_epoch: 20260908-3060
role: devops-executor
target: root@i-1.gpushare.com:27460 (RTX 3060, untouched 3090)

## Summary

The CUDA 12.4 narrow `sglang-kernel` build was attempted from the requested AOT
source using `/root/sglang-env-3060-4b`, a fresh build directory, `pip wheel`,
`MAX_JOBS=2`, `CMAKE_BUILD_PARALLEL_LEVEL=2`, and the requested CMake feature
flags. It was blocked during CMake configuration because the host has no CUDA
compiler available. No wheel was produced and no installation occurred.

## Commands and preserved logs

Executed remotely under a hard `timeout 1200s`:

```text
SRC=/root/sglang-3060-12g-hicache/python/sglang/kernels/aot
ENV=/root/sglang-env-3060-4b
BUILD=/root/sglang-3060-kernel-build-20260908-230211
export MAX_JOBS=2
export CMAKE_BUILD_PARALLEL_LEVEL=2
export CMAKE_ARGS="-DSGL_KERNEL_ENABLE_FA3=OFF -DSGL_KERNEL_ENABLE_SM90A=OFF -DSGL_KERNEL_ENABLE_SM100A=OFF -DSGL_KERNEL_ENABLE_FP4=OFF -DSGL_KERNEL_ENABLE_BELOW_SM90=ON"
pip wheel --no-build-isolation --no-deps --wheel-dir "$BUILD/wheel" "$SRC"
```

The complete output is preserved remotely at:

```text
/root/sglang-3060-kernel-build-20260908-230211/build.log
```

A preliminary invocation using `uv pip wheel` was rejected by the installed
`uv 0.12.10` because that subcommand does not exist; it did not enter a build.
The authorized pip fallback was then used in the fresh directory above.

## Baseline evidence

```text
Python 3.11.11
pip 26.2.1
cmake version 4.4.3
TORCH 2.5.1+cu124
TORCH_CUDA 12.4
CUDA_AVAILABLE True
DEVICE NVIDIA GeForce RTX 3060 (8, 6)
bash: nvcc: command not found
```

## Exact failure

```text
Building wheel for sglang-kernel (pyproject.toml): finished with status 'error'
*** scikit-build-core 1.0.3 using CMake 4.4.3 (wheel)
*** Configuring CMake...
CMake Error at CMakeLists.txt:2 (project):
  No CMAKE_CUDA_COMPILER could be found.

Tell CMake where to find the compiler by setting either the environment
variable "CUDACXX" or the CMake cache entry CMAKE_CUDA_COMPILER to the full
path to the compiler, or to the compiler name if it is in the PATH.
*** CMake configuration failed
ERROR: Failed to build one or more wheels
EXIT_STATUS=1
```

Build progress: metadata preparation completed; CMake detected GNU 11.4.0 and
completed C++ compiler checks; CUDA compiler detection/configuration failed;
no CUDA compilation started.

## Changed resources

- Created remote fresh build directory:
  `/root/sglang-3060-kernel-build-20260908-230211/`
- Created/preserved remote log:
  `/root/sglang-3060-kernel-build-20260908-230211/build.log`
- No source files changed.
- No environment package installation or replacement occurred.
- No wheel was created or installed.
- No model, server, benchmark, driver, Torch, CUDA library, or 3090 resource
  was touched.

## Verification evidence

Wheel completion, `sgl_kernel` import/ops verification, ELF `NEEDED` library
inspection, and architecture inspection were not runnable because the wheel
did not exist. The pre-existing installed package was not used as a substitute.

## Followups

The host needs an already-authorized CUDA toolkit/compiler path made available
(`nvcc`/`CUDACXX`) before this exact build method can proceed. That is an
environment change outside this invocation; no workaround was applied.

## Open issues

- CUDA compiler/toolkit is absent from PATH and no `CMAKE_CUDA_COMPILER` was
  supplied. This is the blocking issue.
- Completion requires a fresh Task ID after the environment issue is resolved.
