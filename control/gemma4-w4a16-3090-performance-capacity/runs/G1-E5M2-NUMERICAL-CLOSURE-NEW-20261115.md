# G1 E5M2 numerical closure — new boundary probes (2026-11-15)

## Scope / identity

Full post-BOS GSM8K E5M2 result remains 1,067/1,319 vs frozen BF16 1,079/1,319 (report `G1-E5M2-POSTBOS-20261115.md`); not rerun here. This is a separate, new boundary diagnostic, not a replay of the missing historical N=512/513/514 samples. Inputs are token-prefix slices from frozen explicit-BOS GSM8K doc 0, exact lengths 512/513/514; tokenizer round-trip passed. Fixture files: `/data/sglang-hicache/gemma4/runs/20261115T-g1-e5m2-boundary-new/n{512,513,514}.json`.

Same checkpoint SHA/revision as prior report: `19d89d2a…fe0c5d` / `6cd26aaa2357fb2bad8c51699a7558a4d1a965bb`. SGLang test servers used W4A16 and BF16-KV or E5M2-KV, radix cache disabled, graph paths disabled so capture ran only on real eager forwards. Test-only child `sitecustomize` captured raw pre-sampling full 262,144-vocabulary logits, keyed by extend sequence length. HF reference used Transformers Gemma4 BF16 on the same checkpoint. All paths ran under `/tmp/f1-r16b-gpu-exclusive.lock`; services stopped and GPU returned to 0% / 1 MiB.

## First-step full logits

HF and SGLang all chose the same greedy token at all three lengths. HF top-1/top-2 margins were 9.125 (N512), 1.625 (N513), 7.875 (N514).

| N | HF greedy | BF16 greedy | E5M2 greedy | BF16 vs HF rel-L2 / RMSE | E5M2 vs HF rel-L2 / RMSE | BF16 chosen-token logprob (HF) | E5M2 chosen-token logprob (HF) |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 512 | 236810 | 236810 | 236810 | 0.03065 / 0.09445 | 0.06068 / 0.18699 | −0.000493 (−0.000440) | −0.000496 (−0.000440) |
| 513 | 808 | 808 | 808 | 0.02807 / 0.10589 | 0.05802 / 0.21885 | −0.193683 (−0.188103) | −0.209231 (−0.188103) |
| 514 | 236743 | 236743 | 236743 | 0.02246 / 0.08121 | 0.05825 / 0.21065 | −0.000748 (−0.000770) | −0.000916 (−0.000770) |

Maximum absolute logit error vs HF: BF16 0.341–0.440; E5M2 0.793–1.041. SGLang BF16-vs-E5M2 relative-L2 was 0.04679 / 0.05491 / 0.04619 (N512/513/514). E5M2 error is larger at every boundary, consistent with added low-precision KV error. Greedy agreement is evidence only for these fixed prompts; it does not establish full numerical equivalence.

## Continuous decoding / selected-token logprob

Each SGLang arm greedily decoded 32 tokens with token IDs returned and output logprobs. BF16 and E5M2 sequences were identical for all 32 steps at N512, N513 and N514; no free-running first divergence within the measured horizon. HF teacher-forced on each arm's exact 32 generated tokens also matched the SGLang tokens at every step. Mean absolute selected-token logprob delta vs HF teacher-forced: BF16 **0.00770 / 0.00322 / 0.00714** at N512/513/514; E5M2 **0.02496 / 0.01821 / 0.01501**. Maximum absolute deltas: BF16 **0.17987 / 0.05250 / 0.11753**; E5M2 **0.32384 / 0.22581 / 0.22556**. These are cumulative continuation measurements; HF and SGLang use distinct attention/KV implementations, so they do not alone identify which numerical component contributes.

## Capture defect and verdict

Initial instrumented startup failed because the capture hook copied CUDA logits to CPU during CUDA Graph capture. Fixed by skipping capture while `torch.cuda.is_current_stream_capturing()` and disabling CUDA Graphs in this eager diagnostic run. Retry completed all six SGLang requests, captured exactly one correctly sized full logits tensor at each N/dtype, and generated complete 32-step continuations. This is a diagnostic-hook defect, not a production model defect.

**No production code defect is confirmed; no model/kernel fix was made.** The new probes fail to reproduce the historical greedy-token mismatch: all three SGLang/HF greedy choices match and 32-step continuations do not diverge. They therefore cover current short-range boundary behavior only; the historical N512/N514 HF guard failures and N513 greedy mismatch remain unresolved as exact historical claims because the original input IDs/oracles are absent. The larger E5M2-vs-HF logit/logprob errors are consistent with quantization-related drift, but acceptance tolerances were not defined/established by these tests. **E5M2 remains NOT ACCEPTED; BF16 KV remains default.**

## Evidence

Directory: `/data/sglang-hicache/gemma4/runs/20261115T-g1-e5m2-boundary-new/`:
- immutable new fixtures `n512.json`, `n513.json`, `n514.json`;
- SGLang per-dtype `n*.json`, pre-sampling `logits.captured-*.pt`, and `server.log`;
- `hf-reference.json` full first-step logits; `hf-decode-reference.json` 32-step teacher-forced details;
- `comparison.json`, `driver.log`, per-arm GPU/port cleanup records.

No full GSM8K rerun and no performance matrix were run in this numerical closure.
