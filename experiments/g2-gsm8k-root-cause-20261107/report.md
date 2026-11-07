# G2 QUASAR GSM8K root-cause evidence — 2026-11-07

## Scope and identities

No full 1,319-item rerun was performed. The original BF16 raw result was removed by the authorized `/data` cleanup and is **not currently available to recompute**. This report distinguishes previously preserved audit counts from the newly executed bounded replay.

- Model: `/data/models/gemma4-quasar-q4_0/gemma-4-E4B-it-QUASAR-Q4_0.gguf`; SHA-256 `7d6269096c9acbce4422fd1aa3a249436b01288868961e48ca9bb2541997f669`.
- Restored train Parquet SHA-256 `ea82612ea9582142387730c793eb67d3b12849002bc0b7fa6f8efafa7351419d`; normalized pinned train JSONL SHA `6043ef64147b59871f4fd3adf669c306fe0a4c27e5a5c4bfb761f3f084895a13` (7473 rows).
- Restored test JSONL SHA `3730d312f6e3440559ace48831e51066acaca737f6eabec99bccb9e4b3c39d14` (1319 rows). This differs from old recorded test SHA `752adc99...`, so the old full output cannot be reconstructed from this file alone. Its sampled questions and answers were confirmed to match the previously listed GSM8K questions.
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
