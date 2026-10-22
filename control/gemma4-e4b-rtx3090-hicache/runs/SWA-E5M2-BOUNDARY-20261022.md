# Gemma4 E5M2 vs BF16 around SWA window — 2026-10-22

Real matched raw-token completions through the actual SGLang service; E5M2 and BF16 used identical deterministic input token arrays, `temperature=0`, `max_tokens=1`, `--disable-radix-cache`, 4096 context/total-token budget, and independent Forward UUIDs. Same official checkpoint SHA as the pinned BF16 Oracle; E5M2 KV physically allocated in both full and SWA pools, and decode CUDA Graph bs1 capture completed in startup logs. Artifacts: `/data/sglang-hicache/gemma4/runs/20261022T052139Z-e5m2-swa-boundary/`, per-length requests/responses/full capture, and `summary.json`.

Compared the final prefill logits row (vocab 262144) E5M2 against BF16 at prompt lengths 510, 511, 512, 513, 514:

| tokens | max abs | mean abs | RMSE | relative L2 | greedy IDs equal |
|---:|---:|---:|---:|---:|:---:|
| 510 | 1.27176 | 0.195739 | 0.246427 | 0.06298 | yes |
| 511 | 1.60192 | 0.215992 | 0.270837 | 0.07690 | yes |
| 512 | 1.54066 | 0.253036 | 0.318876 | 0.10202 | yes |
| 513 | 1.56911 | 0.213881 | 0.271078 | 0.08479 | **no** |
| 514 | 1.66400 | 0.363550 | 0.424178 | 0.09837 | yes |

Actual greedy divergence at length 513: E5M2 `238247`, BF16 `204064`. Thus the prompt crossing `SWA 512` did **not** pass the greedy-equivalence check; full-logit E5M2 errors are not monotonic but remain elevated compared with the short 8-token result. This is a meaningful observed quality difference, not proof of a specific Shared-KV scale defect: the short-prompt control at 510 tokens also has max abs 1.27, and different random contexts change logits. No component-local diagnosis is established yet. Treat SWA E5M2 numeric boundary as **FAIL/needs investigation**, not a PASS; BF16 reference consistency at these lengths and subsequent decode/token drift are separate remaining tests.

The earlier attempt at `/data/sglang-hicache/gemma4/runs/20261022T051559Z-e5m2-swa-boundary/` is invalid for the requested experiment because RadixCache reused 510 cached tokens and the later call captured only one suffix token; its length-510 comparison is not a full matched prefix. The corrected no-radix-cache run above is the authoritative boundary evidence. No conclusion about CUDA Graph replay follows from graph capture at startup.
