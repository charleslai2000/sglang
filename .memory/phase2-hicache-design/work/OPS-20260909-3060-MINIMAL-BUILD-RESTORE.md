# D3060-OPS-071 — minimal-SM86 restore/build report

Status: blocked

## Scope and procedure

- Task: D3060-OPS-071, epoch 2026-09-09.
- Target: `root@i-1.gpushare.com:27460` only, using BatchMode key `/home/dev-codex/.ssh/sglang_3060_ed25519`.
- Source restored from `/hy-tmp/d3060-a76cce39723654cb93ee186b9c3fb570961d7794.tar.gz`.
- Existing source was preserved at `/hy-tmp/sglang-3060-12g-hicache-backup-20260909-003306`.
- No local product files or 3090 branches were modified.

## Evidence

Archive SHA256:

`a71a3bebd0c2577141a013a6a76b6a3eda1fd740c4283c9a78b89a8a502d3f9e`

Restored source marker:

`/root/sglang-3060-12g-hicache/.reviewed-source-commit` = `a76cce39723654cb93ee186b9c3fb570961d7794`

Required restored-source hashes:

- `python/sglang/kernels/aot/CMakeLists.txt`: `54467a0b0cdb59846dafb82e2c08896b1d61f58d399f8cfab9045b2ba0293724`
- `python/sglang/kernels/aot/csrc/common_extension.cc`: `91580c591d5cd4f617c6c47f8c9a184395e15a6d13f56b1e211fe56ebe08cf89`

The venv reported CMake `4.4.3` and Ninja `1.13.2.git.kitware.jobserver-pipe-1`. CUDA compiler was explicitly set to `/usr/local/cuda-12.4/bin/nvcc`; GPU state was RTX 3060, 12288 MiB total, 12037 MiB free.

## Commands and results

1. Reverified archive hash and extracted a new `/hy-tmp/d3060-source-20260909-003306` with `--strip-components=1`.
2. Verified both required hashes before activation.
3. Renamed the old source to the timestamped backup and moved the verified tree atomically into `/root/sglang-3060-12g-hicache`.
4. Created the reviewed-source marker.
5. Ran venv CMake/Ninja configure with `SGL_KERNEL_MINIMAL_SM86=ON`, CUDA 12.4, `CMAKE_CUDA_ARCHITECTURES=86`, Torch CMake prefix, `/hy-tmp/d3060-aot-deps`, and `-j1` build gating.
6. The first configure stopped because `nvcc` was not on PATH; rerun used the verified CUDA 12.4 compiler path.
7. Subsequent configure attempts were stopped after they attempted network FetchContent downloads. Existing logs and build trees were preserved. The final rerun included the requested override:

`-DFETCHCONTENT_SOURCE_DIR_REPO-FLASH-ATTENTION=/hy-tmp/d3060-aot-deps/repo-flash-attention`

The final attempt still reached a nested `repo-flashmla-cutlass` download path and was stopped. No successful configure or build artifact was produced.

## Logs and resource evidence

- Combined log: `/hy-tmp/d3060-minimal-sm86-20260909-003306.log`
- Build trees preserved under `/hy-tmp/d3060-aot-build-20260909-003306*`.
- Final recorded result: `RESULT_RC=143` after intentional stop of the network-stalled configure.
- Final resource snapshot: `/hy-tmp` 50G total, 8.2G used, 42G available; memory 125Gi total, 41Gi free, 116Gi available, no swap.
- No `.so` or `.a` artifact was produced and therefore no import/loadability verification was possible.

## Open issues

The reviewed procedure cannot reach configuration completion while CMake's nested FetchContent logic attempts remote downloads despite the staged dependency directory and the requested flash-attention override. Further dependency-name/path reasoning or another method requires a fresh Task ID; no further changes were made in this task.
