# REV-20260909-3060-MINIMAL-KERNEL-FIX2

ENTRY: ACCEPT

task_id: D3060-REVIEW-068
orchestration_epoch: 2026-09-09
role: reviewer
status: done
invocation_status: done
verdict: ACCEPT

## Summary

The final minimal-SM86 source/registration closure is accepted for the requested
source-only scope. The ON source filter removes 17 providers, and every
registration reference to those providers is excluded by
`SGL_KERNEL_MINIMAL_SM86`. The retained registrations resolve to retained local
sources or to external source entries that remain in the CMake source list. The
OFF/default 3090 source and registration behavior is preserved by static
comparison.

No CUDA configure, compile, link/load, extension import, model load, or runtime
claim is made.

## Findings

None.

## Independent evidence

- Reviewed commit `a76cce39723654cb93ee186b9c3fb570961d7794` on branch
  `3060-12g-qwen35-4b`. The commit changes only
  `python/sglang/kernels/aot/csrc/common_extension.cc`, adding the guard around
  `shuffle_rows` and `apply_shuffle_mul_sum` at lines 200-206.
- CMake inspection at
  `python/sglang/kernels/aot/CMakeLists.txt:256-340,353-384` found 50 default
  source entries and 17 unique minimal removals. Every removal is a member of
  the default list, and all 17 are removed only inside
  `if (SGL_KERNEL_MINIMAL_SM86)`. Both common targets consume the filtered
  `${SOURCES}` list at lines 355 and 369.
- Both `common_ops_sm90_build` and `common_ops_sm100_build` receive
  `SGL_KERNEL_MINIMAL_SM86=1` only inside the same option conditional at lines
  381-384.
- `common_extension.cc` includes only the CUDA/Torch headers and the shared
  `sgl_kernel_ops.h` at lines 15-19; it has no include of a removed
  translation unit or removed-source-specific header. The shared header's
  declarations do not create link references without an address being used.
- The independent registration scan covered all 86 address-taken registration
  references in `common_extension.cc`, including direct `m.def(..., &provider)`
  registrations. It found 21 provider symbols belonging to the 17 removed
  source files. All 21 are inside `#ifndef SGL_KERNEL_MINIMAL_SM86` blocks:
  the existing 19 guards plus `shuffle_rows` and `apply_shuffle_mul_sum` at
  lines 200-206. This includes `cutlass_mla_get_workspace_size`, which is a
  direct `m.def` pointer registration at lines 46-52.
- With the simulated ON source set, 65 active registration pointers all had a
  provider in a retained local CMake source or in the retained FlashInfer/
  Flash-Attention source entries. No active registration lacked a retained
  provider.
- OFF/default checks passed independently: current and parent CMake `SOURCES`
  blocks are identical (50 entries); removing the newly added guard directives
  from the current `common_extension.cc` produces the parent body exactly; and
  the option remains `OFF` by default. The external provider entries for
  FlashInfer norm/renorm and sparse Flash-Attention also remain in `SOURCES`.
- `git diff --check a76cce39723654cb93ee186b9c3fb570961d7794^ a76cce39723654cb93ee186b9c3fb570961d7794` passed. The reviewed worktree was
  clean.

## Acceptance impact

The prior blocker concerning the two unguarded providers from
`csrc/moe/prepare_moe_input.cu` is resolved. The minimal ON source list and the
registration unit now have matching boundaries. Default/OFF behavior remains
unchanged by static source and preprocessor-body comparison.

## Residual risk and open issues

- Target-host CUDA build/import/runtime verification remains unperformed and is
  outside this source-only review. This verdict does not imply runtime success.
- Minimal mode intentionally omits the removed operations; callers that invoke
  those operations explicitly will not find their registrations. Compatibility
  of such callers is outside this closure task.

## Followups

- Run the separately authorized target-host minimal ON build/import verification.
- Preserve the static ON provider scan and OFF/default comparison for future
  changes to the minimal source set.

## Artifacts

- Reviewed commit: `a76cce39723654cb93ee186b9c3fb570961d7794`
- Coder report: `COD-20260908-3060-MINIMAL-KERNEL-FIX2.md`
- This report:
  `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/REV-20260909-3060-MINIMAL-KERNEL-FIX2.md`

Extra work requires a fresh Task ID.
