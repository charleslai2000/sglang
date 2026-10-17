# Queued Request Prefetch / Host-Ready Pipeline

## Goal
(T004, owner ruling 2026-10-17) On the sole `3090-24g-hicache` mainline, complete a trustworthy Falcon queued-prefetch workload and evaluate Ready Horizon (RH) under production Host capacity. Durable FULL KV+MAMBA prefixes may stage Extent L3→Host L2 ahead of admission and must be consumed without avoidable durable-prefix recompute. Prove ordinary FULL Host release is usable by a subsequent queued L3 request without requiring the exact just-evicted node to refill; existing Device/Host hits are valid and preferable to repeated disk reads. Distinguish prefetch completion, recoverable-prefix Host readiness, full-prompt/no-Prefill, admission, H2D ACK, first GPU execution and numerical correctness. Complete long greedy/multi-round/logits plus FULL KV/MAMBA state checks and at least three matched normal-capacity queue-prefetch ON/OFF pairs with honest tier, scheduler, disk/page-cache/physical-I/O and throughput reporting.

## Authority and constraints
- Work only in `/home/ubuntu/workspaces/3rdparty/sglang-hicache`, branch `3090-24g-hicache`, and its `control/`; no new branch/worktree.
- Preserve all pre-existing dirty/untracked work. Do not stage broadly, reset, clean, or mix unrelated/StreamingSession changes.
- Reuse current Scheduler, Ready Horizon, `UnifiedRadixCache`, CacheController, Extent backend, FULL+MAMBA restore path, and tier telemetry. No second cache/scheduler.
- Reuse historical design/contract/evidence under `.memory/phase2-hicache-design` and `rh-p1-durable-replay-eviction`; historical Qwen/3060 results are not Falcon/3090 acceptance.
- Preserve correctness gates and distinguish source hits, Host-ready, disk I/O/page cache, admission, H2D and actual GPU execution.
- GPU use is authorized for all work in this Goal. Hold `/tmp/f1-r16b-gpu-exclusive.lock` through every GPU workload; if unavailable, defer only that run and continue independent work.
- Only selectively commit verified changes; exclude unaccepted StreamingSession edits. Do not claim production acceptance without required technical review.

## Scope
1. Audit current branch, dirty ownership and exact-prefix fixture; correct token-stream/SHA/durable-key/FULL+MAMBA frontier checks and remove cross-run or false joins.
2. Reuse the existing exact-prefix T004 driver and telemetry; run distinct durable queued B/C/D with ordinary bounded allocator release and prove same-run FULL Host free → later queued L3 read → Host-ready → admission. Do not require same-target refill; accept L1/L2 valid hits. Do not create more drivers or expand pressure workload.
3. Join RID, recoverable prefix, Host-ready, H2D ACK, first GPU execution and Prefill. Audit partial-ready predicate and distinguish completed staging, recoverable-prefix readiness, and full prompt/no Prefill.
4. Complete frozen long greedy, multi-round, logits and FULL KV/MAMBA-state correctness comparison.
5. Immediately run at least three matched production-capacity queue-prefetch ON/OFF pairs. OFF disables only Queue Prefetch while retaining Demand L3 restore; RH-disabled eager enqueue is not OFF. Verify identical workload, real L3-resident prefixes, cache frontier, batch and GPU conditions. Measure READY/lead/stock, L3/GPU overlap and actual idle gaps, wasted prefetch, scheduler/rematch CPU, tier hits/saved Prefill/H2D, TTFT/TPOT/GPU TPS/output TPS/aggregate throughput and dispersion; separate Extent reads, OS page-cache and physical-device I/O.
6. Continue normal authorized implementation/debugging; hold existing GPU flock; preserve dirty/untracked work; no new worktree. Selectively commit/push validated T004 source/control evidence only after staged-diff review; exclude unaccepted StreamingSession changes.

## Completion
A reliable and reproducible Falcon fixture; same-run identity-correct queued L3→Host-ready→admission evidence after ordinary FULL Host capacity release (not necessarily the evicted identity); RID-linked H2D/GPU/Prefill consumption; passed long numerical/state correctness; at least three valid matched production-capacity Queue Prefetch ON/OFF pairs with requested metrics and honest I/O attribution; precise selective commits pushed to the authorized branch and exact local/remote source identities recorded. No performance benefit or numerical acceptance claim without corresponding evidence. Keep unresolved required metrics explicitly NOT_VERIFIED with concrete blockers.
