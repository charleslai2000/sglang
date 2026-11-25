# Gemma4 RTX 3090 GPU throughput and scheduling optimization

## Goal
Improve end-to-end performance of the existing Gemma4 Owner-only W4A16 / FP8 E5M2 KV service on RTX 3090, starting from the accepted T006 configuration and fixed-budget cache/resource settings. Attribute low GPU utilization and small Prefill batches to measured workload phases and concrete scheduler/cache/source paths; implement only contract-compatible optimizations supported by evidence and validate net benefit against a same-load, same-configuration baseline.

## Scope
Reuse T006 C-8 results and existing profiler/telemetry patterns, including `device_timer.py`, `nvtx_utils.py`, metrics reporting, available Nsight Systems capture procedures, and `benchmark/hicache/bench_multiturn.py`. Inspect historical Gemma/Falcon profiler and convergence work where present. Preserve Owner-only FP8 KV, pool budgets, workload, and active L1/L2/L3 behavior. Make source/runtime provenance explicit. Continue inspect → measure → optimize → test/compare without procedural handoffs.

## Constraints
- No standalone certification or new profiling framework; restore/reuse existing DeviceTimer/FPM/NVTX and established Nsight Systems usage.
- Do not weaken workload, reduce offered load, disable cache tiers, replay historical WAL, or repeat already completed KV correctness qualifications.
- Separate actual uncached Prefill computation from logical input tokens and distinguish forward batch TPS from end-to-end throughput.
- Preserve all unrelated dirty/untracked work. Selectively commit/push only T007 changes.
- GPU is authorized for this goal; acquire `/tmp/f1-r16b-gpu-exclusive.lock`, check GPU/service/ports before use, bound all workload windows, and clean up owned process trees.
- Algorithmic scheduling or KV ownership changes are outside implicit authority and require a concrete decision; contract-preserving implementation/parameter fixes are allowed when evidence supports them.

## Completion
Completed: same-load 800/800 C-8 comparisons and output payload identity validate the chunk=4096 parameter; E2E throughput/latency, batching and memory results are recorded. Existing Nsight/NVTX directly attributes the longest GPU gap to scheduler no-batch polling and distinguishes it from blocking CPU/HiCache calls and GPU stream dependencies. Historical cache correctness results are reused; no new L2/L3 ledger or theoretical chunk maximum was required by the user's narrowed request. T007 report/control records are ready for selective commit/push and remote SHA verification; traces and source identity are retained.
