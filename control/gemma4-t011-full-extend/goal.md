# T011 — Full Attention Extend Optimization

## Goal
At frozen production baseline `c102ccbc5cfd17b510f896b23107204daf5ed0d7` (production source `a76206a5fb`), improve only Gemma4 Full Attention Extend for head_dim=512 by reusing existing FlashInfer v0.6.17 BF16 large-head Ragged Attention + merge_state. The prior native FP8 FA2 paged candidate was closed as unsupported on SM86. The user now authorizes an explicitly bounded FP8-pool gather/dequantize-to-temporary-BF16 prefix path; no alternative attention algorithm or wholesale backend replacement is authorized.

## Scope
- Use existing Nsight trace and frozen source to identify the `(1,8,128)` hotspot's actual layer ownership, head dimension, Triton BLOCK_M/BLOCK_N, and context geometry; do not repeat full profiling.
- Close the native FP8 FA2 candidate. First qualify existing FlashInfer v0.6.17 BF16 large-head Ragged Attention using gathered/dequantized BF16 prefix from the FP8 pool, paired noncausal Prefix and causal Extend ragged calls, and merge_state. First shape: 4096 new + 28672 prefix, Full head_dim=512, GQA 8/2. Include gather, conversion, both plans, both attentions, merge, synchronization, workspace and all temporary allocations against complete current Triton Extend. Require at least 20% net time reduction before expanding to other shapes.
- BF16 temporary prefix allocation is bounded to 128 MiB, with no resident BF16 cache and no FP8 pool reduction. Count workspace and all extra memory. Preserve FP8-pool scale/descale semantics, original-precision causal new K/V, Shared-KV ownership/numerics, softcap, LSE merge semantics and empty-prefix behavior. Only if supported, ≥20% faster end-to-end for the first shape, and passing FP32 oracle, integrate Full Extend only with Triton fallback.
- Verify Attention outputs and LSE against an FP32 oracle with no new numerical regression; then run one original C-8 L1-only acceptance and validate full three-tier cache restore.

## Constraints
- No Decode, Marlin, SWA, KV capacity, quantization-format, scheduling or cache-policy changes.
- Do not develop a replacement kernel if this candidate is unsupported or lacks clear net benefit; stop the candidate and record evidence.
- Acquire `/tmp/f1-r16b-gpu-exclusive.lock` before GPU workloads; use bounded, durable runs and cleanup.
- Preserve unrelated work; commit/push only authorized T011 changes and control/report artifacts.

## Completion
Either (a) candidate stopped with an evidence-backed report and no production change, or (b) optimised Full head_dim=512 Extend integrated, correctness-verified, and passing the original C-8 L1-only acceptance plus full three-tier restore. Report only measured operator speedup, memory overhead, end-to-end effect and source SHA; update Goal/Plan/Task/frontier and push applicable commits.

## Outcome
Closed. Native FP8 FA2 was unsupported on SM86. The BF16 Ragged operator passed isolated qualification, but its first C-8 integration regressed (650.06 → 561.55 TPS, −13.6%) and was reverted. The authorized Forward-level plan-reuse continuation then passed the complete 42-layer extend gate (−15.8%), but failed the final C-8 L1-only gate: two candidate repeats gained only +1.76% and +1.65% TPS (mean +1.71%) versus 661.27 TPS control, below the required ≥5%; all scored cells were 800/800 with zero failures. Production source is restored to `a76206a5fb`. Reports: `runs/T011-BF16-RAGGED-QUALIFICATION.md` and `runs/T011-FORWARD-PLAN-REUSE-QUALIFICATION.md`.
