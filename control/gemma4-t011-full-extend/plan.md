# T011 Full Attention Extend plan

Status: DONE — authorized Forward-level plan-reuse continuation measured and closed; production source restored.

## Established results

1. **Native FP8 FA2 is unsupported on SM86.** FlashInfer 0.6.17 refuses one-byte large-head FA2 on RTX 3090; no architecture-gate override was made.
2. **Runtime geometry:** Gemma4 Full `head_dim=512`, Q/KV heads 8/2; SWA is 256.
3. **Operator-level BF16 Ragged qualification passed.** Across tested shapes, complete isolated path improved 27–48%, with FP32-oracle error around 1e-5, 112 MiB prefix at the qualified long shape, and log2 LSE preserved through merge. Evidence: `runs/T011-BF16-RAGGED-QUALIFICATION.md`.
4. **Forward-level plan-reuse continuation passed its real 42-layer extend gate.** Plans built once from host lengths; three-request ragged backend check passed all seven Full layers, preserved plan identity, and reused owner 23 for Shared-KV consumers. Real multi-request complete-Forward extend fell from 166.55 to 140.29 ms/1k prefill tokens (**−15.8%**, ≥10% gate passed). Component event aggregates: plan 178.5 ms, gather/cast 238.8 ms, prefix attention 15.881 s, extend attention 3.792 s, merge 249.8 ms (192 forwards; stride 1).
5. **C-8 L1-only keep gate failed.** Same-source control: 661.27 TPS, extend 168.76 s, decode 138.70 s. Candidate repeats: 672.90 and 672.15 TPS (+1.76%, +1.65%; mean +1.71%), extend 162.12 and 162.17 s (~−3.9%), decode 139.46 and 139.74 s. All scored runs completed 800/800 with zero failed requests. The required stable ≥5% net TPS gain was not achieved.
6. Two earlier candidate C-8 attempts OOMed while retaining all four owners' BF16 prefixes. The implementation then bounded residency to one owner, passed its plan/correctness check, and completed the two scored candidate repeats at the 128 MiB hard prefix ceiling. This did not change the throughput decision.

## Decision

**Candidate closed and reverted.** The complete-Forward gate alone is insufficient: the explicitly required C-8 L1-only net gate failed. Production `python/` is restored to frozen source `a76206a5fb`. No Decode, SWA, Marlin, KV capacity, quantization, scheduler, or cache-tier behavior was changed. Candidate module, scripts, and check outputs are retained under `runs/archive/` and `runs/20261127T-fwdplan-r1/` for evidence only.

Full continuation report: `runs/T011-FORWARD-PLAN-REUSE-QUALIFICATION.md`. Prior operator/native-FA2 reports remain valid for their own scoped results. The deliberately untracked `T011-ATTENTION-REVIEW.md` was left untouched. No T011 frontier entry remains.

## Remaining

None. Any further FA2 investigation requires new scope; this candidate is not production-enabled.
