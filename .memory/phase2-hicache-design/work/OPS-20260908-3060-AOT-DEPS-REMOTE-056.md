# OPS-20260908-3060-AOT-DEPS-REMOTE-056

Status: pending (build actively running)

## Scope

Authorized target: `root@i-1.gpushare.com:27460`, dependency staging under
`/hy-tmp/d3060-aot-deps`, AOT source under
`/root/sglang-3060-12g-hicache/python/sglang/kernels/aot`, environment
`/root/sglang-env-3060-4b`. No driver/Torch upgrade, fake libraries, model/server/benchmark,
or 3090 changes were performed.

## Completed evidence

- Local archives were present under `/tmp/d3060-aot-deps`.
- Uploaded archives were verified remotely with these SHA-256 values:
  - FlashMLA: `77d3f1714b5903dc8f7a99fbc3a5d9a2b886e449f994b6c4b1d2feeacb467b1e`
  - FlashMLA CUTLASS: `9f6c53320a85b4a570975e557918cde65168cd311f081920446c238437347dc6`
  - repo-cutlass: `09237099a70f80bff1dc8bb80c843a674bb4fdcb46e43cc6993e711c5ca89bb5`
  - repo-flash-attention: `418b5681584dc3efff496a1cab5ffd58d2728d89dcfe0ea16e6985d6ef35c68c`
  - repo-flashinfer: `931dfd118f4b6de8c7d98702153c7c03840139170af21a07607693bd9749744d`
  - repo-fmt: `c314292789d28c3c3b420e75a7b2d1706f685f7fb63289128d46aeaea2c6be71`
  - repo-triton: `7d998625d1035ac496d06a81117727647169422ee67b8889609f06fd5367c491`
- Extracted override roots exist under `/hy-tmp/d3060-aot-deps/repo-*`, including
  `repo-flashmla` and `repo-flashmla-cutlass`.
- CMake configuration completed on the corrected attempt; it detected CUDA 12.4 and
  autodetected compute capability 8.6 (SM86). The build uses Ninja `-j 2`.

## Build evidence

Remote log: `/root/sglang-3060-12g-hicache/python/sglang/kernels/aot/OPS-20260908-3060-AOT-DEPS-REMOTE-056.build.log`

Two pre-compilation configuration attempts are preserved in that exact log. The first
failed to discover Torch until the torch-derived prefix was also exposed as
`CMAKE_PREFIX_PATH`; the second had a transient typo in the Triton path; the corrected
attempt is now compiling. At `2026-09-08T23:25:55+08:00`, the active process was the
1200-second-bounded `uv build`, with log progress through `[4/131]`.

No wheel, install, import verification, or final build return code exists yet.

## Commands and outputs

- `scp` uploaded all seven archives to `/hy-tmp/d3060-aot-deps`.
- Remote `find ... | xargs sha256sum` matched all seven archive hashes above.
- Remote `tar -xzf` extraction completed for the base archives; FlashMLA and CUTLASS
  were extracted into the explicit override roots.
- Build command: `/root/sglang-env-3060-4b/bin/python -m uv build --wheel
  -Cbuild-dir=build-OPS-20260908-3060-AOT-DEPS-REMOTE-056 . --no-build-isolation`,
  wrapped with `timeout --signal=TERM --kill-after=30s 1200s`, with requested CUDA,
  parallelism, feature-disable, below-SM90, and FETCHCONTENT source overrides.

## Changed resources

- Remote dependency files and extracted directories under `/hy-tmp/d3060-aot-deps`.
- Remote build directory `build-OPS-20260908-3060-AOT-DEPS-REMOTE-056`.
- Remote exact build log listed above.
- This report only.

## Followups

Continue monitoring the existing build process. If it completes successfully, install the
wheel and run `import sgl_kernel` plus CUDA/SM86 verification as already authorized. If it
fails, preserve the exact log and update this report with the final return code and evidence.

## Open issues

- Build is still running; terminal outcome and wheel availability are unresolved.
