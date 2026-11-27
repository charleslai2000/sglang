# T012 — Humming W4A16 GEMM optimization

## Goal
Evaluate whether upstream SGLang Humming W4A16 can replace Marlin for the unchanged Gemma4 checkpoint and deliver a stable net benefit on the original C-8 L1-only workload, while preserving checkpoint quantized values/scales, BF16 activations, FP32 accumulation, model correctness, KV capacity, and workload/configuration. Only equivalent weight-layout conversion is allowed; never requantize or retain duplicate resident weights.

## Scope
- Use upstream `HummingLinearMethod` and exact Gemma4 checkpoint for full-model loading; do not build a mixed-GEMM scheduler or add kernels/telemetry.
- Verify real fused projections, normal and Double-wide MLP projections, full-model logits/greedy tokens, and CUDA Graph replay against existing correctness criteria.
- Run original C-8 L1-only Marlin/Humming A/B with FA2 disabled, measuring Extend, Decode, TPS, memory cost and identical workload. Override only cache enablement and quantization method relative to the frozen baseline argv; explicitly retain `--attention-backend triton` and no prefill graph. Preserve the prior T011 production decision.
- Keep Humming only if stable net benefit is demonstrated without correctness or capacity regressions; otherwise revert. Verify three-tier cache only if Humming clears those conditions.
- Finish by cleaning and committing/pushing only responsible T012 files; preserve unrelated work.

## Constraints
- No new kernels; no Attention, HiCache, KV capacity, scheduling, Marlin or other algorithms changes. No W4A8 or alternate quantization.
- No re-quantization. Checkpoint weights/scales are authoritative; only exact representation/layout conversion allowed.
- GPU workloads acquire `/tmp/f1-r16b-gpu-exclusive.lock`, are bounded, use durable artifacts, and clean up all owned processes/resources.
- Commit/push only T012-scoped artifacts or justified upstream-compatible integration. Preserve unrelated dirty/untracked files.

## Completion
Reach a valid conclusion from full-model correctness and original C-8 L1-only A/B (and three-tier verification only when warranted). Retain a scoped implementation only on demonstrated stable net benefit; otherwise restore production. Record source identities, correctness, Extend/Decode/TPS/memory, capacity and cleanup, and update Plan/Task/Frontier.

## Opt-in Humming post-load route (landed; gate PASS)
Result: `runs/T012-CTLOADER-HUMMING-QUALIFICATION.md`. All 253 Text Core WNA16 layers carry byte-identical packed INT4 words and BF16 scales in the Marlin and Humming arms, the conversion is exact to bf16 kernel precision, Humming runs every forward and inside the replayed decode graph, and greedy agreement holds except at a position where the model's own prefill and decode paths disagree. Performance and conditional tier validation are the remaining gates.
Preserve CompressedTensorsWNA16.create_weights and Gemma4.load_weights unchanged. At `process_weights_after_loading`, before Marlin repack, support an independent explicit opt-in Humming path that converts the already-loaded CT `weight_packed` and group scales using upstream Humming post-load preparation. Marlin remains default. The branch must fail closed if any required CT packed weights/scales are absent and must verify fused QKV and Gate/Up shard contents; no model-structure changes, new kernels, requantization, or duplicate resident weight copies.
