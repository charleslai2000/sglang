# G1 Gemma 4 E4B / RTX3090 GSM8K baseline restoration

## Goal
Identify and repair why current W4A16 + BF16-KV GSM8K scored 896/1,319 (67.93%) versus historical 1,070/1,319 (81.12%) and public Google W4A16 81.5%, then validate corrected BF16-KV baseline against same-checkpoint vLLM and full GSM8K.

## Scope and constraints
Start from `cc63ec447c` records/current source; exact Google W4A16 checkpoint, revision, weight format, tokenizer/BOS, prompts, generation, stop and scorer inspection; no-score-manipulation. Prefer same-prompt vLLM/SGLang BF16-KV representative comparison, token IDs and first-divergence logits; fix and verify; then one complete 1,319-item BF16-KV rerun. Do not rerun E5M2/perf/T004; keep E5M2 NOT ACCEPTED and N512/513/514 guards independent. Reuse current checkout only; no new worktree or cleanup of unrelated dirty/untracked content. GPU is authorized; hold `/tmp/f1-r16b-gpu-exclusive.lock` through GPU work and clean all services afterward. Commit/push necessary repairs and evidence.

## Completion
Root cause established with reproducible evidence; repaired protocol/implementation validated against same-protocol vLLM reference; full item-level 1,319 GSM8K corrected baseline and report; acceptance only if reference-level behavior supported and unexplained gap closed, otherwise NOT ACCEPTED with remaining cause isolated. No general numerical-equivalence claim.

## Current result
BOS omission experimentally explains the large score loss: full BF16-KV score recovered from 896/1,319 to 1,079/1,319 under unchanged model/backend/scorer. Item-level protocol audit passes. Full vLLM reference and remaining-token-divergence attribution are still open; this Goal is active and not accepted pending matched reference coverage.
