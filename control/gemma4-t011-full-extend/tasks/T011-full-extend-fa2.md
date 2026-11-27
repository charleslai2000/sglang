# T011 — Full Attention Extend (head_dim=512)

Status: DONE

## Work area
`python/sglang/srt/layers/attention/`, `control/gemma4-t011-full-extend/`, durable run artifacts under `/data/sglang-hicache/gemma4/runs/`.

## Objective
At frozen production source `a76206a5fbd65b81ddbb470ac8088a46cf78697a`, qualify existing FlashInfer FA2 alternatives for Gemma4 Full Extend only (head_dim 512, GQA 8/2). No replacement kernel or architecture-limit override. The BF16 ragged candidate must meet the complete-Forward gate (≥10% extend reduction), then the official C-8 L1-only gate (≥5% stable net TPS gain); otherwise revert.

## Inputs
Frozen source `a76206a5fb`, FlashInfer v0.6.17, RTX 3090 SM86; earlier attention review and T011 operator qualification reports; T011 forward-plan-reuse continuation from commit `371521fc99`.

## Completion
Either a correctness-preserving production integration passes both measured gates, or the candidate is closed with source restored, evidence recorded, and no candidate production code retained.

## Result
DONE — both alternatives closed; production source unchanged.

- Native one-byte FP8 FA2 Paged Prefix is unsupported on SM86 in FlashInfer 0.6.17 (`No supported CUDA architectures found for major versions [10, 11, 12]`). No override.
- BF16 Ragged operator work passed isolated qualification (27–48% reductions), but its first per-layer integration regressed C-8 (650.06→561.55 TPS, extend +29.2%) and was reverted.
- Authorized forward-level plan reuse then passed the real complete-Forward extend gate: 166.55→140.29 ms/1k prefill tokens (−15.8%). The plan used host lengths once per forward, and the backend check covered all seven Full layers and Shared-KV owner reuse.
- C-8 L1-only same-source control was 661.27 TPS. Two candidate repeats were 672.90 and 672.15 TPS (+1.76%, +1.65%; mean +1.71%), with extend ~3.9% lower and decode unchanged. All scored cells completed 800/800 with zero failures. Required ≥5% stable net TPS gate failed.
- Early C-8 candidate attempts OOMed because four owner BF16 prefixes accumulated; a one-owner eviction fix allowed the scored runs at the 128 MiB ceiling. This did not meet the performance gate.

Production `python/` was restored to frozen `a76206a5fb`; no candidate environment gate or module remains in production. The archived forward-plan candidate and harnesses are under `runs/archive/`; final evidence is `runs/T011-FORWARD-PLAN-REUSE-QUALIFICATION.md`. GPU idle and lock released.

## Remaining
None. Any further investigation requires a new scope.
