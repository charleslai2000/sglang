# COD-20260908-3060-MINIMAL-KERNEL

ENTRY: ACCEPT

status: done
invocation_status: done
task_id: D3060-CODE-MINIMAL-KERNEL-059
orchestration_epoch: 20260908-3060
role: coder

## Artifacts

- Repository: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt`
- Branch: `3060-12g-qwen35-4b`
- Changed file: `python/sglang/kernels/aot/CMakeLists.txt`
- Commit: `4e1e7cfeb5ea35751338f821b8e27809b26b5ef5`
- Commit subject: `build: add minimal SM86 kernel source option`
- Worktree after commit: clean; branch remains `3060-12g-qwen35-4b`

## Summary

Added `SGL_KERNEL_MINIMAL_SM86`, default `OFF`, at `CMakeLists.txt:181`. When enabled,
the option applies `list(REMOVE_ITEM SOURCES ...)` after the unchanged 50-entry default
source list. The filter removes only MLA/sparse-attention, expert-specialization, and
MoE paths. Common extension, basic attention merge, activation/norm/copy/position/topk,
AWQ/GPTQ/generic quantization, kvcacheio transfer, Mamba, grammar, speculative sampling,
and the other default common sources remain available.

The FA3 and FlashMLA sections were not modified. With the option `OFF` (the default),
the `SOURCES` list is unchanged, so the 3090 behavior is preserved.

## Excluded-source rationale

Every excluded source is listed below; all paths existed in the baseline source list.

- `csrc/attention/cutlass_mla_kernel.cu` — CUTLASS MLA implementation with an SM100-only execution path; not an SM86 Qwen3.5-4B common kernel requirement.
- `csrc/attention/vertical_slash_index.cu` — sparse vertical/slash attention indexing helper; outside the Qwen3.5 hybrid basic-attention path.
- `csrc/elementwise/concat_mla.cu` — MLA-specific key concatenation kernels; not required by the target hybrid model path.
- `csrc/expert_specialization/es_fp8_blockwise.cu` — FP8 expert-specialization grouped GEMM path; not needed for dense W4A16.
- `csrc/expert_specialization/es_sm100_mxfp8_blockscaled.cu` — SM100 Blackwell MXFP8 expert-specialization path; unsupported/out of scope for SM86.
- `csrc/expert_specialization/es_sm100_mxfp8_blockscaled_group_quant.cu` — SM100 Blackwell MXFP8 expert group-quantization path; unsupported/out of scope for SM86.
- `csrc/moe/cutlass_moe/w4a8/scaled_mm_entry.cu` — CUTLASS W4A8 MoE entry point; target is W4A16 and not MoE.
- `csrc/moe/cutlass_moe/w4a8/w4a8_grouped_mm_c3x.cu` — CUTLASS grouped W4A8 MoE matmul; not needed for the target dense W4A16 path.
- `csrc/moe/cutlass_moe/w4a8/w4a8_moe_data.cu` — metadata/data support for the W4A8 MoE matmul path; not needed for the target dense W4A16 path.
- `csrc/moe/fp8_blockwise_moe_kernel.cu` — FP8 blockwise MoE grouped matmul; not needed for dense W4A16.
- `csrc/moe/fused_qknorm_rope_kernel.cu` — fused QK norm/rope kernel in the MoE kernel family; not needed for the target non-MoE hybrid path.
- `csrc/moe/moe_align_kernel.cu` — expert-token alignment and padding; only needed for MoE routing.
- `csrc/moe/moe_sum.cu` — expert-output top-k sum reduction; only needed for MoE outputs.
- `csrc/moe/moe_sum_reduce.cu` — expert-output reduction implementation; only needed for MoE outputs.
- `csrc/moe/moe_topk_sigmoid_kernels.cu` — sigmoid MoE router top-k kernels; only needed for MoE routing.
- `csrc/moe/moe_topk_softmax_kernels.cu` — softmax MoE router top-k kernels; only needed for MoE routing.
- `csrc/moe/prepare_moe_input.cu` — MoE expert-input preparation; only needed for MoE routing.

## Exact diff

```diff
@@ -178,6 +178,7 @@ option(SGL_KERNEL_ENABLE_FA3              "Enable FA3"              ${DEFAULT_SGL_KERNEL_ENABLE_FA3})
 option(SGL_KERNEL_ENABLE_FA3_SPARSE_MASK  "Enable FA3 sparse mask kernels" OFF)
 option(SGL_KERNEL_ENABLE_SM90A            "Enable SM90A"            OFF)
 option(SGL_KERNEL_ENABLE_SM100A           "Enable SM100A"           OFF)
