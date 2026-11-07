# G2 QUASAR same-weight cross-engine diagnostic — 2026-11-07

## Protocol

Replayed the frozen 14 five-shot `prompt_token_ids` arrays directly (no text retokenization) against the same QUASAR Q4_0 GGUF. Prompt artifact: `/data/sglang-hicache/g2-quasar-runs/20261107T-g2-cross-engine/prompts.jsonl`, SHA-256 `e098191d1159aa0cf926a8c6f33a1223748d12318c6b561d78484c08761dcec3`. GGUF SHA-256 verified before and after: `7d6269096c9acbce4422fd1aa3a249436b01288868961e48ca9bb2541997f669`.

CPU engine: llama.cpp revision `b49650adb31f2e49a0d76113aeb1792134fd8413`; `llama-server` SHA-256 `b8d6b0009592f37215b8d9bb637ae3764fa5ccce66bf330a490a467487fad10a`; CPU-only (`-ngl 0`), 16 threads, context 8192. `/completion` used integer token arrays, `n_predict=512`, temperature 0, top-k 1, top-p 1, seed 1234, repeat penalty 1, presence/frequency penalties 0, DRY disabled, and stops `Question:`, `</s>`, `<|im_end|>`. The raw request/response records are retained in `llama-cpu-14x512.jsonl`, SHA-256 `92fadcfc6186b36d02e16af5085d222318c06f27c8024a12987daa66b9056a9b`.

SGLang reference: cap-512 rows from the real BF16 service replay, `sglang-bf16-14x512-2048.jsonl`, SHA-256 `fcbdcd0e44c2bf0d9b80823d5d0516740d343fad136070c7a1330a80cb595585`. It used the same GGUF, BF16 compute/KV, greedy top-k 1, seed 1234, stop strings, and 512 cap; service echoed exact input IDs. Caveat: SGLang used the existing private HEAD Extend-kernel overlay and a temporary version-matched SM86 package, so this is evidence for that real runtime, not an untouched clean install.

## Per-item outcomes

| Doc | Gold | SGLang answer | llama.cpp answer | Correct S/L | SGLang finish | llama.cpp stop | Early text difference |
|---:|---:|---|---|:---:|---|---|---|
| 0 | 18 | no marker; repeats “number of eggs ... 16” | 18 | no / yes | length | `Question:` | immediate |
| 1 | 3 | 2.5 | 3 | no / yes | stop | `Question:` | immediate |
| 2 | 70000 | 120000 | 120000 | no / no | stop | `Question:` | immediate |
| 3 | 540 | 180 | 540 | no / yes | length | `Question:` | early |
| 5 | 64 | 48 | 64 | no / yes | length | `Question:` | immediate |
| 6 | 260 | 260 | 260 | yes / yes | length (then repeats) | `Question:` | early |
| 8 | 45 | 100 | 315 | no / no | stop | `Question:` | early |
| 18 | 7 | 7 | 7 | yes / yes | stop | `Question:` | early |
| 20 | 15 | 47 | 15 | no / yes | length | `Question:` | early |
| 24 | 26 | no marker; repetitive continuation | 26 | no / yes | length | `Question:` | immediate |
| 36 | 75 | no marker; repetitive continuation | 75 | no / yes | length | `Question:` | immediate |
| 39 | 18 | 6 | 18 | no / yes | stop | `Question:` | immediate |
| 47 | 800 | 500 | 800 | no / yes | stop | `Question:` | immediate |
| 70 | 7425 | 1125, then repeats | 7425 | no / yes | length | `Question:` | immediate |

Score: SGLang **2/14**, CPU llama.cpp **11/14**. Both are correct on docs 6 and 18; both are wrong on docs 2 and 8, but their answer differs on doc 8 (100 vs 315). Parsed final-answer equality is **3/14**. All llama.cpp generations stopped on `Question:` before the cap. SGLang had 8 length finishes and obvious repetition on docs 0, 6, 24, 36, 70; llama.cpp had one repetition-detection hit (doc 8) and no cap hit. These are selected diagnostic samples, not an estimate of full-set accuracy.

## Important limit on first-token analysis

Although identical frozen integer arrays were sent, the saved llama-server response does not provide a generated token-ID stream whose IDs have been verified against the SGLang/HF tokenizer vocabulary. It provides `completion_probabilities[].id`; those values are not safe to compare directly with SGLang `output_ids` without a verified vocab mapping. They visibly fail to align even where returned text starts identically. Therefore no exact first generated-token divergence index is claimed. Text confirms immediate divergence on docs 0 and 1, and early divergence in multiple other samples, but this is **not** a token-level or logit-level attribution.

Greedy intent and principal settings were matched. However, llama.cpp's sampler chain also lists `min_p`, `typ_p`, `top_n_sigma`, and `xtc` processors at defaults that are nominally inactive; identical argmax behavior has not been independently proven. CPU vs GPU/model compute numerics also differ. Thus the different outputs prove path-dependent behavior but do not by themselves prove a SGLang model-forward bug. Plausible causes still include tokenizer/GGUF vocab-ID interpretation, BOS/special-token handling, GGUF loader semantics, forward numerics/kernels, or sampler implementation.

The text/outcome comparison plus non-authoritative token fields is archived as `comparison.jsonl`, SHA-256 `575a095129b70900129ae94070bf78b69cee0ee0ff907e1db7a675be80f29c68`. A valid first-token diagnosis requires common-vocabulary logits or an authoritative ID mapping and equal sampler behavior.

## Technical conclusion and disposition

The selected examples do **not** show similar quality across engines: llama.cpp is much better and does not reproduce most SGLang repetition/cap pathologies. This disconfirms QUASAR checkpoint-only failure as a sufficient explanation for the current SGLang results. Accordingly, the QUASAR Q4_0 model is **not acceptable as a production candidate on the current SGLang path** pending a validated diagnosis. This is not a verdict that the GGUF is intrinsically unsuitable across runtimes.

No SGLang source fix is justified yet: the first-logit/token mismatch has not been established in a shared vocabulary, so the failing layer/operation is unknown. Next diagnostic, if continued, should capture comparable first-step logits from both engines after proving token-to-vocabulary identity and disabling all non-argmax sampler stages; then localize forward vs sampling. E5M2 remains **NOT ACCEPTED**. No capacity/performance testing was run. CPU llama-server was stopped after collection; the GPU lock was unnecessary for CPU execution.
