# G2 first-step full-vocabulary comparison (2026-11-07)

## Scope and evidence

Fixed 14 prompts only; same GGUF, frozen integer prompt IDs. SGLang run used the HEAD-shadow kernel source (not the private historical attention overlay) and captured generated-token `output_top_logprobs` with all 262,144 vocabulary IDs. For all 14, its top-logprob token is the generated greedy token. llama.cpp CPU server revision `b49650adb31f2e49a0d76113aeb1792134fd8413`, same prompt IDs, explicitly neutral penalties/filter settings, top-k=1/temperature=0, and `n_probs=262144`; response contains 262,144 `top_logprobs` entries per prompt. Tokenizer vocabulary ID identity was previously verified.

llama.cpp JSONL SHA-256: `2dd3928ad093903b98b21103eef9ff3f431f689c17c6be75f87e1acafff8add4` at `/data/sglang-hicache/g2-quasar-runs/20261107T-g2-first-logits/llama-first-top1.jsonl`. SGLang per-prompt responses `toplogprobs-*-correct.json` in the same directory. These are complete log-probability vectors, not raw logits; each engine's normalization constant is discarded, so direct log-prob equality or margin comparisons are not valid measures of raw-logit equality.

## Result

Greedy top-1 token IDs disagree on **9/14** selected prompts and agree on docs **3, 6, 8, 18, 20** (5/14). Pairs (doc: SGLang / llama.cpp): 0: 669/57681; 1: 236743/669; 2: 24092/669; 3: 1293/1293; 5: 107/669; 6: 25930/25930; 8: 3415/3415; 18: 45917/45917; 20: 669/669; 24: 107/1637; 36: 5315/38778; 39: 5165/1637; 47: 9595/669; 70: 12613/13444.

This locates a first-token model-path divergence before any generated-token Decode/KV or later sampling history. It does **not** localize the defect to a specific Prefill kernel or prove the checkpoint is at fault: SGLang used current HEAD-shadow attention, while the historical quality service used a private attention overlay whose exact source/dependencies remain unrecovered. A new production-current run is not a faithful replay of that historical service. The two implementations may also differ in GGUF tensor execution/numerics. No production defect has been isolated and no source change is justified.

## Limitations and next diagnosis

The capture is complete **log probabilities** for all vocabulary IDs, not full raw logits. The records are not accompanied by an exact run-level SGLang source/overlay manifest for each per-prompt capture; preserve that caveat. This establishes argmax disagreement at the first generation position but not its exact cause. Next useful step is a controlled SGLang-vs-llama.cpp teacher-forced comparison on the same prompt plus selected known next-token IDs, while holding the current SGLang path fixed; separately recover and hash the historical private overlay before making any claim about the old quality-run path. No capacity, performance, full GSM8K, or FP8 work was performed. No production source was edited or committed by this comparison; unrelated dirty shared-tree state is untouched.
