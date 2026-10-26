# GSM8K stop-boundary flip attribution — 2026-10-26

## Finding

The old-to-corrected-stop score movement is **not explained by suffix truncation of the same generated prefix**. The old stop list was `</s>, <|im_end|>`; the corrected list adds `Question:`. Although the dataset, prompt text/tokens, checkpoint, engine, temperature (0), max tokens (512), random seeds, context and task scorer are matched, adding a stop sequence changes the autoregressive run as soon as any generated prefix contains that sequence. It is therefore a generation intervention, not merely removal of old output suffixes. On every score-flipped sample the saved decoded output strings already differ before the old output's first `Question:` (no flip had identical decoded text through that point). **This is decisive decoded-text evidence of pre-boundary generation divergence.** The JSONL sample artifacts do not preserve the old runtime request/output token IDs, so an exact generated-token-ID divergence count/location cannot be claimed; re-encoding decoded text is not a valid substitute.

| KV arm | Old → corrected score | Flips | Old correct → new wrong | Old wrong → new correct | Flips whose saved old text diverges before first `Question:` | Old first `####` occurs after first `Question:` on flipped rows |
|---|---:|---:|---:|---:|---:|---:|
| BF16 | 1076/1319 (81.58%) → 896/1319 (67.93%) | 304 | 242 | 62 | 304/304 | 3 |
| E5M2 | 1071/1319 (81.20%) → 892/1319 (67.63%) | 327 | 253 | 74 | 327/327 | 1 |

Only **1/304 BF16** and **0/327 E5M2** flipped old scores were correct answers whose first `####` occurred after `Question:`; those are the cases where old continuation into the following example directly supplied the scored answer. Most flipped old scores (301 BF16, 326 E5M2) came from a first `####` before the first `Question:` and were recoverable under the official first-answer scorer. The remaining flipped rows generally had no literal `Question:` in the saved old text or no first `####`; those score changes likewise cannot be attributed simply to stripping a post-boundary suffix.

The changed stop list provably causes different termination policy and corrected runs stop at the first literal `Question:` where encountered (current E5M2 request audit: 1,234 such stops). But the artifacts do **not** support the counterfactual statement that the new 67.93%/67.63% scores equal the old runs with their suffixes removed. Both the old full generations and the corrected-stop generations are different continuations. Hence report score deltas as *observed between two stop-policy runs*, not as causal per-item “suffix truncation gains/losses.”

## Protocol / execution comparison

Inspected old and corrected BF16/E5M2 lm-eval result configs, logs, task YAML, adapter, server logs, manifests, sample JSONL, and scoring script. Matched: the 1,319 GSM8K question/answer pairs and ordering; prompt text and explicit BOS ID 2; pinned model/checkpoint; SGLang backend and service configuration; 5-shot; greedy (`do_sample=false`, temperature 0); generation cap 512; context 8192; lm-eval seeds (random 0, NumPy/PyTorch/fewshot 1234), adapter request seed 1234; official first-`####` `strict-match` scorer. The intended material protocol delta is the missing `Question:` stop in the old run. The old samples' per-item scores reproduce the aggregate scores exactly. The two adapters also use identical prompt encoding code (text re-tokenized by SGLang server; `tokenized_requests=false`).

Because the old adapter's detailed request audit was not preserved, exact old request IDs, actual transmitted prompt ID arrays, finish reasons and output token IDs are unavailable. Paired prompt text/tokenizer replay and run configuration are evidence of matched prompt inputs, not proof of every old request's exact wire payload. No request IDs or output token IDs have been inferred from other runs.

## Scores and public reference

The corrected-stop scores are valid measurements of their **own** completed local generations and official scoring: BF16 896/1319 = **67.93%**, E5M2 892/1319 = **67.63%**. Their paired difference is −0.303 percentage points (70 BF16-only, 66 E5M2-only; paired bootstrap 95% CI [−2.047pp,+1.440pp]). E5M2 has a complete 1,319-row request audit; BF16 request-level stop audit is unavailable, so symmetry of that qualification is not established.

Against QUASAR's published 81.5% (n=1,319), corrected BF16 is **13.57 percentage points lower**, E5M2 **13.87 points lower**. QUASAR specifies lm-eval 0.4.13, vLLM 0.28.0, FP16, five-shot, BOS enabled; local uses SGLang and BF16 compute. QUASAR's public document does not provide raw GSM8K generations or the exact effective stop list. Thus 81.5% is a contextual, non-protocol-identical reference, not a strict reproduction target. The old local ~81% is also not a valid isolated-answer generation comparison because it omitted `Question:` and frequently continued into later examples.

## Evidence index

- Run configuration and aggregate results: `/data/sglang-hicache/gemma4/runs/20261026T-gsm8k-g1-final/{bf16,e5m2}/lm-eval/*/results_*.json` and corresponding `lm-eval.log`.
- Corrected-stop configuration/results: `/data/sglang-hicache/gemma4/runs/20261026T-gsm8k-g1-final-bos/{bf16,e5m2}/lm-eval/*/results_*.json`.
- Per-item old/new decoded outputs: each run root's `{bf16,e5m2}/samples.jsonl`; paired old-vs-new scoring: corrected run root `paired-scores.json`.
- Stop-policy evidence: old run manifests/logs and corrected run `e5m2/stop-audit.jsonl`, `e5m2/stop-audit-summary.json`; BF16 corrected-stop audit is empty and must not be cited.
- Reproducible offline script: `control/gemma4-e4b-rtx3090-hicache/runs/audit_gsm8k_stop_prefix.py`; outputs: corrected run root `bf16/offline-stop-prefix-audit.json`, `e5m2/offline-stop-prefix-audit.json`.
- Scorer: `control/gemma4-e4b-rtx3090-hicache/runs/gsm8k_official.yaml`, `score_gsm8k_text.py`.
- Public contextual reference: QUASAR `EVAL.md`, `https://huggingface.co/QUASAR-QAT/gemma-4-E4B-it-QUASAR-W4A16-G64/resolve/main/EVAL.md`.

No model run was repeated. No scoring code or production math changed. Frozen N=512/514 numerical guard remains FAILED and unchanged; G1 remains NOT ACCEPTED.
