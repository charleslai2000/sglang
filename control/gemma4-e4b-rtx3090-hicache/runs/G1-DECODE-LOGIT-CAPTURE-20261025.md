# E5M2 Decode Logit Capture — 2026-10-25

## Scope and method

Opt-in capture at `ModelRunner.forward` return, before sampling. It records full next-token logits plus request RID, append-only decode step, position, input token ID, KV length, slot, model identity, KV dtype/pool capacities and actual graph-replay flag. It refuses active CUDA stream capture and incomplete/unaligned host metadata. Normal operation is unchanged unless `SGLANG_GEMMA4_CAPTURE_DECODE_LOGITS=1`.

## RTX 3090 evidence

Pinned checkpoint revision `6cd26aaa2357fb2bad8c51699a7558a4d1a965bb`, SHA-256 `19d89d2a4b3e401a3eae75ec08ab112810421a036c91d8c8226b686be7fe0c5d`; E5M2 KV.

- Identical 32-token prompt, 24 Decode steps: Eager and actual bs=1 CUDA Graph replay match RID/history, positions 32–55 and all full `[1,262144]` logits exactly. Per-row max/mean/relative-L2 errors are zero; selected tokens match. `/data/sglang-hicache/gemma4/runs/20261025T045416Z-g1-graph-replay/decode-capture-retest/decode-eager-graph-parity.json`.
- Frozen 514-token prompt, 16 Decode steps from positions 514–529 across the 512-token SWA boundary: Eager and actual Graph replay match complete logits and selected tokens exactly. `/data/sglang-hicache/gemma4/runs/20261025T045416Z-g1-graph-replay/swa-boundary-decode/eager-graph-summary.json`.

These are Eager/Graph execution parity observations, not E5M2-vs-BF16 or HF correctness acceptance. Prior E5M2-vs-BF16 boundary rows include N=513 greedy disagreement and N=514 top-10 disagreement; no acceptance tolerance was changed.

## Verification and delivery

- `test_gemma4_decode_logit_capture.py` plus existing `test_hidden_state_graph_recapture.py`: 10 passed, 14 subtests passed.
- Python compilation and `git diff --check` passed.
- This change is opt-in and does not alter model math. Full G1 remains ACTIVE / NOT ACCEPTED pending FP8 quality and broader acceptance.
