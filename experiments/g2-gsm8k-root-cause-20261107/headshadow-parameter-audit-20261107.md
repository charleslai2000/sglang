# HEAD-shadow parameter and execution-path audit (2026-11-07)

## Verified

- GGUF SHA-256 `7d6269096c9acbce4422fd1aa3a249436b01288868961e48ca9bb2541997f669`; 42 blocks, hidden 2560, vocab 262144, tied embedding/output, shared KV 18 suffix layers, PLE width 256, final-logit soft-cap **30.0**.
- SGLang loaded this GGUF with BF16 compute/KV, TP1, eager Triton attention; its native GGUF config builder reconstructs layer types/head dimensions/RoPE/PLE shapes and final soft-cap. llama.cpp reads the same soft-cap and computes `30*tanh(logits/30)`; SGLang also applies it before sampling. Earlier API evidence showed full-vocabulary normalized log probabilities before greedy selection, complete token-ID alignment, and rank-1 agreeing with each engine's output token.
- GGUF layer 5 tensors are dense Q4_0 `ffn_gate/up/down`, plus PLE `inp_gate`, `proj`, `post_norm`; there is no layer-5 router or expert-routing tensor. The native GGUF config builder does not set `enable_moe_block`; the instantiated SGLang model configuration still needs direct runtime inspection before treating this as end-to-end confirmation.
- Three-prompt paired layer capture is complete for 42 layers at the final prompt-token row: SGLang EXTEND captures, plus llama.cpp callback captures from pinned CPU revision `b49650adb31f2e49a0d76113aeb1792134fd8413`. The exporter was verified repeatable, with row order derived from GGML tensor byte strides. Current cross-engine comparisons show layers 0–4 cosine ≥0.99987 and layer 5 relative L2 `.149–.207`. The llama-side last-layer outputs are not validated against logits/head reconstruction, and runtime configs/weights/upstream input identity are not yet identical. Treat this as an earliest observed divergence candidate, not proof of a faulty implementation; use the metrics only for exploratory localization until these controls pass.
- No production fix is established. No source edits were made for this diagnosis; the tree already contains extensive unrelated dirty/untracked work and those changes were preserved.

## Still open / next decisive work

- Validate llama.cpp final-layer/head reconstruction and logits against `llama_get_logits_ith` for the same prompt. The temporary exporter is `/tmp/g2_llama_layers.cpp`, binary `/tmp/g2-llama-layers`; its final-layer capture has not passed this check.
- Then pair the same token IDs with SGLang's exact PLE and block boundaries, verify runtime instantiated config and loaded GGUF weights, and compare layer-5 sub-operations with identical inputs/weights. Do not infer a defect from cross-kernel Q4 differences alone.
- Exact runtime RoPE frequencies/masks and loaded tensor identity remain unverified. Historical private attention-overlay results remain a separate provenance branch.

## Artifacts

- Run root `/data/sglang-hicache/g2-quasar-runs/20261107T-g2-first-logits/layers/`.
- SGLang request output `headshadow-layers-3.jsonl`, SHA-256 `9b146013e384f45fdf8db3cf3794e4cb1a32c87608075c331f20212c147e86eb`.
- `layer-comparison-terminal-3.json` is exploratory localization only; no production defect claim rests on it.
