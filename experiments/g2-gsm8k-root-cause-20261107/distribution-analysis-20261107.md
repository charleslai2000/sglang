# Full-vocabulary first-step distribution analysis (fixed 14)

Inputs are the complete 262,144-token SGLang `output_top_logprobs` rows and llama.cpp `top_logprobs` rows in `/data/sglang-hicache/g2-quasar-runs/20261107T-g2-first-logits/`. Vocab IDs were previously verified identical. Both records are normalized log probabilities (log-softmax outputs), not raw logits; greedy top-1 is the selected max after neutral sampling processors. Each top token agrees with its runtime's generated first token. This comparison is not confounded by a sampler changing top-1, but normalization constants mean it cannot establish equality of raw logits.

Analysis script: `diagnostic-distributions-headshadow-20261107.py`. JSON per-prompt metrics: `/data/sglang-hicache/g2-quasar-runs/20261107T-g2-first-logits/distribution-comparison-14.json`, SHA-256 `20c8b5d0d1b3f2eaee48b590e0eddd227779cef71cc7f7a0ce40d5f645434899`.

## Summary

- Greedy top-1 agrees on 5/14; differs on 9/14. All top-1 margins are positive and thus no exact tie is responsible.
- Mean top1−top2 log-prob margin: SGLang **1.1063 nats**, llama.cpp **1.3064 nats**.
- Mean cross entropy H(P_SGLang,Q_llama) **1.8813 nats**; reverse H(P_llama,Q_SGLang) **1.5493 nats**.
- Mean KL(P_SGLang||P_llama) **0.3275 nats**, reverse KL **0.2742 nats**.
- Mean Jensen–Shannon divergence **0.06761 nats** (range 0.00337–0.19720); mean probability overlap coefficient `sum(min(p,q))` **0.7224**.

Cross-entropy is measured using the other engine's full distribution on the same token IDs. These metrics establish substantial but heterogeneous first-position distribution disagreement; they do not identify its cause or an offending SGLang operator. Because the token winner differs for 9 prompts before any output token is consumed, the current evidence does not support teacher-forced Decode/KV as the next priority. Continue on the current HEAD-shadow Prefill/model-computation path without mixing historical private-overlay runs.
