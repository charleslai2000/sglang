# COD-20260908-3060-MINIMAL-KERNEL-FIX2

ENTRY: ACCEPT

task_id: D3060-CODE-067
orchestration_epoch: 2026-09-08
role: coder
status: done
invocation_status: done

## Summary

Closed the remaining minimal-SM86 registration gap. The `shuffle_rows` and
`apply_shuffle_mul_sum` schema/implementation registrations are now guarded by
`#ifndef SGL_KERNEL_MINIMAL_SM86`, matching their provider in
`csrc/moe/prepare_moe_input.cu`, which is removed from the source list when
minimal SM86 mode is enabled.

## Commit

- Branch: `3060-12g-qwen35-4b`
- Commit: `a76cce39723654cb93ee186b9c3fb570961d7794`
- Message: `build: guard remaining minimal SM86 registrations`

## Changed files

- `python/sglang/kernels/aot/csrc/common_extension.cc`
  - Added the minimal-SM86 guard around the two remaining registrations.

No CMake, wrapper, provider, remote-host, 3090-branch, or ledger files were changed.

## Verification evidence

- Static source/provider scan passed: 50 default source entries; 17 minimal
  removals; every removal is a member of the default source list.
- Static registration/provider scan passed: all 21 registration references
  whose providers exist only in removed sources are guarded by
  `SGL_KERNEL_MINIMAL_SM86`, including `shuffle_rows` and
  `apply_shuffle_mul_sum`.
- Static OFF/default check passed: the default `SOURCES` block equals the
  parent revision, and both common-target compile definitions remain inside
  the `SGL_KERNEL_MINIMAL_SM86` option block.
- `git diff HEAD^ HEAD --check`: passed.
- Post-commit working tree: clean on `3060-12g-qwen35-4b`.
- Exact committed product file: `python/sglang/kernels/aot/csrc/common_extension.cc`.

No CUDA configure, compile, link/load, extension import, model load, or runtime
success is claimed.

## Followups

- Obtain fresh independent review/acceptance for this commit.
- Run the target-host minimal ON build/import verification under its separately
  authorized task.

## Open issues

- Target-host CUDA/build/import/runtime verification remains unperformed and is
  outside this source-only repair.
- Python callers that explicitly invoke operations intentionally unavailable in
  minimal mode remain outside this task.

## Artifacts

- Implementation commit: `a76cce39723654cb93ee186b9c3fb570961d7794`
- This report: `COD-20260908-3060-MINIMAL-KERNEL-FIX2.md`

Extra work requires a fresh Task ID.
