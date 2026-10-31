# Gemma4 RTX3090 real-batch percentile closure

## Goal
Complete percentile and graph-replay reporting for the existing validated c16/c24/c32 Radix 8K GPU run, reusing archived artifacts only.

## Scope and constraints
Use only `/data/sglang-hicache/gemma4/runs/20261031T145717Z-radix8k-prefix-benchmark/`; no GPU rerun, GSM8K, unrelated tests, product-path changes, worktree cleanup, or unrelated staging. Preserve G1 FAILED / NOT ACCEPTED. Do not claim graph replay shapes beyond Scheduler batches, CUDA Event batch sizes, and successful exact-size graph captures evidenced in the archive.

## Completion
Report measured-round GPU Decode Forward per-step P50/P95; request TPOT, TTFT, E2E P50/P95; actual scheduler and event batch distributions; exact graph bucket/padding relationship; sampled peak/remaining memory. State timing scope, sample counts, and limits. Validate calculations from raw records/logs, update the result/plan, and selectively commit/push owned report/parser/control files with remote SHA verification.