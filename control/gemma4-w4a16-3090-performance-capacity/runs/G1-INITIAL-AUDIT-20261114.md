# G1 baseline restoration — initial audit and corrected run

## Model and original protocol defect

The checkpoint is Google `gemma-4-E4B-it-qat-w4a16-ct`, revision `6cd26aaa2357fb2bad8c51699a7558a4d1a965bb`, safetensors SHA-256 `19d89d2a4b3e401a3eae75ec08ab112810421a036c91d8c8226b686be7fe0c5d`. Its config specifies pack-quantized signed INT4, group size 32. SGLang model compute is BF16; the evaluated KV cache was BF16. This is not a BF16-weight model. Generation config defaults to sampling, but current evaluation requests explicitly used greedy temperature 0 / top-p 1; sampling defaults were not the cause.

The pre-fix adapter called `tokenizer.encode(..., add_special_tokens=True)`. The tokenizer config has `add_bos_token=false`, so HF did not add Gemma BOS. All 1,319 original prompts started at token 14977 (`Question`) and omitted BOS token ID 2. Public Gemma evaluation and historical Oct. 30 report explicitly used BOS=2. Other measured protocol fields matched: GSM8K main, five plain-text Question/Answer exemplars, greedy, max 512, `Question:`/EOS/turn-end stops, first-`####` strict score. Input lengths were 618–1,629 tokens, far below context 8,192. The original BF16-KV result was 896/1,319 = 67.930%.

## Cross-engine probe

Same W4A16 checkpoint, BF16 KV, eager, no prefix cache, same frozen prompt IDs, greedy and stops were served sequentially on local SGLang and vLLM 0.32.1rc1.dev326 (not the public benchmark's vLLM 0.28.0). On 19 representative docs, generated IDs matched 13/19 without BOS and 15/19 with BOS. Remaining first divergences occurred at output steps 1–38, often on close top-5 candidates. With an exact shared input prefix, vLLM's doc512 continuation after the SGLang history chose `she` at logprob −0.357; this does not give SGLang's aligned distribution. Top-k logprobs are not full logits. Consequently, representative output differences demonstrate backend numerical/implementation variation but do not identify its source or establish all-item parity. Evidence is in `/data/sglang-hicache/gemma4/runs/20261114T-g1-reference-pair/`.

## Fix and full corrected BF16-KV run

The custom completion adapter now explicitly prepends the tokenizer's BOS (and errors if BOS is unavailable), independent of tokenizer `add_bos_token` defaults. The full canonical GSM8K main set was run once with the original checkpoint, W4A16, SGLang, **BF16 KV**, 5-shot protocol, greedy settings and original scorer; no E5M2 or performance workload was run. Every prompt was recorded with protocol and token IDs, each generation with output IDs/text and stop/finish reason. The audit contains the SHA-256 of the adapter diff patch (`744f4110fe701dfe72eaf0c34a3897e5b50639d64e9744935e6714ced8d37972`), not the adapter file's SHA-256; this patch digest is preserved as a run identifier. Independent verifier checked all 1,319 sample/audit pairs, BOS=2 on every prompt, exact generation text/IDs, and official first-answer scorer:

- **1,079 / 1,319 = 81.804%** (lm-eval displayed 0.818 ± 0.0106).
- All 1,319 ended on a stop; 1,297 stopped at `Question:`, 22 at EOS token 106; none reached length cap.
- This is +183 answers / +13.874 percentage points over the 896/1,319 no-BOS result.
- It is +9 items / +0.682 pp over the historical corrected-stop 1,070/1,319 report; historical raw item traces are unavailable, so no itemwise comparison is possible.
- It is +0.304 pp over Google's public 81.5% W4A16 score; harness/version/backend details differ, so this is contextual, not a matched reference acceptance.

Raw evidence: `/data/sglang-hicache/gemma4/runs/20261115T-g1-bf16-gsm8k-explicit-bos/`; 1,319-line `samples.jsonl`, `stop-audit.jsonl`, lm-eval logs/results, `summary.json`, `model-info.json`, SHA256SUMS. Verifier asserts every prompt starts ID 2 and every sample binds `gemma-explicit-bos-v1`; `summary.json` stores the adapter diff-patch digest above.

## Full same-checkpoint vLLM reference and verdict

A full 1,319-item vLLM run used the same exact frozen text-derived prompt IDs with explicit BOS, same W4A16 safetensors checkpoint/revision, BF16 compute and automatic/BF16 KV, greedy temperature 0/top-p 1, 512 cap and same stop strings. vLLM is local 0.32.1rc1.dev326 (not public 0.28.0), eager/no prefix cache, TP1. Output IDs, texts, per-item prompt and hash were recorded. Independent lm-eval 0.4.13 `exact_match_hf_evaluate`, first-`####` scoring gives **1,068/1,319 = 80.970%**, versus SGLang **1,079/1,319 = 81.804%**: vLLM −11 answers / −0.834 pp. Full output IDs were exactly equal on **950/1,319 (72.024%)**; 369 items had a token-sequence divergence. Thus the large original shortfall is explained by missing BOS, but residual cross-engine generation differences remain. This is quality-level convergence, not token/numerical equivalence. No full aligned logits were captured for the 369 divergences, so their exact kernel/model-path causes remain undetermined.

Reference evidence: `/data/sglang-hicache/gemma4/runs/20261115T-g1-bf16-gsm8k-explicit-bos/vllm-reference/` (`records.json`, `summary.json`, `server.log`, SHA256SUMS). The SGLang corrected run and item evidence remain at `/data/sglang-hicache/gemma4/runs/20261115T-g1-bf16-gsm8k-explicit-bos/`.

**Root-cause result: PASS for the low 67.93% baseline.** Missing Gemma BOS is directly confirmed and fixing it raised full GSM8K by 183 answers / +13.874 pp with same SGLang, checkpoint, BF16 KV and scorer, restoring the historical/public accuracy range. Historical Oct. 30 corrected result was 1,070/1,319; current is +9 answers. Public W4A16 was 81.5%; local vLLM is 80.97%. Raw historical Oct. 30 items are unavailable, so itemwise equality is unverified.

**Numerical parity / engine identity: NOT ACCEPTED.** Full token equality is 72.02%, despite a close task score; no claim of numerical equivalence. The user's requested score/root-cause investigation is resolved, but residual token divergences are observed and exact logit/kernel attribution remains blocked. Existing N=512/513/514 numerical guards are unchanged and independently effective; this GSM8K score does not clear them. BF16 KV remains the default/accepted mode; E5M2 remains NOT ACCEPTED. T004 is unchanged and paused.
