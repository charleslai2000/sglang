# Full-set GSM8K vLLM replay — 2026-10-27

## Protocol and identity
The GPU replay `20261026T-gsm8k-vllm-full-matched-r6` completed 1,319 requests with pinned checkpoint revision `6cd26aaa2357fb2bad8c51699a7558a4d1a965bb` (model SHA-256 `19d89d2a4b3e401a3eae75ec08ab112810421a036c91d8c8226b686be7fe0c5d`), vLLM `0.32.1rc1.dev326+gc722f3a53`, BF16 compute/KV, W4A16 Marlin, Triton attention, eager mode, greedy temperature 0/top-p 1, and 512-token cap. Inputs were reconstructed from the exact saved SGLang BF16 prompt text, tokenizer encoding plus BOS ID 2. Every response's `prompt_token_ids` exactly matched its expected request; the artifact has 1,319 contiguous doc IDs and unique numeric request IDs. This is response-side identity evidence; the configured temporary Worker hook did not produce a worker-capture directory/artifact.

SGLang's E5M2 request audit proves its actual requested stop list was `Question:`, `</s>`, `<|im_end|>`, `<eos>` (1,319/1,319 requests). The vLLM replay used the identical list, confirmed in its SamplingParams and stop outcomes. SGLang's corrected-stop evaluation used `max_running_requests=1`, `batch_size=1`, and decode graph batch 1. The full vLLM r6 run used `max_num_seqs=16` (the persisted manifest erroneously says 1; the runner configuration says 16 and should be used as the intended setting, with no scheduler batch trace retained). Thus prompt, stop strings, checkpoint, dtype, greedy/cap protocol match, but runtime batching/scheduling does not. vLLM eager versus SGLang CUDA Graph decode is an additional execution-path difference. Neither output divergence nor score gap alone identifies an engine-specific correctness defect.

## Scores and paired outcomes
Scoring uses the official lm-eval 0.4.13 GSM8K strict-match first-`####` procedure. For vLLM, completion text is cut before the generated `Question:` marker before scoring; this excludes the retained answer boundary without changing generated token history. All sampled stop behavior: 1,284 finished on `Question:`, 30 on EOS token ID 106, and 5 reached length 512.

| Arm | Correct | Score | Both correct | Both wrong | SGLang-only | vLLM-only |
|---|---:|---:|---:|---:|---:|---:|
| SGLang BF16 vs vLLM | 896/1,319 | 67.93% vs 80.89% | 830 | 186 | 66 | 237 |
| SGLang E5M2 vs vLLM | 892/1,319 | 67.63% vs 80.89% | 813 | 173 | 79 | 254 |

Exact paired McNemar two-sided p-values are `8.80e-24` (BF16) and `1.45e-22` (E5M2). These quantify discordance conditional on these two runs, not causal attribution or general engine quality. Matching input token IDs does not match decode batch composition, graph/eager path, or numerical execution. The 128-item subset is separately scheduled and is not assumed to reproduce full-run outputs.

## Limits and artifacts
No historical SGLang execution IDs/batch schedule exist for the old 81.58% run, so neither this comparison nor the 128-item wave reproduces it. QUASAR's public 81.5% remains contextual, not a matched-runtime result. This replay does not resolve the frozen N=512/514 HF guard, which remains FAILED, nor does it qualify G1.

Reproducible scorer and machine-readable summary are external at `/tmp/score_vllm_gsm8k_r6.py` and `/data/sglang-hicache/gemma4/runs/20261026T-gsm8k-vllm-full-matched-r6/`. Summary JSON: `/data/sglang-hicache/gemma4/runs/20261026T-gsm8k-vllm-full-matched-r6/analysis.json`. Raw results SHA-256: `1dd7d98bf772ac1cf06c9f3523165eb96f692b5cef8bb2be11c609e12cbea09b`. No production code, math, or tolerances changed.
