# Gemma4 QUASAR GGUF integration findings

## Source/reference
- Model path and SHA256 remain fixed in `tasks/T001-locate-and-qualify.md`.
- Independent llama.cpp `/completion` reference: `/data/sglang-hicache/g2-quasar-runs/reference/completion.json`; generated IDs `[236800,236778,236800,106]`, per-step Top-10 logprobs (not raw logits).
- New current-source SM86 build: `/data/sglang-hicache/g2-quasar-runs/aot-sm86-build/sm86/common_ops.cpython-312-x86_64-linux-gnu.so`, SHA256 `eabac59d3195b144e6a2d937029fc24ea71fb6bc410ccf61f278659ddb88d4e4`, built with Torch 2.13.0+cu129, CUDA 12.9, Python 3.12, current `SGL_KERNEL_MINIMAL_SM86` CMake target. Imported successfully alongside copied current AOT Python API in `/data/sglang-hicache/g2-quasar-runs/aot-sm86-package/`.

## GGUF inventory/config
- 42 blocks: indices 0–23 contain SWA/full attention per metadata pattern, indices 24–41 are shared-KV layers. `shared_kv_layers=18`.
- SWA head dim 256, full/global head dim 512; both tensor shapes imply two KV heads. PLE token embedding is Q6_K `[262144,10752]`; PLE projection is F16; final output norm is F32; transformer matrices Q4_0. `layer_scalar` is one element.
- Added `Gemma4GGUFTextConfig.from_gguf` and `gemma4` native builder. It constructs a valid 42-layer Transformers TextConfig.
- Added an authored name map/coverage validator in `gemma4_gguf.py`. The map covers all source tensors except `rope_freqs.weight` (explicit archive-only omission), excludes K/V and K/V norm parameters for shared layers; smoke validation currently passes 665 model tensor mappings. This is not yet proof each parameter is correctly consumed by SGLang loader.
- Current dirty Gemma4 changes replace both token and PLE tables with `VocabParallelEmbedding(quant_config=GGUF)`, retain their independent `sqrt(hidden_size)` and `sqrt(256)` scales, and restore scales after selected-row lookup. This is source-consistent but still lacks a final model-load/consumption audit.
- The current Qwen tied alias is not a verified GGUF Q6_K output path: `GGUFEmbeddingMethod` only overrides `embedding`, while logits dispatch calls quant-method `apply`; validate weight layout/API before treating it as supported. See `tied-gguf-output-decision.md`.

## Remaining verification
- Exercise current `GGUFModelLoader` and Gemma4 registry with the isolated SM86 package; fail closed on every required source tensor and runtime parameter. The default venv currently cannot import the full runtime because `sgl_kernel.fp8_scaled_mm` is absent; this is an environment/package issue to resolve without abandoning the loader audit.
- Validate embedding lookup against gguf-py CPU dequantization, preserving separate token/PLE scales. Resolve the tied Q6_K output contract using an already-supported SGLang path; do not invent a dequant/GEMM algorithm.
- Only after model load and output path are proven, acquire `/tmp/f1-r16b-gpu-exclusive.lock`, run real BF16-KV request, compare logits/Top-K and autoregressive IDs against llama.cpp. No FP8/capacity test before this gate passes.
