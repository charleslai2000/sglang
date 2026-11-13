# Layer5 Q4_0 same-input diagnostic — 2026-11-08

## Scope and identity

- Frozen model: `/data/models/gemma4-quasar-q4_0/gemma-4-E4B-it-QUASAR-Q4_0.gguf`, SHA-256 `7d6269096c9acbce4422fd1aa3a249436b01288868961e48ca9bb2541997f669`.
- Frozen doc24: 1,104 tokens, prompt-ID SHA-256 `226c3a0ab3dfe6329fb1a9d198ee342ceef3422b0f60acb09352b438ae0a1235`, selected Layer5 position 1103.
- A8 capture UUID `a149298aed9d489597b8ffb6ca34ca61`; full-Q4_0-FP32 opt-in service UUID `f1fcb176bfef46539bc32f5bdec4446f`.
- Both completed BF16 EXTEND service captures. These are separate full-model trajectories; cross-capture boundary deltas alone do not attribute causality to Layer5.

## Opt-in path

`SGLANG_GGUF_Q4_0_FP32_DEQUANT_GEMM=1` selects FP32 dequant + FP32 GEMM (TF32 disabled) for Q4_0 `GGUFLinearMethod` linear layers, then casts to the input activation dtype. It is off by default. MoE and embeddings do not use this path. This is diagnostic only; no production fix established.

## Same-input findings

- Q/K/V: production `ggml_mul_mat_vec_a8` reproduces service captures (K/V exact; Q rel-L2 `7.67e-7`). On the identical frozen Layer5 activation, A8 vs FP32 GEMM rel-L2 is Q `0.01038`, K `0.01217`, V `0.01362`; cosine is approximately 0.9999. This establishes a quantized-accumulation path difference, not an implementation defect.
- o_proj: directly evaluate both kernels on the exact FP32-service captured BF16 o_proj input (SHA-256 `4031e7b946e0d1269b0232299f0670ff97dce661405ebbe04266f84d473c1b3c`). FP32 output exactly matches the live service capture; A8 differs from live/FP32 rel-L2 `0.0053873`, max abs `0.04296875`, cosine `0.9999856`. Thus the direct production projection and FP32 projection are numerically distinct on the same input.
- Raw final logits from the two separate full service runs: rel-L2 `0.08822`, RMSE `0.63405`, max abs `2.4571`, cosine `0.99714`. Both greedy token IDs are `107`; top-10 order differs at low ranks, top-1 margins `0.3490` (A8) and `0.7737` (FP32). This is not a controlled single-projection intervention and does not show quality recovery.
- Cross-run Layer5 comparisons showed the FFN and PLE boundaries also differ, as expected when the upstream full-model trajectories differ. They are not localized causes. An attempted FFN direct kernel comparison was invalid because packed expert tensor orientation / fused MoE semantics do not match ordinary GEMV; its failed output is discarded.

## Decision

No causal production defect or quality repair is established. Keep quality NO-GO and E5M2 NOT ACCEPTED. Do not promote this diagnostic path into production or infer the cause from the cross-run logit delta. Next useful work is a controlled single-projection intervention on a matched forward state, followed by RoPE/attention/PLE same-input checks if projection changes do not explain the anomaly. No FP8, capacity, performance, or E5M2 work was performed.

## Layer0 attention / MoE follow-up — 2026-11-09

- Frozen GGUF/config check shows doc24 Layer5 does not use MoE: native config has `enable_moe_block=False`; the GGUF has no router/expert tensors. This is a dense FFN; routing/top-k/expert-scale/`ggml_moe_a8` cannot explain this case.
- Layer5 PLE replay using the original GGUF weights is elementwise exact against the service capture when the true residual is reconstructed as `block_input + post_attention_normed`. This excludes a Layer5 PLE arithmetic mismatch at the captured position.
- Existing A8 vs FP32 doc24 captures diverge at Layer0. To identify whether the attention output difference propagates, we replaced only position 1103 Layer0 attention output with the exact captured output from the other service run while keeping A8 Layer0 Q/K/V and all earlier-layer activations fixed. The replacement payload was exactly equal to the FP32 capture. Downstream A8 stages moved toward the FP32-run values: `post_attention_normed` rel-L2 0.01024→0.00509, `ffn_input` 0.01772→0.00888, `ffn_output` 0.01750→0.00939, `post_ple` 0.01053→0.00676, `layer_output` 0.01064→0.00683. None became BF16-equal; this is one position, and it does not establish task-quality causality.
- A reverse-direction run (A8 service with FP32 Layer0 attention-output replacement) reproduced the same A8 upstream and downstream values as the A8-upstream intervention arm. It confirmed the exact replacement is applied, but is not an independent replica because the injection is identical.
- Captured actual Layer0 production attention inputs from both service arms at doc24 position 1103 (same 1,104 prompt IDs, same causal SWA window of 512 keys, no prefix KV, custom mask, score_mod, or logit cap). The production A8-vs-FP32 attention outputs differ rel-L2 0.01485 / max abs 0.046875. Captured Q/K/V also differ (rel-L2 Q 0.01267, K 0.00928, V 0.01347); this is an upstream activation-path difference, not evidence of a mask defect.
- CPU FP32 attention replay on each arm's captured Q/K/V and exact causal-SWA mask matches the corresponding production output closely (A8 rel-L2 5.95e-4; FP32 rel-L2 7.77e-4; both max abs 0.0078125). Cross-swapping Q vs K/V shows the attention output delta mainly follows Q/K/V: replacing A8 K/V with FP32 K/V while retaining A8 Q moves the reference output closer to FP32 production (rel-L2 0.00330); replacing only Q with FP32 while retaining A8 K/V remains about 0.01442 away. This replay is an FP32 semantic reference, not bitwise production replay; it does not identify whether the upstream Q/K/V differences originate in projection accumulation or earlier activation trajectory.
- An attempted production Triton offline replay could not compile because the shared dirty `extend_attention.py` references undefined `BF16_KV_COMPUTE` in its kernel body. Do not silently repair or overwrite this shared change without ownership clarification; the real services still executed successfully via their separate configured runtime path. LSP diagnostics are not reliable here (missing `torch`/`triton` imports plus existing type errors); Python `py_compile` and `git diff --check` passed.
- Artifacts: `/data/sglang-hicache/g2-quasar-runs/20261107T-g2-first-logits/layer0-attn-qkv-cross-cpu-replay.json`, `layer0-attn-fp32-reference.json`, `layer0-attn-intervention-vs-fp32-doc24.json`, `layer0-attn-reverse-intervention-vs-fp32.json`.

## Verification and resource state

The two real BF16 service runs completed; the diagnostic matrix experiment executed under `/tmp/f1-r16b-gpu-exclusive.lock`. GPU was verified idle afterward (1 MiB, 0%). No frozen 14-prompt rerun, quality acceptance, commit, or push occurred.
