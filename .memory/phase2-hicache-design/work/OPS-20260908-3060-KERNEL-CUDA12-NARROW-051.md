# OPS-20260908-3060-KERNEL-CUDA12-NARROW-051

Status: blocked
Task ID: D3060-KERNEL-CUDA12-NARROW-051
Orchestration epoch: 20260908-3060
Role: devops-executor

## Summary

The authorized CUDA 12.4 narrow AOT retry was executed from the requested directory using `/root/sglang-env-3060-4b`. It reached CMake configuration and stopped with exit status 2 because CMake could not find the Torch package configuration. No wheel was produced; therefore no installation or import verification was attempted.

## Command and method

Remote host: `root@i-1.gpushare.com:27460` (credential intentionally omitted).

The remote command used the repository-defined `uv build` method:

```text
cd /root/sglang-3060-12g-hicache/python/sglang/kernels/aot
rm -f OPS-20260908-3060-KERNEL-CUDA12-NARROW-051.build.log
timeout --signal=TERM --kill-after=30s 1200s env \
  PATH=/usr/local/cuda-12.4/bin:$PATH \
  CUDA_HOME=/usr/local/cuda-12.4 \
  CUDACXX=/usr/local/cuda-12.4/bin/nvcc \
  MAX_JOBS=2 CMAKE_BUILD_PARALLEL_LEVEL=2 \
  CMAKE_ARGS="-DENABLE_BELOW_SM90=ON -DSGL_KERNEL_ENABLE_FA3=OFF -DSGL_KERNEL_ENABLE_SM90A=OFF -DSGL_KERNEL_ENABLE_SM100A=OFF -DSGL_KERNEL_ENABLE_FP4=OFF" \
  bash -lc 'set -o pipefail; command -v nvcc; nvcc --version; rm -rf build; /root/sglang-env-3060-4b/bin/python -m uv build --wheel -Cbuild-dir=build . --verbose --color=always --no-build-isolation; rc=$?; echo BUILD_RC=$rc; exit $rc' \
  2>&1 | tee OPS-20260908-3060-KERNEL-CUDA12-NARROW-051.build.log
```

The build command was run with no dependency download, driver change, Torch upgrade, server start, benchmark, fake library, or 3090 modification.

## Evidence

- `command -v nvcc`: `/usr/local/cuda/bin/nvcc` (the resolved executable reports CUDA 12.4.131).
- `nvcc --version`: `Cuda compilation tools, release 12.4, V12.4.131`.
- CMake used `/usr/local/cuda-12.4/bin/nvcc` as `CMAKE_CUDA_COMPILER`.
- Fresh `build/` cache recorded:
  - `ENABLE_BELOW_SM90=ON`
  - `SGL_KERNEL_ENABLE_FA3=OFF`
  - `SGL_KERNEL_ENABLE_SM90A=OFF`
  - `SGL_KERNEL_ENABLE_SM100A=OFF`
  - `SGL_KERNEL_ENABLE_FP4=OFF`
  - `CMAKE_BUILD_PARALLEL_LEVEL=2` was requested.
- CMake failure: `Could not find one of the following names: Torch.cps, torch.cps, TorchConfig.cmake, torch-config.cmake`.
- Build result: `BUILD_RC=2`; remote result: `REMOTE_RC=2`.
- Hard timeout was 1200 seconds; the command terminated in about 6 seconds during CMake configuration, not due to timeout.
- No `dist/*.whl` was present after the failed build.
- Exact remote log preserved at:
  `/root/sglang-3060-12g-hicache/python/sglang/kernels/aot/OPS-20260908-3060-KERNEL-CUDA12-NARROW-051.build.log`
  (4080 bytes; mtime `2026-09-08 23:04:09 +0800`).

## Changed resources

- Remote: fresh `/root/sglang-3060-12g-hicache/python/sglang/kernels/aot/build/` was created by the defined build process; the exact failure log above was created.
- Local: this report only.

## Followups

None within this Task ID. Any further remediation or alternate build procedure requires a new Task ID.

## Open issues

- The configured environment does not expose a discoverable Torch CMake package to CMake, despite `CMAKE_PREFIX_PATH` containing `/root/sglang-env-3060-4b/lib/python3.11/site-packages`.
