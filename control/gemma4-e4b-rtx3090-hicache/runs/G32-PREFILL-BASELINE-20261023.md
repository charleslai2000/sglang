# Gemma4 RTX3090 G32 Prefill baseline — 2026-10-23

## Run and method
Real GPU-exclusive RTX3090 service, pinned official `google/gemma-4-E4B-it-qat-w4a16-ct` snapshot (revision `6cd26aaa2357fb2bad8c51699a7558a4d1a965bb`, safetensors SHA-256 `19d89d2a4b3e401a3eae75ec08ab112810421a036c91d8c8226b686be7fe0c5d`), BF16 KV, Triton attention, radix cache disabled, batch-1 fixed-ID Prefills, one generated token. One frozen 32,768-ID seeded stream is sliced for each length; every accepted request reports `cached_tokens=0`. Prefill CUDA Graph is disabled by this multimodal architecture; these are real eager Prefills.

Three repeated requests per length were run in `/data/sglang-hicache/gemma4/runs/20261023T075324Z-g32-prefill-baseline/`; logs and frozen IDs are in that directory. The original one-shot run is retained at `20261023T074418Z-g32-prefill-baseline/`. GPU memory was sampled every 500 ms during the repeated run (195 samples): peak total device use was 12,305 MiB, max utilization 100%, sample mean 41.6%; after shutdown GPU returned to 0%, 1 MiB. This is sampled whole-device memory, not a per-process peak ledger.

| Prompt tokens | Client-wall input tok/s, 3 reps | Mean ± sample SD | Server E2E s (mean; min–max) | Accepted |
|---:|---|---:|---:|:---:|
| 1,024 | 4,624.5 / 6,023.6 / 6,026.8 | 5,558.3 ± 808.7 | .1705 (.1672–.1768) | yes |
| 4,096 | 5,903.6 / 5,959.3 / 5,944.3 | 5,935.8 ± 28.8 | .6872 (.6846–.6910) | yes |
| 16,384 | 4,502.4 / 4,508.9 / 4,526.7 | 4,512.7 ± 12.6 | 3.6265 (3.6154–3.6345) | yes |
| 32,761 | 3,590.3 / 3,584.0 / 3,493.2 | 3,555.8 ± 54.3 | 9.2089 (9.1191–9.3720) | yes |

The exact 32,768-token request plus one generated token was rejected before execution; HTTP error reported maximum input 32,762. 32,761 was accepted, so this measures a real near-32K prompt, not exactly 32,768. These results establish repeat measurements under one config and provide a preliminary baseline, not final performance acceptance. 1K has a cold/first-request outlier; compare warm reps with care. The CUDA prefill graph was off; no Graph performance is inferred.

## Interpretation / follow-up
The run establishes genuine 1K/4K/16K/near-32K service Prefill throughput points. They are single samples under one startup/config and must not be presented as stable performance estimates or acceptance. Peak allocated memory/usable Full-vs-SWA KV, repeated trials, TTFT distribution, C1/C4/C8/C16 decode performance, and correctness against HF at long contexts remain unmeasured/unaccepted. The currently failing frozen N512/N514 BF16 oracle guards also remain unresolved; the numerical debug run must continue separately. G1 remains ACTIVE / NOT ACCEPTED.