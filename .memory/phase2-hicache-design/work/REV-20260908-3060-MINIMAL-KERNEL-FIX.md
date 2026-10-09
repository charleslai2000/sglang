# REV-20260908-3060-MINIMAL-KERNEL-FIX

ENTRY: ACCEPT

task_id: D3060-REVIEW-066
orchestration_epoch: 2026-09-08
role: reviewer
status: done
invocation_status: done
verdict: REJECT

## Summary

The repaired boundary remains incomplete. The commit correctly propagates
`SGL_KERNEL_MINIMAL_SM86=1` to both common extension targets and guards the 19
registrations previously identified, but `prepare_moe_input.cu` provides three
registered CUDA operations. Only `prepare_moe_input` is guarded. `shuffle_rows`
and `apply_shuffle_mul_sum` remain unconditionally registered after their sole
provider source is removed, so the enabled common extension still has unresolved
registration/provider references.

## Findings

### BLOCKER-1 — two registrations still reference a removed translation unit

Locations:

- `python/sglang/kernels/aot/CMakeLists.txt:318-340`
- `python/sglang/kernels/aot/csrc/common_extension.cc:200-204`
- `python/sglang/kernels/aot/csrc/moe/prepare_moe_input.cu:253-256,386-392`

Evidence:

- With `SGL_KERNEL_MINIMAL_SM86=ON`, line 339 removes
  `csrc/moe/prepare_moe_input.cu` from `SOURCES`.
- `common_extension.cc:200-204` unconditionally takes the addresses of
  `shuffle_rows` and `apply_shuffle_mul_sum`.
- Static definition search found the only local providers for those symbols in
  the removed `prepare_moe_input.cu` at lines 253 and 386. No retained source
  provides either symbol.
- An independent guard/provider scan found 21 registration references whose
  providers are in removed sources: the 19 intended references are guarded by
  `#ifndef SGL_KERNEL_MINIMAL_SM86`, while these two are not:

  ```text
  shuffle_rows             common_extension.cc:201  guarded=false
  apply_shuffle_mul_sum    common_extension.cc:204  guarded=false
  ```

Acceptance impact: the ON path still cannot be accepted as a consistent
source/registration boundary. The registration unit can retain unresolved
function references when the removed source is omitted. This blocks the
requested minimal artifact independently of any CUDA build or runtime claim.

Required correction: either retain `prepare_moe_input.cu` in the minimal source
set, or put both registrations (their `m.def` schemas and `m.impl` calls) under
the same `#ifndef SGL_KERNEL_MINIMAL_SM86` contract. Then rerun the complete
removed-source/provider scan and obtain a fresh independent review.

## Passing checks

- Reviewed branch is `3060-12g-qwen35-4b` at
  `495ea91522605e0aebfa88576f1d1c5fbfd6c48d`.
- CMake adds the compile definition to both `common_ops_sm90_build` and
  `common_ops_sm100_build` only inside `if (SGL_KERNEL_MINIMAL_SM86)` at lines
  381-384.
- The 17 minimal removals are all members of the 50-entry default source list;
  no removal is outside that list.
- The 19 originally identified removed-source registrations are all guarded,
  but the provider scan exposes the additional two unguarded registrations
  above.
- `git diff --check 495ea915^ 495ea915` passed.
- The reviewed worktree was clean before this report was written.

## OFF/default compatibility assessment

Static evidence supports preservation of the default 3090 source boundary:

- The complete default `SOURCES` block in the reviewed commit is equal to the
  parent commit's block (50 entries).
- The removal is conditional on `SGL_KERNEL_MINIMAL_SM86`; the option remains
  `OFF` by default.
- The added compile definitions are also conditional, so the macro is absent
  from both common targets when the option is `OFF`.
- The registration changes use `#ifndef SGL_KERNEL_MINIMAL_SM86`, so all
  registration blocks are active in the OFF/default preprocessing path.

This is static/diff evidence only; it does not claim a 3090 build, extension
load, or runtime result.

## Verification limits

- No product files, remote state, ledger, or reviewed artifact were modified.
- No CUDA configure, compile, link/load, extension import, model load, or
  runtime test was performed. `cmake` is unavailable in this review
  environment; `nvcc` is present but cannot substitute for the required project
  configure/build evidence.
- Python wrappers for the removed operations remain importable and will fail if
  explicitly called in minimal mode; that is a contract-level residual risk,
  not the blocker used for this verdict. The blocker is the native
  registration/provider mismatch above.

## Exact followup

After correcting the two registrations, run on the target SM86 environment:

```bash
cd /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/python/sglang/kernels/aot
CMAKE_ARGS="-DSGL_KERNEL_MINIMAL_SM86=ON" make build
```

Then independently verify that the built extension imports and that the selected
dense Qwen3.5-4B W4A16/Marlin path loads without invoking the removed operations.
Repeat the static ON/OFF source/provider checks and preserve the OFF/default
3090 comparison. These are required followups, not results of this review.

## Artifacts

- Review report: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/REV-20260908-3060-MINIMAL-KERNEL-FIX.md`
- Reviewed commit: `495ea91522605e0aebfa88576f1d1c5fbfd6c48d`
- Prior rejection: `REV-20260908-3060-MINIMAL-KERNEL.md`
- Coder report: `COD-20260908-3060-MINIMAL-KERNEL-FIX.md`

## Followups

- Guard or retain the two missing provider registrations and rerun the complete
  static source-to-registration check.
- Obtain target-host ON build/import evidence and independent runtime verification
  under a fresh task/review dispatch.
- Keep the static OFF/default 3090 compatibility evidence as a regression check.

## Open issues

- Minimal ON remains rejected because two unconditional registrations point at
  the removed `prepare_moe_input.cu` provider.
- No CUDA/build/runtime success is established by this review.
- Python-level availability/guarding for explicitly invoked removed operations
  remains outside this repair and should be resolved or documented by the
  minimal-mode contract owner.

Extra work requires a fresh Task ID.
