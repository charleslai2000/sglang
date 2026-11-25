# T007 — Eliminate Gemma4 HiCache performance loss

## Goal
Improve end-to-end performance of the existing Gemma4 Owner-only W4A16 / FP8 E5M2 KV service on RTX 3090, starting from accepted T006 configuration and fixed-budget cache/resource settings. T007 established the chunk=4096 comparison baseline but remains ACTIVE: its 132.724 tok/s is not accepted as the goal-level performance result. The active work recovers the completed L1-only benchmark result, compares L1-only/L1+L2/L1+L2+L3 on identical C8 workload and fixed GPU pools, attributes the dominant cache/scheduler loss, and applies evidence-backed in-contract fixes. A near-L1-only online throughput is the target direction; the prior 132.724 TPS is not acceptance.

## Scope
Reuse T006 C-8 results and existing profiler/telemetry patterns, including `device_timer.py`, `nvtx_utils.py`, metrics reporting, available Nsight Systems capture procedures, and `benchmark/hicache/bench_multiturn.py`. Inspect historical Gemma/Falcon profiler and convergence work where present. Preserve Owner-only FP8 KV, pool budgets, workload, and active L1/L2/L3 behavior. Make source/runtime provenance explicit. Continue inspect → measure → optimize → test/compare without procedural handoffs.

## Constraints
- No standalone certification or new profiling framework; restore/reuse existing DeviceTimer/FPM/NVTX and established Nsight Systems usage.
- Do not weaken workload, reduce offered load, disable cache tiers, replay historical WAL, or repeat already completed KV correctness qualifications.
- Separate actual uncached Prefill computation from logical input tokens and distinguish forward batch TPS from end-to-end throughput.
- Preserve all unrelated dirty/untracked work. Selectively commit/push only T007 changes.
- GPU is authorized for this goal; acquire `/tmp/f1-r16b-gpu-exclusive.lock`, check GPU/service/ports before use, bound all workload windows, and clean up owned process trees.
- Algorithmic scheduling or KV ownership changes are outside implicit authority and require a concrete decision; contract-preserving implementation/parameter fixes are allowed when evidence supports them.
- T008 baseline is commit `cfacaedeb3b1369c7a762f81d2a46751704321ea`, chunked prefill 4096. Preserve active cache tiers and Full/SWA capacity safeguards; do not shrink GPU KV to manufacture L3 pressure or reopen T006 correctness qualification.

## Completion
Recover the existing 800-request L1-only service TPS from raw records without replaying it; fix the wrapper; compare same-model/configuration/capacity/chunk/load L1-only, L1+L2 and full HiCache; attribute dominant Host eviction/write-through, scheduler admission/no-batch, prefetch and restore capacity wait costs using existing telemetry; apply evidence-backed in-contract changes and finish full active-tier 40×20 acceptance. Target near L1-only output throughput. Do not repeat KV correctness or historical benchmark certification, weaken correctness/capacity, or delete historical archives. Preserve T007 ACTIVE until user accepts results.
