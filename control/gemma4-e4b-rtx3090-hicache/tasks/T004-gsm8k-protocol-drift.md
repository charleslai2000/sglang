# T004 — GSM8K protocol drift attribution

Status: ACTIVE
Work area: repo root (offline analysis and narrowly scoped evaluation code)

## Objective
Explain the nominal 81% → 68% GSM8K score change from existing artifacts, establish whether current BF16/E5M2 results are scoreable/auditable, and adjudicate comparability with public QUASAR G32 81.5%. Repair only a demonstrated adapter/fixture defect. Keep production model math and the frozen numerical Guard unchanged; preserve unrelated Falcon state.

## Inputs
`runs/GSM8K-G1-20261026.md`; raw runs under `/data/sglang-hicache/gemma4/runs/20261026T-gsm8k-g1-final/`, `...-g1-r2/`, `...-g1-r3/`, `...-g1-final-bos/`; public QUASAR `EVAL.md`; local lm-eval 0.4.13 task/filter, tokenizer, checkpoint and adapter.

## Completion
Offline per-item/token-level comparison; quantify changed outcomes and identify causes without discarding recoverable first answers. Verify local dtype, prompt/BOS/few-shot ordering, stops, filter/scoring against public protocol. Integrate an evidence-backed adapter/fixture correction and report usable paired scores/audit limits, protocol differences and scoped commit/remote status. No new full evaluation unless artifacts cannot answer the objective and a demonstrated fix changes raw generations.

## Result
Old and current runs all contain 1,319 identical question/target pairs, byte-identical prompt strings and equal prompt hashes per item. Re-tokenization with the pinned tokenizer confirms identical tokens across rounds. Local Gemma tokenizer does not insert BOS automatically (`encode(..., add_special_tokens=True)` starts with token 14977, not ID 2); adapter explicitly prepends `[2]` in both rounds. The pinned checkpoint, SGLang service, BF16/E5M2 KV arms, five-shot deterministic examples/order, greedy temperature 0, 512 cap, and official lm-eval `strict-match` first-`####` scorer are unchanged. The saved task generation config's effective change is old `until=[</s>, <|im_end|>]` versus current `until=[Question:, </s>, <|im_end|>]`.

Old scores: BF16 1076/1319 (81.58%); E5M2 1071/1319 (81.20%). Their stored official first-answer score is reproducible and equals lm-eval's saved metric; do not replace it with strict-last or discard the first answer. But old outputs overgenerate: `Question:` occurs in 1,296 BF16 and 1,294 E5M2 outputs; all 1,319 responses per arm reach the 512-token cap. Current stop-protected outputs contain no next-question leakage and yield BF16 896/1319 (67.93%) and E5M2 892/1319 (67.63%).

Per-item first-answer rescoring with the same official first-match extractor: BF16 1076→896 (242 old-correct/new-wrong; 62 old-wrong/new-correct; 304 changed); E5M2 1071→892 (253 lost; 74 gained; 327 changed). This is not merely scoring cleanup: first-answer correctness changed on all 327 E5M2 flip items and 303/304 BF16 flip items. Old continuations generated additional Q/A examples up to the token cap; those out-of-boundary tokens fed back into autoregressive decoding and changed later first answers. The 81% score is an actual score on the old emitted text under official `take_first`, but that generation protocol omitted the task's `Question:` stop and therefore was not a valid isolated-answer evaluation. The 68% score reflects changed outputs when the correct stop boundary prevents that feedback; do not claim that truncating old text would itself produce the new answers.

Current paired result: both correct 826, both wrong 357, BF16-only 70, E5M2-only 66; E5M2−BF16 -0.303pp, paired bootstrap 20,000/seed 20261026, 95% CI [-2.047pp,+1.440pp]. Old pair: both correct 1,020, both wrong 192, BF16-only 56, E5M2-only 51; paired delta -0.379pp, 95% CI [-1.971pp,+1.137pp]. Current E5M2 audit is complete: 1,319 rows, 1,303 stop finishes (1,234 `Question:` matches, 69 EOS matches), 16 length finishes at 512, zero verifier errors. BF16 samples/results are complete, but manual restart truncated its request audit; that audit cannot be recovered. No new full run is needed for the offline attribution.

Adapter/YAML stop correction was tested with a separate real 12-request GPU probe: 12/12 stopped, no next-question leakage. Current E5M2 full-run audit independently validates all 1,319 outputs. The incomplete BF16 request audit remains a stated acceptance limitation.

Directly fetched QUASAR `EVAL.md`: downstream harness lm-eval 0.4.13 + vLLM 0.28.0, 8K context, five-shot lane `add_bos_token=True`; Google QAT W4A16 strict GSM8K 81.5% (n=1,319). Local evaluation shares lm-eval version, five-shot, dataset family/count, explicit BOS ID 2, greedy decoding and strict first-`####` extractor. Local runtime is SGLang rather than vLLM; local model config and service load default to BF16 compute with W4A16 linears, while QUASAR explicitly serves FP16. Public `EVAL.md` does not expose raw GSM8K generations or per-task effective stop list, so exact stop-boundary parity cannot be verified. Public 81.5% is a reported single Google QAT row, not the local paired cache-mode comparison. It is a useful close reference but not a protocol-identical reproduction; no direct parity claim is warranted.

## Remaining
Commit and push only reviewed, scoped Gemma adapter/task/report changes using explicit path staging; verify remote SHA. Do not change production math/Guard, touch unrelated dirty paths, or run another full evaluation.
