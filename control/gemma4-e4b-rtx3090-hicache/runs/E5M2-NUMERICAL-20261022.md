# E5M2 single-prefill numerical result — 2026-10-22

Real service run: `/data/sglang-hicache/gemma4/runs/20261022T052000Z-e5m2-full-logits/`; model revision `6cd26aaa2357fb2bad8c51699a7558a4d1a965bb`, `model.safetensors` SHA-256 `19d89d2a4b3e401a3eae75ec08ab112810421a036c91d8c8226b686be7fe0c5d`, KV dtype `fp8_e5m2`, actual attention backend Triton. Request RID `4a8ef67531ba4b67bd621d44cf2765a4`, Forward UUID `b1dbeb59874944149cd36204708300f9`, IDs `[6974,886,2822,13315,1003,506,7217,236761]`, positions 1–8, no cached prefix, HTTP response generated token 108.

Full 262,144-coordinate last-prefill logits compared directly against the audited BF16 Transformers Oracle (SHA-256 `6b7965bde08636abc199637917aba7e66c05c9078b13741f28c15127cdde1e66`) and the previously frozen BF16 output. E5M2 vs BF16: max_abs `0.9588699341`, mean_abs `0.1843590140`, RMSE `0.2262995094`, relative L2 `0.0404376239`; top-10 ID set exactly equal; greedy `108 == 108`. BF16 reference-vs-Oracle max_abs `.4347810745`, mean_abs `.0604655854`, relL2 `.0136484802`.

Because there was no separately frozen FP8 threshold for this run, diagnostic gates were declared before measuring (`max_abs<=8`, `mean_abs<=.5`, exact top10, exact greedy). It passes those gates. This establishes a **single-prompt E5M2 full-vector diagnostic PASS against BF16**, not E5M2 G1 acceptance, long-context/decode drift, scale/SWA boundary correctness, concurrency, graph replay, or service stability.

Raw full numerical report and response are in the run directory above. E5M2 service was stopped after the request; GPU returned to 1 MiB used.
