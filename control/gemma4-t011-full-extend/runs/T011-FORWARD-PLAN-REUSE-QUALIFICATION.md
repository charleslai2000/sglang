# T011 — Forward-level FA2 plan reuse qualification

**Outcome: CLOSED / REVERTED.** The implementation met the complete-Forward extend gate, but failed the required C-8 L1-only net-throughput gate. Production code is restored to frozen source `a76206a5fb`; the candidate is archived only.

## Scope and method

Freeze/starting commit: `371521fc990513fadd879e11c27d130eca4e65e7`. Candidate: FlashInfer 0.6.17 BF16 FA2 Ragged Prefix + causal Ragged Extend + `merge_state`, with plans hoisted into `init_forward_metadata` from host lengths. Shared-KV layers reuse the owner pool buffers. No Decode, SWA, Marlin, KV-capacity, quantization, scheduler, or cache-policy changes were made.

The plan check used a three-request ragged batch (prefix lengths `[1024,2048,512]`, extend `[700,300,1500]`) on the real backend methods and compared all seven Full layers against production Triton. Plan identity remained unchanged across layers; all seven engaged; max output difference was `9.16e-4` for the synthetic FP8-pool comparison; owner 23 was reused by shared consumers; over-budget inputs fell back. The check also exposed and fixed two harness/candidate issues: total prefix must be the sum of per-request lengths, and the Triton reference must convert shared-layer FP8 pool rows to compute dtype.

The real-Forward benchmark used the frozen C-8 launch arguments with HiCache disabled, 12 concurrent long prompts, and 3 rounds. It exercised complete 42-layer model forwards with multiple requests and measured category=extend device-forward time.

## Complete-Forward gate: PASS

| cell | extend device time | prefill tokens | extend ms / 1k tokens | requests |
|---|---:|---:|---:|---:|
| candidate off | 124.260 s | 746,068 | 166.55 | 36/36 |
| candidate on | 104.669 s | 746,068 | 140.29 | 36/36 |

Reduction: **15.8%**, passing the ≥10% gate. Candidate component timings (192 forwards observed; event sample stride 1) were plan 178.5 ms, gather/cast 238.8 ms, prefix attention 15.881 s, extend attention 3.792 s, merge 249.8 ms. These component figures are sampled-path aggregates and are not a replacement for end-to-end timing.

## C-8 L1-only gate: FAIL

Official C-8 L1-only protocol, same current candidate source and baseline argv, 40 clients × 20 rounds, 1024 input / 256 output, Poisson seed 42, chunk 4096, 800 requests per cell. One control and two candidate repetitions all completed with zero failed requests.

| cell | TPS | extend forward s | decode forward s | bench s | TTFT s | ITL s |
|---|---:|---:|---:|---:|---:|---:|
| off control | 661.27 | 168.76 | 138.70 | 309.71 | 3.634 | 0.0405 |
| on r1 | 672.90 | 162.12 | 139.46 | 304.35 | 3.628 | 0.0398 |
| on r2 | 672.15 | 162.17 | 139.74 | see run artifact | 3.682 | 0.0398 |

Candidate TPS gains were **+1.76%** and **+1.65%**; mean **+1.71%**, below the required **≥5% stable net gain**. Extend time improved by about **3.9%**, while decode was effectively unchanged. Therefore no production integration is retained and the FA2 direction is closed under the user-specified decision rule.

Run artifacts are under `/data/sglang-hicache/gemma4/runs/20261127T-t011-fwd-{off,on}` and `/data/sglang-hicache/gemma4/runs/20261127T-t011-l1only-{off2,on2,on3}`. The on2 timing/counter record shows 192 candidate plans, 25 no-prefix skips, zero over-budget skips at the 128 MiB budget, maximum BF16 prefix 128 MiB, 764 owner conversions and 573 shared reuses. The two earlier C-8 candidate attempts OOMed under the frozen memory configuration; root cause was retaining all four owners' BF16 prefixes simultaneously. The corrected candidate bounded residency to one owner and completed the scored runs, but did not meet the throughput gate. This memory fix does not change the final decision.

## Final state

`python/sglang/srt/layers/attention/triton_backend.py` was restored; no candidate module remains under `python/`. The forward-plan candidate module and test/benchmark harnesses are archived in `runs/archive/` and `runs/`. The prior attention-review file remains untracked and untouched. GPU is idle, port 31401 is clear, and the exclusive GPU lock is free.

This follow-up does not reopen the previously completed task; it records its authorized continuation and final result. No remaining work. Any future attempt requires a new scope and cannot be inferred from this archived candidate.
