# F1 — Falcon GPTQ / 3090 / HiCache L3 Performance

## Goal
在 `3090-24g-hicache` 工作线上，验收 Falcon-H1-7B GPTQ-Int4 的 GPU/Host/Disk 三级缓存集成，并建立高并发、可复现的性能基线，确认 L3 的收益边界及瓶颈。

## Frozen target
- Model: `tiiuae/Falcon-H1-7B-Instruct-GPTQ-Int4`
- Revision: `52036ae497a2c0c253e17f98cc8652f2f7082ae3`
- Checkpoint: `/data/models/Falcon-H1-7B-Instruct-GPTQ-Int4`
- Hardware target: single RTX 3090 24GB.
- Runtime: current `3090-24g-hicache` branch; retain GPTQ, Mamba and accepted HiCache L2 implementation. L3 backend: existing `ExtentFileBackend`.
- Keep `3090-24g-hicache` and `3090-24g-opt` independent until an explicitly planned final integration. Borrow from opt only by reviewing clean committed diffs/hunks; never modify or bulk-import its dirty worktree.

## Scope
- Reconcile current runtime identities against historical accepted Falcon commits/reports; establish minimum delta for L3. Reuse valid Falcon GPTQ and L2 evidence; do not repeat broad certification unnecessarily.
- Validate FULL/KV and MAMBA L3 write, device/host eviction, rematch, storage prefetch and restore, with byte/state correctness, atomic visibility, lifecycle, partial-prefetch/cancel and failure fallback. Distinguish storage existence/logical hits from actual bytes read and committed restoration.
- Audit Unified Cache host-anchor and L3 partial-prefetch/cancel paths; exercise deterministic race/failure seams and recoverable fallback.
- Implement reproducible workload A (historical B5-like low-host-reuse control), B (high-host-reuse multi-session dormancy/revisit), C (working set beyond L2 capacity with L3 reuse), plus constructional per-tier forced-eviction tests. Each declares token lengths, prefix sharing, sessions, revisit interval, and tier capacities.
- Compare GPU-only, GPU+Host, and GPU+Host+Extent under identical useful request traces; cold and warm separately. Count actual tier hits, restored bytes/states, cache occupancy/evictions, and physical disk reads versus Linux page-cache hits using verifiable I/O evidence.
- Run multi-level concurrency load profiles with stable sampling and repeated measurements; capture prefill/decode/aggregate rates separately, req/s, TTFT/TPOT/E2E p50/p95, effective concurrency, error/OOM/cancel rate, memory and disk metrics, and cache scheduling/backup/restore overhead.
- Use fixed seed and greedy reference requests; validate outputs after L2/L3 restore and state consistency, not merely HTTP success. Profile material regressions with Nsight or suitable CPU/I/O tools. Only fix correctness defects and clearly localized low-risk performance defects.

## Constraints and safety
- Preserve model weights and unrelated GPU workloads. Do not reset/clean/change the sibling opt checkout.
- No GPU performance acceptance without an available, coordinated RTX 3090 window and a fresh no-interference check. Do not fabricate or infer GPU results from old reports.
- All disk-cache experiments must use a new, unique, isolated extent storage directory with capacity/free-space checks; never clear/reuse production or historical cache data.
- Reuse accepted Falcon L2 evidence and old B5 trace as the control where trace artifacts permit; do not rerun that low-host-reuse comparison without a concrete need.
- Keep changes narrowly scoped, reversible, tested, and committed on the hicache line. Do not merge branches during this Goal.

## Completion / acceptance
- Falcon GPTQ remains stable; historical L2 correctness conclusions do not regress under current bytes.
- Actual Falcon FULL/KV and MAMBA L3 data writes, evictions, storage reads and successful restores are evidenced end-to-end. Logical existence hits alone do not count.
- Atomicity/lifecycle, partial restore, cancel, error fallback, and cache state correctness pass; no stale data, use-after-free, deadlock, or unrecoverable service failure.
- All three workload classes complete fair GPU-only/L2/L2+L3 comparison with reproducible scripts, configs, commit identity and raw outputs.
- Concurrency/throughput/latency curves and the highest effective throughput region are reported with separate prefill/decode/input/output metrics.
- State when L3 helps, is neutral, or hurts for the tested working sets, including physical-I/O vs page-cache evidence. No performance benefit is required for PASS; a sound negative result is acceptable.
- Final phase report classifies each required item PASS / FAIL / BLOCKED / NOT_RUN and records residual risks and next optimization hypotheses.

## Stop/escalation
Continue routine code, interface, test and diagnosable performance work autonomously. Stop only for frozen architecture/ownership decisions, unavailable indispensable external APIs/resources, or unresolved hard blockers. If no safe shared GPU window exists, do not run GPU acceptance; complete safe CPU/static work and report GPU portions BLOCKED/NOT_RUN with minimum evidence.
