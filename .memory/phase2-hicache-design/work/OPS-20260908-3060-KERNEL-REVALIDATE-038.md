# OPS-20260908-3060-KERNEL-REVALIDATE-038

- invocation: `done`
- Task ID: `D3060-KERNEL-REVALIDATE-038`
- orchestration epoch: `20260908-3060`
- role: `devops-executor`
- scope: read-only revalidation of `D3060-KERNEL-REBUILD-034`
- remote target: `root@i-1.gpushare.com:27460` (credential omitted)
- observation time: `2026-09-08T22:26:46+08:00` (remote)
- changed resources: none; no stop, install, delete, or modification performed

## Commands executed

1. SSH read-only inspection using `ps`, `find`, `df`, and `df -i` over `/root`, `/workspace`, `/opt`, and `/tmp`.
2. SSH read-only inspection in `/root/sglang-3060-12g-hicache/python/sglang/kernels/aot` using `stat`, `tail`, `find`, `ps`, and `nvidia-smi`.

The password was supplied to `sshpass` via an environment variable and was not printed.

## Evidence

### PID chain / terminal state

The rebuild remains active. Observed chain:

`18630 bash` -> `18631 timeout 900s` -> `18633 uv build --wheel` -> `18636 python ... build_wheel` -> `18836 cmake --build` -> `18837 ninja -j 2` -> `18838 sh -c nvcc` -> `18840 nvcc`.

At the second check, the timeout chain was still present with elapsed times:

- PID 18630: `Ss`, `13:16`
- PID 18631: `S`, `13:16`, command explicitly includes `timeout 900s`
- PID 18633: `Sl`, `13:16`
- PID 18636: `Sl`, `13:16`
- PID 18836: `S`, `13:09`
- PID 18837: `S`, `13:09`
- PID 18838: `S`, `13:09`
- PID 18840: `S`, `13:09`

An active CUDA compiler descendant was also observed: PID 19196 `cicc`, state `R`, elapsed `03:05`, compiling `cutlass_mla_kernel.cu` for `compute_89`. No `BUILD_RC=` line was present in the inspected log tail, so the build had not reached terminal success/failure at observation time. No build `.pid`, `.status`, `.done`, or `.timeout` marker was found (apart from unrelated `/tmp/supervisord.pid`).

### Latest build log tail

`/root/sglang-3060-12g-hicache/python/sglang/kernels/aot/OPS-20260908-3060-KERNEL-REBUILD-034.build.log`

- mtime: `2026-09-08 22:20:14.846112393 +0800`
- size: `5380` bytes
- tail ended at Ninja progress `[3/498]` after CMake configuration/generation.
- The tail showed CUDA toolkit 12.4, autodetected architecture `8.6`, and active compilation. It also contained non-fatal CMake warnings about missing NVTX3, disabled optional CUDA libraries, and missing `kineto_LIBRARY`.

### Wheel / dist artifacts

`dist/` contained only:

`2026-09-08 20:42:10.8276984200 1 dist/.gitignore`

No wheel was present in the target `dist/` directory. The broader read-only artifact scan found only older temporary wheels:

- `/tmp/pip-unpack-plosyort/sglang_kernel-0.4.6.post1-cp310-abi3-manylinux2014_x86_64.whl`, 17,301,504 bytes, mtime `20:55:17`
- `/tmp/pip-unpack-1m77l4l8/sglang_kernel-0.4.6.post1-cp310-abi3-manylinux2014_x86_64.whl`, 17,039,360 bytes, mtime `20:54:05`

These are not outputs of the active rebuild based on their location/time and were not modified.

### Build outputs and disk

Recent object outputs existed under `build/`, including `topk.cu.o` (934,952 bytes, mtime `22:20:14`) and `pos_enc.cu.o` (227,432 bytes, mtime `22:19:36`), but no wheel or final package artifact was present.

Disk evidence:

- `/` overlay: `30G` total, `5.1G` used, `25G` available, `17%`
- `/hy-tmp`: `50G` total, `6.7G` used, `44G` available, `14%`
- root filesystem inode use: `3%`
- `/hy-tmp` inode use: `3%`

GPU snapshot: NVIDIA GeForce RTX 3060, `0%` utilization, `2 MiB / 12288 MiB` memory.

## Summary

`D3060-KERNEL-REBUILD-034` is still running and has not reached a terminal state. The 900-second timeout wrapper is active at this observation, the latest log is advancing only through early Ninja progress (`[3/498]` in its tail), `dist/` has no newly produced wheel, and disk/inode capacity is ample.

## Followups

- Revalidate later with a new Task ID if terminal completion or timeout evidence is required.

## Open issues

- Current final build result is unknown because the process remains active; no completion return code has been recorded.
- No wheel artifact has been emitted to `dist/` as of the observation.
