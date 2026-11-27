# T011 — Full Attention Extend Optimization

## Goal
At frozen production baseline `c102ccbc5cfd17b510f896b23107204daf5ed0d7` (production source `a76206a5fb`), improve only Gemma4 Full Attention Extend for head_dim=512 by reusing FlashInfer FA2's Paged Prefix + Ragged Extend + MergeState implementation. The user has fixed this technical approach; this work does not authorize an alternative algorithm or wholesale backend replacement.

## Scope
- Use existing Nsight trace and frozen source to identify the `(1,8,128)` hotspot's actual layer ownership, head dimension, Triton BLOCK_M/BLOCK_N, and context geometry; do not repeat full profiling.
- First qualify the isolated FA2 operator path on SM86 with BF16 Q, FP8 E5M2 prefix KV, head_dim 512, page_size 1, actual GQA geometry, including plan + attention + merge costs, for new-token/prefix lengths 1024/7168, 4096/12288, and 4096/28672, against complete current Triton Extend.
- Only if supported and showing clear net benefit, integrate into existing Full Extend using its KV pool, metadata and owner mapping; preserve FP8 prefix plus descale, original-precision causal new K/V, Shared-KV source/numerical semantics, log-base correctness, and empty-prefix behavior.
- Verify Attention outputs and LSE against an FP32 oracle with no new numerical regression; then run one original C-8 L1-only acceptance and validate full three-tier cache restore.

## Constraints
- No Decode, Marlin, SWA, KV capacity, quantization-format, scheduling or cache-policy changes.
- Do not develop a replacement kernel if this candidate is unsupported or lacks clear net benefit; stop the candidate and record evidence.
- Acquire `/tmp/f1-r16b-gpu-exclusive.lock` before GPU workloads; use bounded, durable runs and cleanup.
- Preserve unrelated work; commit/push only authorized T011 changes and control/report artifacts.

## Completion
Either (a) candidate falsified/unsupported and stopped with an evidence-backed report and no production change, or (b) optimized Full head_dim=512 Extend integrated and correctness-verified, original C-8 L1-only acceptance and full three-tier restore completed. Report operator speedups, actual memory overhead, end-to-end effect, and source SHA. Update Goal/Plan/Task/frontier and push the applicable commit(s).
