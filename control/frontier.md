# Frontier

## falcon-h1-3090-hicache-perf
- R17 throughput, cache KPI and optimization — ACTIVE (R17-METRICS incomplete / not accepted)
  - frontier: NCU synthetic smoke only; no scheduler hardware counters. V2 profiles diagnostic only; full workload matrix and phase-split clean rates remain open. Host c8 t5 had 120/120 success but zero L1/L2/L3 restored tokens; D→H backup is not H→D restore. Need verified Host reuse/restore, matched cold/warm matrix, scheduler counters and profile-backed A/B. L3 `NOT_QUALIFIED`. See `runs/R17-20261012T0100Z/R17-METRICS-STATUS.md`.
  - task: control/falcon-h1-3090-hicache-perf/tasks/R17-throughput-cache-kpi.md
  - unblock/reopen: isolated worktree at pushed R16C baseline `6f612b030`; RTX3090 owner lock and idle check.

## falcon-h1-3090-hicache-perf
- T001 Falcon FULL+MAMBA L2/L3 lifecycle and performance validation — ACTIVE
  - frontier: R7C L2 PASS; R11/R15 durable ACK PASS but no target KV Host eviction/L3 restore. L3 is independent of R16 performance gate.
  - task: control/falcon-h1-3090-hicache-perf/tasks/T001-f1-source-and-seam-audit.md
  - unblock/reopen: continue source-level eviction-path diagnosis and restore using existing durable evidence.
- F1-R16 GPU/Host baseline and R15 closure — ACTIVE
  - frontier: Run matched GPU-only and GPU+Host benchmark curves first; no formal baseline may include the unverified R15 candidate.
  - task: control/falcon-h1-3090-hicache-perf/tasks/F1-R16-baseline-r15-closure.md
  - unblock/reopen: RTX 3090 currently idle; stop every test-owned service and verify VRAM/ports after each configuration.
