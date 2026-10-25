# Official chat-template task quality — 2026-10-25

## Method

Pinned W4A16 checkpoint `6cd26aaa2357fb2bad8c51699a7558a4d1a965bb`, weights SHA-256 `19d89d2a4b3e401a3eae75ec08ab112810421a036c91d8c8226b686be7fe0c5d`. Loaded checkpoint `AutoProcessor` and applied its canonical `chat_template.jinja` (SHA-256 `0a2c8073c878ab1da004bee933a998606537bbb62016310352c7285c3f01c5b5`) to each user message with `add_generation_prompt=True`; supplied the resulting exact `input_ids` to the real SGLang HTTP service. Standard terminal `<turn|>` token 106 was a stop ID; max 32 new tokens, temperature 0, radix disabled, one request at a time. Compared BF16 and `fp8_e5m2` KV with identical prompt IDs, model revision and service configuration. Both runs under `/tmp/f1-r16b-gpu-exclusive.lock`; decode capture bound by returned request RID, and every captured step had `cuda_graph_replay=true`. The checkpoint `generation_config.json` lists EOS IDs `[1,106,50]`; this test explicitly stopped on user-turn end `106`, so the observed `finish_reason` is `stop` matched 106. It did not verify model-emitted EOS IDs 1 or 50.

The four tasks were: factual short QA (22 input tokens), arithmetic short QA (23), 16,384-token exact-length synthetic archive lookup, and 32,768-token synthetic archive lookup. Long needle codes were embedded at ~0.500 of decoded prompt characters in repetitive context, with query after the needle. The 32K prompt landed at **32,768**, not 32,767 tokens; no claim is made that this exact length equals a previous prompt. Tokenized IDs, template hash, exact requests, responses, server logs and binary RID-bound full-logit captures are in `/data/sglang-hicache/gemma4/runs/20261025T103753Z-gemma-chat-quality/`.

## Results

| Task | BF16 KV | E5M2 KV | Matched same-history first Decode logits (BF16 vs E5M2) |
|---|---|---|---|
| Capital of France | `Paris`, stopped by 106 | `Paris`, stopped by 106 | prompt IDs/position equal; max/mean abs 1.7388/0.2842, RMSE .3562, rel-L2 .08226; greedy equal (106), Top-10 differs |
| 2+2 | `4`, stopped by 106 | `4`, stopped by 106 | max/mean abs 1.9622/.2912, RMSE .3648, rel-L2 .08016; greedy equal (106), Top-10 differs |
| Needle at 16K | exact `ZXQ-16384-ALPHA`, stopped by 106 | exact `ZXQ-16384-ALPHA`, stopped by 106 | max/mean abs .4708/.08689, RMSE .1102, rel-L2 .01046; greedy equal (`Q`), Top-10 differs |
| Needle at 32K | exact `ZXQ-32767-ALPHA`, stopped by 106 | exact `ZXQ-32767-ALPHA`, stopped by 106 | actual prompt length 32,768; max/mean abs .4953/.09686, RMSE .1216, rel-L2 .01193; greedy and Top-10 equal (`Q`) |

All answer token sequences matched their objective answer prefixes exactly in both modes. Each request produced real graph-backed Decode captures; long tasks captured 11 steps each. Capture metadata confirms requested pool dtypes `torch.bfloat16` and `torch.float8_e5m2`, actual positions, request IDs, and graph replay. Exact raw task/logit comparison artifacts are retained externally and not combined across different request histories.

## Interpretation

The earlier 16K/32K “needle failures” were not valid evidence of model capability: their raw user-style task prompts were not wrapped in the official Gemma 4 chat template, generation was forced to continue for a fixed 16 tokens while ignoring normal EOS, and the needle was at the end rather than in a natural long-context task position. On properly templated requests both cache modes return all four exact answers and terminate on the official turn-end token. Thus this task set provides no observed task-level FP8 quality loss; it does show first-step full-logit perturbations, Top-10 changes on three tasks, and greedy divergence remains possible near sensitive decisions. These four narrow synthetic tasks do not establish broad task-quality equivalence or general model capability. They do not resolve the independent frozen BF16/HF numerical FAILED guard or qualify E5M2 cache semantics. No tolerance or model math changed; no production code changed.

G1 remains ACTIVE / NOT ACCEPTED pending the unresolved numerical correctness contract and owner disposition. Existing service, graph parity, `.94`, C16 and Prefill qualifications are reused, not repeated. GPU returned to 1 MiB / 0% and exclusive lock was released.
