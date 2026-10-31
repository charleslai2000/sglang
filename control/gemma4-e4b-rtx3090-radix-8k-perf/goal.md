# Gemma4 RTX3090 Radix 7K-hit / 8K-context performance

## Goal
Measure BF16-KV W4A16 online service with exact 7,168-token Radix L1 prefix hit and 1,024-token new suffix, total 8,192-token prompt, 256 generated tokens; concurrency c1/2/4/8/16/24/32. Report cache verification, prefill timing boundary, decode TPS/TPOT, E2E and capacity.

## Constraints
Single RTX3090 TP1, Triton, decode CUDA Graph, Radix Cache ON; HiCache L2/L3 OFF. Greedy, max_running_requests=16, no production math/cache/scheduler/performance-path changes. Reuse current worktree and existing service/metrics; preserve unrelated dirty/untracked files. All GPU work requires `/tmp/f1-r16b-gpu-exclusive.lock`; do not override another holder.

## Completion
Each accepted run must have Scheduler/Cache-derived exact prefix hit=7168 and newly-prefilled=1024, full prompt=8192; record request/correlation IDs and actual decode/cache position evidence. At least warmup plus three valid trials per supported concurrency; invalid hit lengths excluded. Report separately measurable prefill, decode-only aggregate TPS, total Output TPS, TPOT/E2E, active GPU batch/Graph and GPU peak memory. State unmeasurable timing boundaries explicitly; archive source/config/artifact hashes and replay scripts; selective commit/push and verify remote SHA. G1 remains FAILED / NOT ACCEPTED.
