# Full-vocabulary first-step distribution analysis (fixed 14)

Inputs are the complete 262,144-token SGLang `output_top_logprobs` rows and llama.cpp `top_logprobs` rows in `/data/sglang-hicache/g2-quasar-runs/20261107T-g2-first-logits/`. Each SGLang response's prompt-ID hash and echoed token count match the frozen prompt; it has 262,144 first-generated-position `output_top_logprobs`. llama.cpp has 262,144 `top_logprobs` for the same prompt. Vocab IDs were independently verified identical. Both APIs return normalized log probabilities (log-softmax), not raw logits; the first output token matches each runtime's greedy choice, with sampling filters/penalties neutral. Hence this is the pre-choice distribution and not a sampling-after-effect comparison, but it cannot establish raw-logit equality because normalization constants are discarded.

Analysis script: `diagnostic-distributions-headshadow-20261107.py`. Per-prompt JSON: `/data/sglang-hicache/g2-quasar-runs/20261107T-g2-first-logits/distribution-comparison-14.json`, SHA-256 `cd360168ee979696c6d3e5fa9225c0ac6bd2268702333a4f5cf97d6c3eeb27e1`.

## Summary

- Greedy top-1 agrees on 5/14; differs on 9/14. All margins are positive; no tie explains a disagreement.
- Mean top1−top2 log-prob margin: SGLang **1.1063 nats**, llama.cpp **1.3064 nats**.
- Mean cross entropy H(P_SGLang,Q_llama) **3.9232 nats**; reverse H(P_llama,Q_SGLang) **3.0993 nats**.
- Mean KL(P_SGLang||P_llama) **2.3694 nats**, reverse KL **1.8242 nats**.
- Mean Jensen–Shannon divergence **0.28401 nats** (range 0.00954–0.57498); mean overlap coefficient `sum(min(p,q))` **0.4132**.

**Critical alignment detail:** each API returns values ordered by its own probability rank. The analysis script joins records by token ID and asserts complete, unique ID-set equality before calculating cross-entropy, KL, JS, or overlap. A prior position-wise calculation was invalid and its estimates are discarded.

This establishes substantial heterogeneous first-position distribution disagreement, not its cause or a specific offending operator. Since 9/14 argmax IDs already differ before generated Decode tokens, teacher-forced Decode/KV is not the next priority. Continue investigating current HEAD-shadow Prefill/model computation, and keep historical private-overlay evidence separate.
