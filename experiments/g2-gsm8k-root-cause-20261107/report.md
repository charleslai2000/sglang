# G2 QUASAR GSM8K root-cause evidence — 2026-11-07

## Scope and identities

A corrected-RoPE full 1,319-item rerun has since completed; its complete result is appended below. Historical BF16 baseline raw result remains unavailable for recalculation, so its preserved counts are explicitly identified as archived. The earlier sections document prior evidence and retain their original provenance.

- Model: `/data/models/gemma4-quasar-q4_0/gemma-4-E4B-it-QUASAR-Q4_0.gguf`; SHA-256 `7d6269096c9acbce4422fd1aa3a249436b01288868961e48ca9bb2541997f669`.
- Restored train Parquet SHA-256 `ea82612ea9582142387730c793eb67d3b12849002bc0b7fa6f8efafa7351419d`; normalized pinned train JSONL SHA `6043ef64147b59871f4fd3adf669c306fe0a4c27e5a5c4bfb761f3f084895a13` (7473 rows).
- Earlier restored test JSONL SHA `3730d312...` differed from history. For the corrected full run, official test Parquet SHA `ee7b8da9e381df27b9e3f7758a159ab2bdaa4dbaa910546cbbc47e0cb44e4f59` was normalized to the exact historical test JSONL SHA `752adc99f23132275139f1f7be57126b08735a55daf0c56859ee6df70abafbac` (1,319 rows).
- Rebuilt five-shot inputs using lm-eval 0.4.13's `DEFAULT_SEED[3]=1234`, one shared Python `Random(1234)` across ascending test doc IDs, 5 samples from the training split per doc, the task's `Question: {question}\nAnswer:` and target concatenation, and explicit BOS=2. Token IDs were produced by the preserved Gemma tokenizer. For docs 8,18,20,24,36,39,47, the reconstructed prompt-ID hashes exactly match retained history in `/tmp/gsm8k-summary.json`; all 14 service prompt echoes matched.
- Reconstructed 14-sample prompt artifact SHA-256 `e098191d1159aa0cf926a8c6f33a1223748d12318c6b561d78484c08761dcec3`.
- Real replay result artifact SHA-256 `fcbdcd0e44c2bf0d9b80823d5d0516740d343fad136070c7a1330a80cb595585`; 28 rows = 14 docs × caps 512/2048. Files currently at `/tmp/g2-rebuilt-fewshot-14.jsonl` and `/tmp/g2-gsm8k-controlled-14.jsonl`.

## Previously recorded full BF16 result audit (not recomputed now)

The prior result SHA was `002ea777f449f195fe1a3c74b77bddbb7769b91b053542e5bc158d8729e368a1`; its exact JSONL is no longer present after cleanup. The recorded audit says 398/1319 correct (30.17%), `finish_reason=length` 833/1319, no `####` marker 197/1319, first-marker outputs with a wrong extracted value 724, and non-length/stop outputs wrong 320. The latter follows the mutually exclusive answerability partition: 486 stop-finished minus 166 correct = 320. Categories overlap: of 833 length hits, 232 scored correct and 601 wrong; among length-hit wrong outputs, 197 had no marker and 404 had a wrong marker value. All wrong output categories partition as 601 truncated-but-wrong + 320 normally stopped-but-wrong = 921. No whitespace-relaxed scoring gain was recorded; strict-vs-whitespace-tolerant extraction recovered zero samples. The scorer did not miss any valid first `####` answer in the saved audit. These historical counts are reported as archived measurements, not fresh recalculation.

Conclusion on the 30.17%: cap hits are a major symptom, but do **not** mainly explain the low score. 166/486 (34.16%) normally stopped answers were still wrong. Parser/protocol explanations are not supported by the archived checks: explicit BOS/stop/seed were fixed for the valid run, prompt IDs echoed exactly, whitespace relaxation changed no score, and the initial protocol-invalid run was excluded.

## Controlled BF16 replay

Runtime was the real G2 BF16 service configuration: QUASAR GGUF, BF16 compute/KV, context 8192, Triton, chunked prefill 2048, no graphs, no Radix cache, max running requests 1; private HEAD attention overlay plus a `/tmp` SM86 package assembled from the installed version-matched binary to replace the AOT directory removed during data cleanup. GPU lock `/tmp/f1-r16b-gpu-exclusive.lock` was acquired and held. Server exited after the run; final GPU was 1 MiB, 0% utilization. SGLang stop list was `Question:`, `</s>`, `<|im_end|>`; greedy top-k 1, per-request seed 1234. All requests echoed exact input IDs.

