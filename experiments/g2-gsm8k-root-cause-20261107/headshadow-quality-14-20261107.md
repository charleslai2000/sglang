# Current HEAD-shadow BF16 GSM8K diagnostic (fixed 14)

## Protocol and evidence

Re-ran the same 14 five-shot prompt token-ID arrays from `20261107T-g2-first-logits/prompts.jsonl` against current HEAD-shadow SGLang BF16: GGUF SHA `7d6269096c9acbce4422fd1aa3a249436b01288868961e48ca9bb2541997f669`; `temperature=0`, `top_k=1`, `top_p=1`, neutral min-p and penalties, per-request seed 1234, max-new-tokens 512, stops `Question:`, `</s>`, `<|im_end|>`. Prompt token counts were checked by the runtime. This is the same current HEAD-shadow path as the first-step capture, not the historical private-overlay quality run. GPU exclusive lock was held throughout; no other workload or FP8/performance/capacity test.

Raw per-prompt responses: `/data/sglang-hicache/g2-quasar-runs/20261107T-g2-first-logits/head-shadow-quality-14.jsonl`, SHA-256 `d5ecbcda0c8b02f3c3a256dce0b462cd23cbb63bb2f13222ec8a835403d2d136`. Model info and service log are alongside in the same directory. Prompt IDs are the same frozen arrays; all 14 request records carry their prompt-ID hash.

## Result

Scorer (first `####\s+number`, strict gold comparison) returned **2/14 correct** (docs 6 and 18). **8/14** hit the 512-token length cap; **6/14** stopped on a configured sequence. Four outputs had no parseable answer marker; ten had at least one. A conservative six-ID exact-period detector initially flagged 4/14, but that detector missed longer text-level loops: direct inspection confirms severe repetition on docs 0 (same wrong sentence to cap), 3 and 5 (repeated boilerplate), 6 (repeated sentence after correct marker), 20 (repeated solution/marker), 24 (`Answer:` repeated), and 36 (same wrong sentence). Thus at least 8/14 show obvious repetitive continuation; doc 2 is wrong but not a verified repetition loop. At least one cap hit (doc 6) had already emitted a correct answer but continued; scorer still counts it correct.

Per doc: 0 wrong/length/512/0 markers; 1 wrong/Question stop/25/1; 2 wrong/Question stop/80/1; 3 wrong/length/512/1; 5 wrong/length/512/1; 6 correct/length/512/1; 8 wrong/Question stop/21/1; 18 correct/Question stop/80/1; 20 wrong/length/512/1; 24 wrong/length/512/0; 36 wrong/length/512/0; 39 wrong/Question stop/94/1; 47 wrong/other stop (token ID 1)/142/1; 70 wrong/length/512/0.

This confirms that current HEAD-shadow BF16 quality is still abnormal on the fixed diagnostic sample. It does not by itself validate the old private-overlay path. Because its own captured first-step vector disagrees with CPU llama.cpp on 9/14, investigation should now prioritize current-path prefill/model-computation numerical causes, not teacher-forced Decode. No production implementation defect has yet been isolated.

## Distribution comparison caveat

See `distribution-analysis-20261107.md` and its JSON artifact under `/data/.../20261107T-g2-first-logits/distribution-comparison-14.json`. Both APIs return full-vocabulary per-engine **normalized log probabilities** before greedy choice (request sampling processors are neutral; their output top-1 IDs match generated IDs). They do not expose raw logits in these records. Therefore, cross-engine differences in normalization constants prevent interpretation as raw-logit equality; the cross-entropies/KL/JS below compare probability distributions, which are valid regardless of additive logit constants.

No code fix was made. Historical overlay remains a separate unresolved provenance branch; do not combine its quality result with this HEAD-shadow run for causal attribution. Next: instrument/compare current-path same-prompt prefill logits using an independent supported numerical oracle or trace the first divergent layer only after establishing trustworthy same-run inputs/weights; recover and hash the exact old overlay separately. Keep NO-GO / E5M2 NOT ACCEPTED; no full GSM8K, FP8 optimization, capacity, or performance work.
