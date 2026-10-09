# REV-20260908-3060-MINIMAL-KERNEL

ENTRY: ACCEPT

task_id: D3060-REVIEW-060
orchestration_epoch: 2026-09-08
role: reviewer
status: done
invocation_status: done
verdict: REJECT

## Summary

The default 3090 path is preserved, but the opt-in minimal path is not buildable as
committed. `SGL_KERNEL_MINIMAL_SM86=ON` removes CUDA translation units while retaining
`csrc/common_extension.cc` in both common targets. That registration unit unconditionally
takes function addresses whose only definitions are in the removed files. The option must
therefore be rejected until the source list and registrations are made consistent.

## Findings

### BLOCKER-1 — opt-in source list leaves unresolved AOT registrations

Locations:

- `python/sglang/kernels/aot/CMakeLists.txt:258-316,322-340`
- `python/sglang/kernels/aot/CMakeLists.txt:355-372`
- `python/sglang/kernels/aot/csrc/common_extension.cc:46-50,93-97,155-192,215-240,379-398,468-480`

Evidence:

- `common_extension.cc` remains in `SOURCES` at line 263, and both
  `common_ops_sm90_build` and `common_ops_sm100_build` consume the filtered `${SOURCES}`.
- The filter removes the definitions for `cutlass_mla_decode` and
  `cutlass_mla_get_workspace_size`, `concat_mla_k` and `concat_mla_absorb_q`, the
  vertical/slash conversion functions, all three expert-specialization entry points,
  the W4A8 CUTLASS MoE entry/data functions, `fp8_blockwise_scaled_grouped_mm`, the
  MoE align/top-k/sum/prepare functions, and `fused_qk_norm_rope`.
- `common_extension.cc` still passes the addresses of those functions to `m.impl`.
  The corresponding source files contain the only definitions found by static search.

Acceptance impact: an enabled build cannot reliably link/load `common_ops`; unused
runtime paths do not make this safe because the registration object is initialized when
the extension is loaded. Consequently this commit cannot support the requested SM86
Qwen3.5-4B build/runtime path.

Required followup: either retain every translation unit required by
`common_extension.cc`, or conditionally remove the matching declarations/registrations
and any Python imports under the same feature contract. Add a static source-to-registration
check and complete an enabled build/import check before re-review.

## Independent path assessment

- The dense Qwen3.5 model path itself selects `Qwen2MoeMLP` rather than the sparse-MoE
  block (`python/sglang/srt/models/qwen3_5.py:813-837`), and its fused QK norm/RoPE path
  is supplied through the JIT attention implementation rather than the removed AOT MoE
  file. This supports the runtime rationale for excluding MoE/MLA work, but it does not
  solve the unconditional AOT registration/link dependency above.
- The inspected W4A16 implementation uses the Marlin/JIT quantization path
  (`CompressedTensorsWNA16` and `gptq_marlin_repack`/`ops.marlin_gemm`); the filter does
  not remove the AOT AWQ/GPTQ source entries. No missing dense-W4A16 source dependency
  was found beyond the registration blocker.
- The new option does not itself add an explicit SM86 gencode to the common target. The
  repository's common flags list SM80/SM89/SM90, while the explicit SM86 flag appears in
  the separate FA3 block. The coder's remote CMake log reports environment/toolchain
  autodetection of SM86, but that is not guaranteed by this commit and remains an
  independent build-artifact followup.

## Default 3090 compatibility evidence

- Commit parent is `d49214e59228a555dc9f878426928a8a628d8848`, equal to local
  `3090-24g-opt`; local `3090-24g-hicache` and both origin 3090 refs have the same
  baseline CMake file content.
- Read-only parser check: parent, current default source block, and local authoritative
  `3090-24g-opt` each contain 50 entries; parent/current and parent/3090 source lists are
  equal. The new option is explicitly `OFF`; the 17 removals are unique and all are
  members of the default list; the filter occurs before both common targets.
- `git diff --check` passed. The committed diff changes only
  `python/sglang/kernels/aot/CMakeLists.txt` and leaves existing option declarations and
  default source ordering unchanged. With the option left `OFF`, the conditional list
  mutation is not executed.

## Verification limits

- No product files or remote host were modified.
- Only read-only/static checks were run. Local `cmake` is unavailable, and no CUDA build,
  extension link/load, model load, or runtime test was performed. The coder report likewise
  records no completed CMake/CUDA build.

## Artifacts

- Review report: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/REV-20260908-3060-MINIMAL-KERNEL.md`
- Reviewed commit: `4e1e7cfeb5ea35751338f821b8e27809b26b5ef5`
- Coder report: `COD-20260908-3060-MINIMAL-KERNEL.md`

## Followups

- Fix the opt-in source/registration dependency mismatch and obtain a fresh independent
  review task.
- Re-run static source-list and registration coverage checks, then build/import the ON path
  on SM86 and verify the selected dense W4A16/Marlin execution path.
- Preserve the existing OFF/default 3090 comparison as a regression check.

## Open issues

- No enabled minimal artifact exists; linker/import behavior is statically blocked by the
  unresolved registration set.
- Native SM86 code generation for the common target is not established by the committed
  CMake option alone.
- No target-host Qwen3.5-4B W4A16 runtime evidence is available in this review scope.

Extra work requires a fresh Task ID.