| cap | completed | correct | length hit | no parseable first marker | marker present, wrong | stopped wrong |
|---:|---:|---:|---:|---:|---:|---:|
| 512 | 14 | 2 | 8 | 4 | 8 | 5 |
| 2048 | 14 | 2 | 8 | 4 | 8 | 5 |

For cap 512, the 12 wrong items partition mutually exclusively as 3 truncated with a wrong first marker, 4 truncated with no parseable marker, and 5 normally stopped with a wrong marker. The 8 length-hit items include one whose first answer is correct (doc 6, `####260`) but which continues into a repetition loop; length-hit wrong = 7.

These 14 were selected to represent previous failed/cap-hit cases, not a random/full-set estimate. Increasing cap did not rescue any item. All eight items that hit the 512 cap also hit 2048. Docs 0,3,5,20,24,36,70 continued to the larger cap; doc 6 retained its valid first `####260` and continued repeating unrelated text; docs 1,2,8,39,47 stopped early on wrong answers; doc18 was correct at both caps.

### Representative raw completions

- Doc 0, gold 18, both caps: `The number of eggs she sells is 16.` repeated until cap; no `####` final answer. 512→2048 did not finish reasoning.
- Doc 1, gold 3, both caps: `2 + 0.5 = 2.5 bolts in total.\n#### 2.5`; normal `Question:` stop, clearly wrong arithmetic, unaffected by cap.
- Doc 2, gold 70000, both caps: `... increase in value is 150% of $80,000 ... 120000.\nSo, the profit is $120000.\n#### 120000`; normal stop, wrong profit calculation.
- Doc 3, gold 540, both caps: `He runs 3 sprints * 60 meters/sprint = 180 ... He runs 1 week = 180 meters.\n#### 180`; reaches cap while continuing with repetitive post-answer text.
- Doc 6, gold 260, both caps: `... Total sheep: 20 + 80 + 160 = 260 sheep.\n#### 260\n\nQuestion Stella ...` followed by repeated text until cap. Correct first answer despite truncation.
- Doc 70, gold 7425, both caps: `Total students = 5*15=75. Total money = 75*15=1125.\n####1125` then repeated summary. Missing a space after marker makes this invalid under the strict scorer; even a whitespace-tolerant parser would extract 1125, still mathematically wrong. Cap increase does not correct it.

## Answer to requested questions and disposition

1. Archived full-set 512-token cap hits: **833**.
2. Archived full-set no `####` marker: **197**.
3. Archived valid-but-unparsed/score-lost answers: **0 evidenced**. Relaxing marker whitespace changed no score; generated marker with wrong value is a model answer error, not an extraction omission. Doc70's missing whitespace is malformed and the number is wrong either way.
4. Archived normal-stop but wrong answers: **320**.

Mutually exclusive final outcome classes for the archived full set:
- Correct answer: **398** (232 length-hit + 166 normally stopped).
- Truncated and wrong: **601** (197 without a marker + 404 with a wrong first marker).
- Normally stopped and wrong: **320**.
- Total wrong: **921**. The zero evidenced extractor misses are subsumed in the underlying output classes; wrong-valued markers are model answer errors, not score-lost correct answers.

The 14-item controlled test falsifies “raising the cap alone resolves the issue”: zero new correct answers at 2048 vs 512. It also directly demonstrates genuine normal-stop math errors. No confirmed evaluator implementation bug was found, so no production code fix is justified. Root cause is bounded: generation pathology (repetition/long continuation), missing/malformed answers, and incorrect reasoning; this is not mainly a scorer/parser defect or merely a cap-size issue. It does **not** yet distinguish QUASAR checkpoint behavior from SGLang model-forward/quantized execution for the incorrect reasoning; E5M2 remains NOT ACCEPTED and capacity/performance remains prohibited.

## Same-forward numerical capture update

A locked real BF16 SGLang service was rerun on frozen docs 3/24/70 with immutable diagnostic snapshots and no API logprob expansion. Exact prompt IDs matched the preserved prompt artifact; full-prefix Layer 5 EXTEND captures contain 821/1104/797 tokens and are paired by request ID plus Forward UUID to finalnorm and 262144-wide raw LM-head logits. Raw-logit argmax exactly matches the service output token IDs (1293/107/12613). This verifies raw logits to greedy token for these three requests only; it does not close the normalized-logprob API comparison to llama.cpp or establish a Layer 5 defect. GPU was released and measured at 1 MiB, 0% after service shutdown. The diagnostic snapshot patch is not a production arithmetic fix.

