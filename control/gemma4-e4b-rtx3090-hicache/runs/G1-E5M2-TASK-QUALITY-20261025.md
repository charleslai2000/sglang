# E5M2 task-quality comparison — 2026-10-25

## Method

RTX 3090 runs under `/tmp/f1-r16b-gpu-exclusive.lock`; same pinned W4A16 checkpoint, one request at a time, no radix reuse, temperature zero, 16 generated tokens. Each forward captured full pre-sampling logits and actual graph-replay flag. Revision `6cd26aaa2357fb2bad8c51699a7558a4d1a965bb`; weights SHA-256 `19d89d2a4b3e401a3eae75ec08ab112810421a036c91d8c8226b686be7fe0c5d`.

Run/artifacts: `/data/sglang-hicache/gemma4/runs/20261025T094802Z-e5m2-task-quality-v3/quality-summary.json`. Tasks: short factual completion (5 tokens), arithmetic (`2+2`) (10 tokens), synthetic factual needle retrieval with exact 16,384 and 32,767 token prompts. Whole request IDs and tails verified; query was at prompt end. BF16 and E5M2 each have 16 actual decode captures per task; Graph replay flag true for all. The model HF guard remains FAILED independently; this is a relative service task comparison, not oracle acceptance.

## Results

- Short factual and arithmetic: BF16/E5M2 output IDs and visible answers match. The short fact prompt produces repetitive `France is` continuation; arithmetic produces `4.` then repetitive filler. Correctness of these narrow answers does not establish general quality.
- 16,384-token needle `ZXQ-16384-ALPHA`: both modes fail to answer; both continue the repeated filler sentence. First-step greedy is the same token (818). E5M2 vs BF16 full-logit metrics at the identical prompt/history: max abs `1.7418`, mean abs `.2851`, RMSE `.3635`, rel-L2 `.08355`; Top-10 differs. Target first answer token ranks 102 (BF16) and 263 (E5M2).
- 32,767-token needle `ZXQ-32767-ALPHA`: both modes fail to answer; both repeat the terminal `Query: archive ID?` text. First-step greedy is identical (7990). Same-history full-logit metrics: max abs `1.8169`, mean abs `.3076`, RMSE `.3887`, rel-L2 `.07693`; Top-10 differs. Target first answer token ranks 6,762 (BF16) and 6,111 (E5M2).
- Separate real 32,767-token frozen-random prompt, 32 generated tokens: both arms completed with 32 actual Decode Graph replays. The full report is `/data/sglang-hicache/gemma4/runs/20261025T082332Z-e5m2-long-quality/quality-summary.json`. At step 0, same RID-local input token/position history: E5M2 vs BF16 max/mean/RMSE/rel-L2 `1.0122/.17363/.21901/.02706`; greedy differs `236803` vs `236805`, Top-10 differs. The BF16 top candidates are tied at printed BF16 precision; this is a near-tie-sensitive divergence. Generated outputs differ starting token index 1; later cross-arm logits are not comparable because histories differ. BF16 generated repetitive numeric text; E5M2 generated a different multilingual/list-like continuation. One arbitrary synthetic continuation is not a benchmark of general quality.

## Interpretation and remaining contract

Observed first-step perturbations alone do not prove a Shared-KV/SWA scale or cache semantic defect. The fixed N510–514 evidence already shows E5M2/BF16 numeric deltas and an N513 greedy change; Graph/Eager equality remains a separate execution-parity result. Conversely, passing a couple of short answers is insufficient to establish FP8 quality. The two synthetic long-retrieval prompts fail even under BF16, so they cannot isolate FP8-specific capability loss. No formal thresholds or model math were changed. No proven FP8 implementation defect found in this task set. G1 remains ACTIVE / NOT ACCEPTED; a task-relevant, frozen E5M2-vs-BF16 quality contract and owner decision remain necessary, in addition to the unresolved BF16/HF numerical FAILED guard.
