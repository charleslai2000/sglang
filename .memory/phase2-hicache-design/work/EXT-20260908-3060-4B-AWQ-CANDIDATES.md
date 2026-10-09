# EXT-20260908-3060-4B-AWQ-CANDIDATES

Task ID: `D3060-CKPT-002`  
Orchestration epoch: `20260908-3060`  
Role: `external-researcher`  
Status: `done`  
Survey date: `2026-09-08` (Asia/Shanghai)

## Recommendation

**Primary:** [`LostGentoo/Qwen3.5-4B-AWQ`](https://huggingface.co/LostGentoo/Qwen3.5-4B-AWQ)

Why: it is the best public fit for the stated AWQ INT4/Marlin preference. Its model card explicitly declares AWQ W4A16, symmetric `group_size=128`, `compressed-tensors` packing, and native vLLM Marlin loading. The card also reports a BF16-vs-AWQ quality comparison and vLLM verification on an SM120 RTX 5060 Ti. The checkpoint is larger than the other candidates, but the public repository inventory is about 5.31 GB, which is still materially below the 12-GB RTX 3060 capacity before runtime/KV allocations.

**Fallback:** [`cyankiwi/Qwen3.5-4B-AWQ-4bit`](https://huggingface.co/cyankiwi/Qwen3.5-4B-AWQ-4bit)

Why: it is a smaller, full-VLM checkpoint with explicit SGLang launch instructions and a directly inspectable `compressed-tensors` `pack-quantized` config. Its AWQ recipe is symmetric INT4 with `group_size=32`, and it leaves the vision tower, GDN/linear-attention projections, MTP, embeddings, and `lm_head` outside the quantized target set. That mixed-precision shape may be a safer correctness fallback for the hybrid Qwen3.5 path, but the public card does not report a Marlin or SM86 run, and it has no public BF16 comparison in the inspected material.

**Size-first alternative, not selected as primary/fallback:** [`kumar2235/Qwen3.5-4B-AWQ`](https://huggingface.co/kumar2235/Qwen3.5-4B-AWQ). It reports AWQ W4A16 asymmetric, `group_size=128`, zero-points, `compressed-tensors`, and about 3.13 GB. Current SGLang source says compressed-tensors WNA16 handles both symmetric and asymmetric linear weights through the Marlin path, but the public candidate evidence does not show a Marlin run or an SM86 run, and the card itself says the reported scores have not been compared against BF16 under an identical harness.

The words “primary” and “fallback” above are **experiment ordering recommendations**, not verified target-host compatibility results.

## Candidate comparison

| Candidate | Quant method / packing | Group size and zero point | Public backend claim | Public file-size evidence | SGLang evidence | SM86/Marlin confidence |
|---|---|---|---|---|---|---|
| `LostGentoo/Qwen3.5-4B-AWQ` | AWQ INT4/W4A16; `llm-compressor`; `compressed-tensors`; 248 LM linear layers quantized. Vision tower, merger, embeddings, norms, tied head, and MTP remain BF16. | `g128`, symmetric. | Model card explicitly says `compressed-tensors` for native vLLM loading with Marlin kernels; it reports Marlin W4A16 working on SM120. | HF tree: 5.31 GB repo; main `model.safetensors` 5.05 GB plus `model_mtp.safetensors` 241 MB. Card rounds on-disk model size to ~5.0 GB. | HF card has an SGLang launch snippet using `--model-path` and no explicit quantization flag. This is a card/launcher claim, not a target-host run. | **Best candidate-level Marlin evidence**, but only SM120/vLLM was reported. SGLang/SM86 remains unverified. |
| `cyankiwi/Qwen3.5-4B-AWQ-4bit` | AWQModifier; INT4 `pack-quantized`; `quant_method=compressed-tensors`; the recipe ignores visual layers, `linear_attn`, MTP, embeddings, and `lm_head`. | `g32`, symmetric, static, group strategy. | Card provides SGLang and vLLM commands but does not explicitly claim Marlin. Current SGLang source maps `pack-quantized` WNA16 linear schemes to the Marlin path. | HF tree: 4.06 GB repo; main model safetensors 4.04 GB. | HF card has an SGLang launch snippet using `--model-path` and no explicit quantization flag. | **Good format-level fit, weak empirical evidence.** `g32` and hybrid ignored-layer behavior require the target-host test. |
| `kumar2235/Qwen3.5-4B-AWQ` | AWQ INT4/W4A16 asymmetric; `llm-compressor`; `compressed-tensors`; 512 OpenPlatypus calibration samples. | `g128`, asymmetric, zero point enabled. | No candidate-specific Marlin claim found. Current SGLang source says compressed-tensors WNA16 handles symmetric and asymmetric linear weights through Marlin. | Card reports ~3.13 GB on disk and ~3.06 GB at load; no independent file-tree total was used here. | HF card has an SGLang launch snippet using `--model-path`; it is not a reported SM86 run. | **Potentially attractive on 12 GB, but higher format/ASYM uncertainty** than the symmetric primary. |
| `ikantkode/Qwen3.5-4B-AWQ-vd` | Independently re-quantized AWQ INT4; full INT4 attention + GDN + MLP; alternating-least-squares scale/zero fitting; companion vLLM tuning work. | `g128`, asymmetric zero point. | Public evidence is vLLM on AMD `gfx1030`/Radeon V620; no SGLang command or Marlin claim found. | HF tree: 4.06 GB repo; `model.safetensors` 3.8 GB plus 241 MB MTP. | No direct SGLang evidence found. | **Poor fit for this task** despite promising size/quality claims, because the evidence is AMD/vLLM-specific and uses companion kernel patches. |
| `QuantTrio/Qwen3.5-4B-AWQ` | Public page is tagged AWQ/4-bit and has SGLang/vLLM launch snippets. The inspected card did not expose a reliable group-size or detailed backend claim. | Not established from inspected public material. | No direct Marlin claim found. | HF tree reports 6.09 GB, with three model shards. | SGLang snippet is present, but no target-host result. | **Low evidence density** for this SM86 experiment; not selected. |

## Evidence details

### Official correctness reference

The official [`Qwen/Qwen3.5-4B` model card](https://huggingface.co/Qwen/Qwen3.5-4B) describes a 4B causal language model with a vision encoder, 32 layers, interleaved Gated DeltaNet linear attention and full attention, and a native 262,144-token context. It says Qwen3.5 requires SGLang from the repository main branch and provides a standard SGLang launch example. The same public card says the artifacts are compatible with Transformers, vLLM, SGLang, and KTransformers.

This is the correctness/reference checkpoint, not an INT4 candidate. The official card's SGLang command establishes public framework support for the base model path, but does not establish AWQ checkpoint support on the target GPU.

SGLang's public test utility also lists `Qwen/Qwen3.5-4B` as its default small Gated-DeltaNet hybrid model. That is evidence that the base architecture is in the public SGLang test inventory; it is not evidence that any of the AWQ candidates passed the same tests.

### SGLang quantization and KV-cache evidence

The current [SGLang quantization documentation](https://docs.sglang.ai/advanced_features/quantization.html) states:

- Pre-quantized AWQ/GPTQ checkpoints should be loaded from their config; do not add a redundant `--quantization` flag for an offline-quantized model.
- `compressed-tensors` is supported on NVIDIA GPUs.
- `awq_marlin` is supported on NVIDIA GPUs; Marlin is CUDA-only.
- SGLang's current source for [`compressed_tensors.py`](https://github.com/sgl-project/sglang/blob/main/python/sglang/srt/layers/quantization/compressed_tensors/compressed_tensors.py) says both symmetric and asymmetric static WNA16 linear weights are handled by `CompressedTensorsWNA16` through the Marlin path. For `pack-quantized` WNA16 it constructs the corresponding scheme and passes the configured group size through.
- The same source explicitly restricts its **Triton WNA16 MoE** path to symmetric INT4 group quantization with `group_size=32` or `128` and no act-order. That restriction is for the MoE path; it should not be silently generalized to the dense linear path, but it is a reason to inspect runtime backend logs.

SGLang's [quantized KV-cache documentation](https://docs.sglang.ai/advanced_features/quantized_kv_cache) states that FP8 KV cache can be enabled with `--kv-cache-dtype fp8_e4m3` or `--kv-cache-dtype fp8_e5m2`. It warns that the attention backend must support fused quantized-KV handling and that missing FP8 KV scaling factors default to `1.0`, which may affect accuracy. No inspected Qwen3.5-4B AWQ card supplied target-specific FP8-KV validation on SM86. Therefore FP8 KV is a requested experiment setting, not a verified property of either candidate.

### Marlin and SM86 evidence

NVIDIA's [CUDA GPU Compute Capability table](https://developer.nvidia.com/cuda/gpus) lists GeForce RTX 3060 under compute capability 8.6. The [current vLLM quantization compatibility documentation](https://github.com/vllm-project/vllm/blob/main/docs/features/quantization/README.md) marks AWQ and Marlin (GPTQ/AWQ/FP8/FP4) as supported on Ampere and defines Ampere there as SM8.0/SM8.6.

This establishes a strong **framework-level** reason to try W4A16 Marlin on an RTX 3060. It does not prove that SGLang's build, CUDA wheel, exact model dimensions, selected attention backend, or the candidate's mixed-precision ignore list will work on SM86. The vLLM statement is not a SGLang guarantee.

The primary candidate's card reports Marlin on SM120, not SM86. The fallback card does not report a Marlin run. No public source found in this survey reports an end-to-end SGLang run of either exact Qwen3.5-4B candidate on an RTX 3060.

### Relevant negative evidence

The public SGLang issue [#19406](https://github.com/sgl-project/sglang/issues/19406), opened 2026-02-26, reports Qwen3.5-27B AWQ/INT8 failures on current `main`: an automatic Marlin repack failed for dimensions not divisible by Marlin's tile size, and forcing Triton AWQ then exposed a hybrid-cache dtype mismatch. This is **not** proof that Qwen3.5-4B fails; the model size and tensor shapes differ. It is evidence that Qwen3.5 hybrid quantized paths need shape- and dtype-specific validation.

The public SGLang issue [#22287](https://github.com/sgl-project/sglang/issues/22287), opened 2026-04-07, reports a different Qwen3.5 compressed-tensors NVFP4 failure where ignored GDN layers were mishandled and produced garbage output. That issue concerns NVFP4 and larger MoE checkpoints, not these W4A16 candidates. It is still relevant as a warning against assuming that a model-card “compatible” label proves hybrid-layer correctness.

## Why the primary/fallback ordering is conservative

1. The primary is the only inspected candidate with an explicit, candidate-specific Marlin claim and symmetric `g128`, a conventional W4A16 Marlin shape, plus a public BF16 comparison.
2. The fallback is smaller and preserves more of the hybrid architecture in BF16. Its public `config.json` and recipe are unusually transparent, and the current SGLang source recognizes the same `compressed-tensors`/`pack-quantized` family. Its `g32` path is less empirically established on SM86, so it is a fallback rather than the primary.
3. The Kumar candidate is attractive if the experiment is memory-bound, but it is asymmetric and its evidence is primarily a model-card recipe plus generic SGLang launcher text. Use it only after the primary/fallback or when the target host cannot reserve enough memory for the 5.31-GB primary.

## Required target-host validation

These are open validation requirements, not claims that were executed by this public-only research task:

- Pin and record the exact SGLang commit/container, CUDA version, PyTorch version, GPU model, and driver. Use a current SGLang build because the official Qwen card calls for main-branch support and older public issues show quantized hybrid regressions.
- First run the official BF16 `Qwen/Qwen3.5-4B` smoke reference with a deliberately small context and the same tokenizer/chat-template path intended for INT4. Record readiness, one greedy text output, one short reasoning output, and memory.
- For each candidate, load the checkpoint without a redundant online `--quantization` override, then confirm from logs that the config is parsed as compressed-tensors W4A16 and that the intended Marlin/WNA16 path is selected. A server that merely starts is insufficient; compare deterministic output to the BF16 reference.
- Verify the candidate's actual `config.json` on the target host: `quant_method`, `format`, bit width, group size, symmetric/asymmetric flag, zero-point presence, ignored modules, and tensor-name layout. This is especially important for Kumar's asymmetric format and for the hybrid-layer ignores in cyankiwi.
- Test `--kv-cache-dtype fp8_e4m3` and/or `fp8_e5m2` only after a BF16-KV control works. Confirm the attention backend supports quantized KV, record whether scales are loaded or supplied, and compare short-context outputs. Do not treat a default scale of `1.0` as validated accuracy.
- Exercise both batch-1 decode and a small batched decode, because Marlin's value is most relevant to W4A16 inference and shape/backend selection can differ between load, eager execution, and CUDA-graph capture.
- If the Marlin path fails, preserve the exact error and backend log. Do not silently relabel a Triton/AWQ or dequantized run as a successful Marlin result. Any fallback backend choice needs its own target-host evidence.

## Open issues

- No exact end-to-end SGLang + Qwen3.5-4B-AWQ + RTX3060/SM86 public result was found.
- No public source proves that the primary's SM120 Marlin result transfers to SGLang on SM86.
- No public source proves that FP8 KV cache is accurate and performant for this hybrid Qwen3.5-4B workload on SM86; attention-backend and scaling-factor behavior remain open.
- Candidate cards and HF “How to use with SGLang” blocks are documentation claims, not independent verification. The report deliberately separates them from SGLang source/docs and from framework-level Ampere support tables.
- The exact current SGLang behavior for the primary's quantized GDN/linear-attention projections and for the fallback's ignored GDN projections must be checked on the pinned target build.

## Direct public sources

All links below were public and accessed on 2026-09-08; no weights were downloaded.

- [Qwen/Qwen3.5-4B official model card](https://huggingface.co/Qwen/Qwen3.5-4B) — official architecture, BF16/reference usage, and SGLang main-branch guidance.
- [SGLang quantization documentation](https://docs.sglang.ai/advanced_features/quantization.html) — offline checkpoint loading, compressed-tensors, AWQ/Marlin platform table.
- [SGLang quantized KV-cache documentation](https://docs.sglang.ai/advanced_features/quantized_kv_cache) — FP8 KV flags, scaling-factor behavior, and backend warning.
- [SGLang compressed-tensors implementation](https://github.com/sgl-project/sglang/blob/main/python/sglang/srt/layers/quantization/compressed_tensors/compressed_tensors.py) — current public WNA16/Marlin scheme selection.
- [SGLang public test utilities](https://github.com/sgl-project/sglang/blob/main/python/sglang/test/test_utils.py) — Qwen3.5-4B appears as the small GDN-hybrid test model.
- [vLLM quantization compatibility](https://github.com/vllm-project/vllm/blob/main/docs/features/quantization/README.md) — Ampere/SM8.0/SM8.6 AWQ and Marlin support table; framework-level evidence only.
- [NVIDIA CUDA GPU Compute Capability](https://developer.nvidia.com/cuda/gpus) — RTX 3060 listed at compute capability 8.6.
- [LostGentoo/Qwen3.5-4B-AWQ](https://huggingface.co/LostGentoo/Qwen3.5-4B-AWQ) — primary candidate card, W4A16/g128/symmetric/Marlin claim, quality evidence, and SGLang snippet.
- [LostGentoo checkpoint file tree](https://huggingface.co/LostGentoo/Qwen3.5-4B-AWQ/tree/main) — public repository size and file sizes.
- [cyankiwi/Qwen3.5-4B-AWQ-4bit](https://huggingface.co/cyankiwi/Qwen3.5-4B-AWQ-4bit) — fallback card and SGLang snippet.
- [cyankiwi `config.json`](https://huggingface.co/cyankiwi/Qwen3.5-4B-AWQ-4bit/blob/main/config.json) — public `compressed-tensors`, `pack-quantized`, INT4, `group_size=32`, and ignore list.
- [cyankiwi `recipe.yaml`](https://huggingface.co/cyankiwi/Qwen3.5-4B-AWQ-4bit/blob/main/recipe.yaml) — public AWQModifier recipe and group size.
- [cyankiwi checkpoint file tree](https://huggingface.co/cyankiwi/Qwen3.5-4B-AWQ-4bit/tree/main) — public repository and main weight sizes.
- [kumar2235/Qwen3.5-4B-AWQ](https://huggingface.co/kumar2235/Qwen3.5-4B-AWQ) — size-first alternative, W4A16 asymmetric/g128 recipe, limitations, and SGLang snippet.
- [ikantkode/Qwen3.5-4B-AWQ-vd](https://huggingface.co/ikantkode/Qwen3.5-4B-AWQ-vd) — AMD/vLLM-focused alternative, ALS recipe, sizes, and measured claims.
- [QuantTrio/Qwen3.5-4B-AWQ](https://huggingface.co/QuantTrio/Qwen3.5-4B-AWQ) — larger public AWQ alternative with generic SGLang/vLLM snippets.
- [SGLang issue #19406](https://github.com/sgl-project/sglang/issues/19406) — dated Qwen3.5-27B AWQ/INT8 Marlin shape and hybrid dtype failure report; related warning, not direct 4B proof.
- [SGLang issue #22287](https://github.com/sgl-project/sglang/issues/22287) — dated Qwen3.5 compressed-tensors hybrid-layer correctness report for NVFP4; related warning, not direct W4A16 proof.

## Invocation handoff

- `status`: `done`
- `artifacts`: this report at `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/EXT-20260908-3060-4B-AWQ-CANDIDATES.md`
- `evidence`: direct public URLs and candidate/config/source distinctions are recorded above.
- `summary`: primary `LostGentoo/Qwen3.5-4B-AWQ`; fallback `cyankiwi/Qwen3.5-4B-AWQ-4bit`; Kumar retained as a size-first alternative.
- `followups`: target-host validation of SGLang Marlin selection, SM86 load/generation, FP8 KV cache, and BF16-vs-INT4 correctness.
- `open_issues`: listed above; no private hosts, credentials, repositories, logs, or weights were accessed.
- Extra work requires a new Task ID.