## RoPE config intervention update — 2026-11-09

The frozen GGUF frequency mask encodes 64 active full-attention angles of 256 (factor 0.25), while the prior GGUF config supplied factor 1.0. A mask-validating inference helper and 8 unit tests were added. A real locked BF16 production-A8 doc24 run confirmed factor 0.25 changes Layer5 Q/K RoPE and downstream attention/post-attention boundaries; Q/K RoPE is close to pinned llama.cpp. The same frozen 14 HEAD-shadow prompts improved from 2/14 to 9/14, all prompt hashes equal; corrected responses had no cap hits/repetition flags. Details and numerical limits are in `layer5-sglang-llama-doc24-boundaries-20261109.md`.

## Corrected-RoPE full-set qualification — 2026-11-10

Fix commit `3bf30274a281775b4eb813c08a85414b96821df2` is pushed to `origin/3090-gemma4-e4b-hicache`, whose ref matches the local HEAD. It changes only `python/sglang/srt/configs/gemma4_gguf.py` and `test/registered/unit/models/test_gemma4_gguf_rope_config.py`; eight tests had passed before commit. The helper validates the GGUF active-prefix/identity-tail mask and infers full-attention partial rotary factor 0.25. GGUF model SHA remains `7d6269096c9acbce4422fd1aa3a249436b01288868961e48ca9bb2541997f669`.

A real locked BF16/BF16-KV TP1 HEAD-shadow service completed all 1,319 official GSM8K prompts: greedy top-k 1, per-request seed 1234, explicit BOS, stop list `Question:`, `</s>`, `<|im_end|>`, 512 cap, Triton eager, chunked-prefill 2048, context 8192. Results are `/data/sglang-hicache/g2-quasar-runs/20261110T-g2-rope-bf16-quality/results.jsonl`, SHA-256 `3e0cdfdce5d2a2c864c6f4ab7f83b4ebe71982306ebf2fafe943601b1a32a8e4`; fixture SHA-256 `2e64e8865f9e314eadb3320593a23e65ebc3f01daf6d2f4662c35983df5c3f86`. Results are exactly 1,319 ordered rows; each row's prompt text and token-ID hashes match its fixture, and each prompt token length matches. The test normalized SHA matches the historical test SHA; 14 retained historic prompt hashes match 14/14. The historic complete prompt fixture was lost, so the remaining reconstructed prompts cannot be byte-compared individually.

Full result: **1,091/1,319 (82.714%)**, against archived same-QUASAR BF16 baseline 398/1,319 (30.174%), a gain of 693 items / 52.540 percentage points. Failure/termination counts: 8 `length` cap hits (0.61%), of which 2 still score correct and 6 are wrong without a marker; 1,311 normal stop completions. 42 outputs meet the repeated-4gram≥8 flag (3.18%), overlapping with cap: 25 of those scored correct and 17 wrong. There are 16 no-marker outputs (all wrong), 212 outputs with a wrong strict-last marker, and 222 total normally stopped wrong outputs. No multi-marker output or next-question leakage was found. Because no output has multiple markers, the first/last extraction is identical. All 1,319 rows were rescored with the historical `gsm8k-strict-last` filter and lm-eval exact-match metric; parity is 1,319/1,319. Frozen 14 subset scored 9/14, consistent with prior bounded intervention.

Comparability: test questions/targets, recorded few-shot reconstruction seed/order/BOS/scoring protocol match; historical retained hashes match 14/14. However the historic full prompt fixture is absent, and historical G1 used a private Extend-kernel overlay while this is current HEAD-shadow. Therefore this is a valid full qualification of corrected current HEAD-shadow BF16, not a bitwise historical-overlay reproduction or a single-variable explanation of the 52.54pp historical gap. Historical detailed score, doc-level failures and archived raw hash are in the control record. The different-checkpoint W4A16 results are not an oracle.

**Disposition: corrected current HEAD-shadow BF16 RoPE quality gate GO on this full frozen set. E5M2 remains NOT ACCEPTED.** This result does not qualify E5M2/FP8, capacity, or performance; the historical private-overlay path has not been rerun. Service exited, lock released, and final GPU state was 1 MiB / 0%.