+option(SGL_KERNEL_MINIMAL_SM86            "Build the reduced SM86 common kernel source set" OFF)
 
 if (SGL_KERNEL_ENABLE_BF16)
@@ -314,6 +315,31 @@ set(SOURCES
     "${repo-flash-attention_SOURCE_DIR}/csrc/flash_attn/flash_sparse_api.cpp"
 )
 
+if (SGL_KERNEL_MINIMAL_SM86)
+    # Qwen3.5-4B on SM86 does not require MLA, expert-specialization, or MoE
+    # kernels. Keep the complete default source list above unchanged so this
+    # opt-in filter cannot alter the 3090 build when disabled.
+    list(REMOVE_ITEM SOURCES
+        "csrc/attention/cutlass_mla_kernel.cu"
+        "csrc/attention/vertical_slash_index.cu"
+        "csrc/elementwise/concat_mla.cu"
+        "csrc/expert_specialization/es_fp8_blockwise.cu"
+        "csrc/expert_specialization/es_sm100_mxfp8_blockscaled.cu"
+        "csrc/expert_specialization/es_sm100_mxfp8_blockscaled_group_quant.cu"
+        "csrc/moe/cutlass_moe/w4a8/scaled_mm_entry.cu"
+        "csrc/moe/cutlass_moe/w4a8/w4a8_grouped_mm_c3x.cu"
+        "csrc/moe/cutlass_moe/w4a8/w4a8_moe_data.cu"
+        "csrc/moe/fp8_blockwise_moe_kernel.cu"
+        "csrc/moe/fused_qknorm_rope_kernel.cu"
+        "csrc/moe/moe_align_kernel.cu"
+        "csrc/moe/moe_sum.cu"
+        "csrc/moe/moe_sum_reduce.cu"
+        "csrc/moe/moe_topk_sigmoid_kernels.cu"
+        "csrc/moe/moe_topk_softmax_kernels.cu"
+        "csrc/moe/prepare_moe_input.cu"
+    )
+endif()
 
 set(INCLUDES
```

## Verification evidence

- `git diff --check` — passed before commit.
- Static source-list validation — passed:
  - default `SOURCES` block is byte-for-byte unchanged from `HEAD`;
  - parsed 50 default sources;
  - parsed exactly 17 opt-in removals;
  - all 17 filtered source paths exist;
  - 13 retained common/W4A16/hybrid sentinels remain unfiltered.
- Branch/worktree check — passed: branch is `3060-12g-qwen35-4b`, clean after commit.
- A direct CMake script execution check was not possible because `cmake` is not installed
  in the execution environment (`cmake: command not found`).
- No model, server, GPU, benchmark, remote, or deployment command was run.

## Followups

- A tester/runtime owner can build the AOT kernels with `-DSGL_KERNEL_MINIMAL_SM86=ON`
  and exercise the Qwen3.5-4B W4A16 load path under the authorized 3060 environment.

## Open issues and runtime risks

- This change has source-list/static evidence only; CUDA compilation and runtime symbol
  coverage remain unverified locally because CMake/CUDA/model execution were out of scope
  or unavailable.
- The exclusion assumes the target Qwen3.5-4B checkpoint uses the dense W4A16 hybrid path
  described in the dispatch. A checkpoint or runtime configuration that selects MLA, MoE,
  or sparse vertical/slash attention would require a different source set.
- The option filters the common `SOURCES` list only. FA3 and FlashMLA option semantics
  remain unchanged, but their independent runtime compatibility on SM86 remains a separate
  environment/runtime question.

Extra work requires a new Task ID.
