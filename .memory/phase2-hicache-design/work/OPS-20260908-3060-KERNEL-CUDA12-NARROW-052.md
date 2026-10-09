# OPS-20260908-3060-KERNEL-CUDA12-NARROW-052

status: blocked
task_id: D3060-KERNEL-CUDA12-NARROW-052
orchestration_epoch: 20260908-3060
role: devops-executor

## Summary

The authorized CUDA 12 narrow AOT retry reached CMake/Torch discovery and detected
SM86, but failed before compilation while fetching the pinned CUTLASS source. No
wheel was completed; therefore no install or `sgl_kernel` verification was run.

## Authorized procedure and configuration

- Remote target: `root@i-1.gpushare.com:27460`.
- Source: `/root/sglang-3060-12g-hicache/python/sglang/kernels/aot`.
- Python: `/root/sglang-env-3060-4b/bin/python`.
- `CUDA_HOME=/usr/local/cuda-12.4`.
- `CUDACXX=/usr/local/cuda-12.4/bin/nvcc`.
- `MAX_JOBS=2` and `CMAKE_BUILD_PARALLEL_LEVEL=2`.
- `TORCH_CMAKE_PREFIX` was computed with:
  `/root/sglang-env-3060-4b/bin/python -c 'import torch; print(torch.utils.cmake_prefix_path)'`
- Computed prefix: `/usr/local/lib/python3.11/dist-packages/torch/share/cmake`.
- `CMAKE_PREFIX_PATH` was set to that prefix.
- `CMAKE_ARGS` included `-DCMAKE_PREFIX_PATH=<computed prefix>` and disabled:
  `SGL_KERNEL_ENABLE_FA3`, `SGL_KERNEL_ENABLE_SM90A`,
  `SGL_KERNEL_ENABLE_SM100A`, and `SGL_KERNEL_ENABLE_FP4`.
- Fresh build directory: `build-OPS-20260908-3060-KERNEL-CUDA12-NARROW-052`.
- Build command: `timeout 1200s /root/sglang-env-3060-4b/bin/python -m uv build --wheel -Cbuild-OPS-20260908-3060-KERNEL-CUDA12-NARROW-052 . --color=always --no-build-isolation`.

## Preserved log

Remote log:
`/root/sglang-3060-12g-hicache/python/sglang/kernels/aot/OPS-20260908-3060-KERNEL-CUDA12-NARROW-052.build.log`

Observed log markers:

```text
CUDA_HOME=/usr/local/cuda-12.4
CUDACXX=/usr/local/cuda-12.4/bin/nvcc
MAX_JOBS=2
TORCH_CMAKE_PREFIX=/usr/local/lib/python3.11/dist-packages/torch/share/cmake
-- Found Torch: /usr/local/lib/python3.11/dist-packages/torch/lib/libtorch.so
-- Autodetected CUDA architecture(s):  8.6
-- Added CUDA NVCC flags for: -gencode;arch=compute_86,code=sm_86
```

Exact terminal failure:

```text
CMake Error at .../FetchContent.cmake:1933 (message):
  Build step for repo-cutlass failed: 1
...
error: downloading 'https://github.com/NVIDIA/cutlass/archive/57e3cfb47a2d9e0d46eb6335c3dc411498efa198.tar.gz' failed
status_code: 35
status_string: "SSL connect error.  If this is due to certificate verification failure..."
SSL routines::unexpected eof while reading
BUILD_RC=2
=== END 2026-09-08T23:08:24+08:00 FINAL_RC=2 ===
```

## Changed resources

- Created the fresh remote build directory named above; it contains the partial
  CMake/FetchContent state from this attempt.
- Created/updated the preserved remote build log named above.
- No wheel installation occurred.
- No model, server, benchmark, Torch/driver upgrade, fake library, or 3090
  resource was touched.
- This report is the only local artifact written for the task.

## Verification evidence

- CMake successfully found Torch and configured the CUDA compiler as CUDA 12.4.
- CMake selected only `compute_86`/`sm_86`.
- The build exited with code 2 during dependency fetch, before wheel creation.
- Install and `sgl_kernel/SM86` verification were correctly not attempted because
  the wheel did not complete.

## Followups

Retry requires resolution of the remote GitHub TLS/download failure under a new
Task ID. No alternative procedure was selected.

## Open issues

- CUTLASS archive download failed repeatedly with TLS error 35; this is the sole
  blocking failure observed in this invocation.
