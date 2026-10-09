# OPS-20260909-3060-MINIMAL-BUILD-CORRECT-SOURCE

status: blocked
invocation: D3060-OPS-074
epoch: 2026-09-09
role: devops-executor

## Summary

Controlled stop before build. The exact restored source passed the source/hash/marker
gate, but the first configure used incorrect plain `-DREPO-*` arguments for six local
dependencies. CMake therefore attempted a `repo-fmt` FetchContent download. The active
configure was stopped as requested; no build or artifact was produced. A fresh task is
required with the exact `FETCHCONTENT_SOURCE_DIR_REPO-*` flags.

## Commands and evidence

Remote target: `root@i-1.gpushare.com:27460`, BatchMode SSH key
`/home/dev-codex/.ssh/sglang_3060_ed25519`.

Source gate command:

```text
SOURCE=/root/sglang-3060-12g-hicache
test -f "$SOURCE/python/sglang/kernels/aot/CMakeLists.txt"
sha256sum "$SOURCE/python/sglang/kernels/aot/CMakeLists.txt" \
  "$SOURCE/python/sglang/kernels/aot/csrc/common_extension.cc"
```

Observed:

```text
CMAKE_PRESENT=0
CMAKE_SIZE=23773
54467a0b0cdb59846dafb82e2c08896b1d61f58d399f8cfab9045b2ba0293724  CMakeLists.txt
91580c591d5cd4f617c6c47f8c9a184395e15a6d13f56b1e211fe56ebe08cf89  common_extension.cc
.reviewed-source-commit: a76cce39723654cb93ee186b9c3fb570961d7794
```

The two hashes match the reviewed local source report. Required tools were present:
CMake 4.4.3, Ninja 1.13.2, CUDA 12.4. The seven dependency directories were present.

Initial configure with the incorrect flags created:

```text
/hy-tmp/d3060-aot-build-correct-source-20260909-004420
/hy-tmp/d3060-aot-configure-correct-source-20260909-retry.log (13328 bytes)
```

The preserved log ends with:

```text
FAILED: ... repo-fmt-populate-download ...
Build step for repo-fmt failed: 1
-- Configuring incomplete, errors occurred!
```

Cache inspection showed:

```text
FETCHCONTENT_SOURCE_DIR_REPO-CUTLASS=/hy-tmp/d3060-aot-deps/repo-cutlass
FETCHCONTENT_SOURCE_DIR_REPO-FMT=            (empty)
REPO-FMT=/hy-tmp/d3060-aot-deps/repo-fmt
REPO-TRITON=/hy-tmp/d3060-aot-deps/repo-triton
REPO-FLASHINFER=/hy-tmp/d3060-aot-deps/repo-flashinfer
REPO-FLASH-ATTENTION=/hy-tmp/d3060-aot-deps/repo-flash-attention
REPO-FLASHMLA=/hy-tmp/d3060-aot-deps/repo-flashmla
REPO-FLASHMLA-CUTLASS=/hy-tmp/d3060-aot-deps/repo-flashmla-cutlass
```

After stopping, a read-only process check found no active matching CMake, Ninja, NVCC,
FetchContent, or git download process. Logs and the incomplete build directory were
preserved. No source, local product, 3090, or dependency files were changed.

## Verification

- Exact source path: PASS.
- Reviewed source hashes: PASS.
- Reviewed marker: PASS.
- Configure: BLOCKED by unauthorized network FetchContent attempt caused by incorrect flags.
- Build: NOT RUN.
- Import/loadability: NOT RUN.
- Artifact path/size/hash: NONE.
- Rollback: not applicable; no source or dependency mutation performed.

## Followups

Fresh Task ID required. The next invocation must pass the exact six flags:
`FETCHCONTENT_SOURCE_DIR_REPO-FMT`, `..._REPO-TRITON`, `..._REPO-FLASHINFER`,
`..._REPO-FLASH-ATTENTION`, `..._REPO-FLASHMLA`, and `..._REPO-FLASHMLA-CUTLASS`,
then verify no download subprocess before `ninja -j1`.

## Open issues

- No build result or loadability evidence exists because configure was intentionally stopped.
- The first failed configure left an incomplete build directory under `/hy-tmp`; it was
  preserved and not reused.
