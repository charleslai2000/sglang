# OPS-20260909-3060-MINIMAL-BUILD-EXACT-LOCALDEPS

status: done (controlled stop; SM86 gate not satisfied)
task: D3060-OPS-075
role: devops-executor
epoch: 2026-09-09

## Scope and admission

ENTRY: ACCEPT. Authorized target was `root@i-1.gpushare.com:27460`, source
`/root/sglang-3060-12g-hicache`, `/hy-tmp` build/log/temp, venv
`/root/sglang-env-3060-4b`, and SSH key
`/home/dev-codex/.ssh/sglang_3060_ed25519` with BatchMode. No local product or
3090 files were changed. The build was stopped under the controlled-stop
instruction; no artifact or runtime success is claimed.

## Commands and evidence

SSH connectivity succeeded with BatchMode. Preflight observed:

- source CMakeLists exists; supplied reviewed marker was `a76cce39723654cb93ee186b9c3fb570961d7794`; observed file SHA-256 was `54467a0b0cdb59846dafb82e2c08896b1d61f58d399f8cfab9045b2ba0293724`;
- CMake `4.4.3`; Ninja `1.13.2.git.kitware.jobserver-pipe-1`;
- Torch prefix: `/usr/local/lib/python3.11/dist-packages/torch/share/cmake`;
- all seven staged dependency directories existed;
- `/hy-tmp`: 42 GiB available; memory available: 116 GiB; GPU: RTX 3060, 12,037 MiB free.

Fresh build: `/hy-tmp/d3060-aot-build-20260909-075`.

Configure used the exact requested CMake structure and all seven unmodified keys:
`FETCHCONTENT_SOURCE_DIR_REPO-CUTLASS`, `REPO-FMT`, `REPO-TRITON`,
`REPO-FLASHINFER`, `REPO-FLASH-ATTENTION`, `REPO-FLASHMLA`, and
`REPO-FLASHMLA-CUTLASS`, each pointing under `/hy-tmp/d3060-aot-deps`.
Configure exit was `0`; CMake reported “Configuring done” and “Generating done”.
Log: `/hy-tmp/d3060-aot-configure-20260909-075.log` (9,241 bytes).

Cache verification output showed all seven exact keys with the expected local
paths. The downloader-process check found only the diagnostic wrapper itself
matching the broad pattern; no independent git/curl/wget/CMake downloader was
present.

Build command started exactly as:

```text
/root/sglang-env-3060-4b/bin/ninja -C /hy-tmp/d3060-aot-build-20260909-075 -j1
```

The build entered `common_ops_sm90_build`; its observed NVCC command contained
`-gencode=arch=compute_90,code=sm_90`, `-gencode=arch=compute_80,code=sm_80`,
`-gencode=arch=compute_89,code=sm_89`, and
`-gencode=arch=compute_90a,code=sm_90a`, with no explicit SM86 gencode. This
cannot satisfy the 3060 SM86-native gate. Progress reached `[4/472]`.

Controlled stop: SIGTERM was sent to Ninja PID 29694. After five seconds no
Ninja or NVCC process remained; the preserved build log records
`ninja: build stopped: interrupted by user.` Final resources were `/hy-tmp` 42
GiB available, memory 116 GiB available, and GPU 12,037 MiB free.

## Artifacts and verification

No completed artifact, artifact size/hash, or `python -c 'import sgl_kernel'`
result is available or claimed. Preserved build log:
`/hy-tmp/d3060-aot-build-20260909-075.log` (507 bytes); configure log remains
9,241 bytes.

## Followups

A new coder task must add the minimal-mode SM86 architecture/output boundary
before another build attempt.

## Open issues

- No artifact or runtime success was claimed. No alternative procedure was
  attempted.
