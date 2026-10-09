# G3-IQ3-SM86-LOCAL-ARTIFACT-20260909

## Invocation

- Stable Task ID: `G3-IQ3-SM86-LOCAL-ARTIFACT-20260909`
- Invocation ID: `INV-G3-IQ3-SM86-LOCAL-ARTIFACT-001`
- Epoch: `E11`
- Role: `devops-executor`
- Status: `done`

## Scope and procedure

Read-only local inspection only. No process was started, stopped, or modified; no driver,
environment, or product file was changed. Commands and output were captured in the task
conversation and checked against the local worktree.

## Findings

At `2026-09-09 15:59:01` local `nvidia-smi -i 1` reported:

- GPU 1: NVIDIA GeForce RTX 3090, driver `580.178.04`, CUDA `13.0`
- Temperature `34C`, power `21W / 250W`, utilization `0%`
- Memory `37MiB / 24576MiB`
- Only desktop processes (`gnome-shell` PID 3168 and a desktop process PID 4543) were listed.
- No `gpu_burn`, `cmake --build`, `ninja`, or `nvcc` process was present.

The local worktree contains commit `5c5f5e3b25bc04fb5c37dbff31bc531d71ea9143`, whose only
committed change is the SM86 AOT gencode addition in `python/sglang/kernels/aot/CMakeLists.txt`.

No local `common_ops*.so`, `*.abi3.so`, or other compiled shared library was found under the
workspace, and no local `cmake-build*`, `*sm86*`, or `*isolated*` build directory was found in
the inspected `/home/dev-codex` tree. Therefore no local compiled artifact path, SHA-256, or
ELF architecture can be verified from this workstation.

## Acceptance

GPU1 is available for a future queued test. The local SM86 source correction is present in the
committed worktree, but a resulting local `.so` artifact is absent/unavailable for inspection.
This report does not assert that the separate remote isolated build completed.

## Followups / open issues

- Before deployment, obtain or build a local/remote isolated `.so` and inspect it with
  `cuobjdump --list-elf` (expect native `sm_86`) and record its hash.
- Queue any GPU workload behind the user's other process; this inspection found the GPU idle.

