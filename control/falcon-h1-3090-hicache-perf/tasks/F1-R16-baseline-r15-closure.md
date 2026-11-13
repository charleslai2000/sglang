# F1-R16 — GPU/Host performance baseline and R15 closure

Status: ACTIVE
Work area: `control/falcon-h1-3090-hicache-perf/runs/`
Objective: Obtain reproducible GPU-only and GPU+Host concurrency baselines independently of L3; separately validate/correct R15 host eviction and report L3 status.
Inputs: Frozen Falcon-H1 checkpoint/revision; accepted L2 result; R10/R11/R15 evidence; existing `benchmark/hicache/bench_serving.py` and `bench_multiturn.py`.
Completion: Matched workloads, repeated multi-concurrency curves, latency/throughput/memory/errors/cache/migration evidence, prefill/decode profiler evidence; R15 candidate verdict with regression coverage; L3 PASS/FAIL/NOT_RUN; changes committed and pushed, with no candidate left unvalidated.
Result: Started. RTX 3090 was idle at 2026-10-10 10:33 UTC. R15 script exited 1 because target KV Host detach was absent; persistent server was explicitly stopped. Existing R15 evidence proves durable ACK, not L3 restore. Candidate source changes and two CPU regressions are uncommitted; targeted existing GPU tests pass 48/9 skipped when server is stopped.
Remaining: Establish baseline workload/run harness, execute both configurations and profiling; prove/fix R15 path, then verify or isolate candidate; reconcile/commit/push only verified changes.
