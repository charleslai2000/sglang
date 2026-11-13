# Layer5 RoPE diagnosis — 2026-11-09

## Finding

The frozen QUASAR GGUF's `rope_freqs.weight` encodes 64 active angles out of 256 for full-attention head dimension 512 (partial factor 0.25). The old `Gemma4GGUFTextConfig.from_gguf()` defaulted to factor 1.0. Independent same-input Layer5 replay showed that factor 1.0 tracks SGLang Q/K RoPE while 0.25 tracks pinned llama.cpp; the pre-fix runtime therefore disagreed with the GGUF's encoded RoPE semantics.

Implemented `_infer_gemma4_partial_rotary_factor()` in `python/sglang/srt/configs/gemma4_gguf.py`. It validates the expected 1.0-prefix / 1e30-identity mask and derives the active fraction. Eight unit tests pass. The direct config reports `Gemma4RotaryEmbedding(... rope_angles=64, nope_angles=192 ...)`.

A real locked GPU BF16 doc24 run using production A8/MMQ dispatch completed, prompt hash `226c3a0a...a1235`, prompt length 1104, output token 1637 (`" If"`). The dispatch trace records `mmq_a8` for the 1104-row QKV EXTEND. At Layer5 position 1103, Q/K projections and Q/K normed inputs are unchanged from the default-factor run, while Q/K RoPE outputs change (relative changes 0.7984 / 0.8820); attention output changes by relative 0.6706 and post-attention norm by 0.4308. Against a newly regenerated callback capture from pinned llama.cpp revision `b49650adb31f2e49a0d76113aeb1792134fd8413`, factor-0.25 SGLang Layer5 Q/K normed and RoPE tensors are close (relative L2 Q 0.0188, K 0.0205); post-attention norm relative L2 is 0.0200. The compared input boundary is close but not identical (relative L2 0.0215), so this is a component diagnostic, not an identical-trajectory proof. Default factor 1.0 had Q/K RoPE relative errors about 0.799 / 0.882 against the pinned llama capture.

## Bounded quality intervention

Ran the frozen 14-prompt IDs against BF16 current HEAD-shadow SGLang with the corrected config, same seed and generation settings as the archived HEAD-shadow arm. All prompt ID hashes match. Correct count increased from 2/14 (docs 6,18) to 9/14 (docs 0,1,3,5,6,18,20,39,47); first-token IDs match the old arm on only 5/14. The corrected run had zero 512-token cap hits or repetition-flagged outputs; all 14 stopped on `Question:`. Raw result: `/data/sglang-hicache/g2-quasar-runs/20261107T-g2-first-logits/g2-rope-fixed-quality14-20261109-results.json`; run log and GPU-after record share the same directory.

This is controlled intervention evidence that the RoPE config defect materially contributes to the current HEAD-shadow quality failure; it is not a random/full GSM8K estimate, nor a reproduction of the historical private-overlay service. The 14-item result is not full production qualification.

## Scope and disposition

Quality remains **NO-GO** and E5M2 remains **NOT ACCEPTED**. Do not treat this diagnostic change as production-accepted or use it to resume performance/capacity work. Full 1,319-question evaluation is outside this investigation's agreed scope and was not run. Existing shared worktree changes were preserved; no commit or push was made.

GPU lock `/tmp/f1-r16b-gpu-exclusive.lock` was held for GPU runs. Afterward the server process was gone and `nvidia-smi` reported 1 MiB used, 0% utilization. The earlier default/fixed component runs also recorded GPU-after 1 MiB / 0%; the callback reference was CPU-only.
