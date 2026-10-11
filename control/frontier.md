# Frontier

## falcon-h1-3090-hicache-perf
- R16C multi-turn performance and profiling milestone — ACTIVE
  - frontier: Matched c1/c4/c8 and representative c8 Prefill/Decode profiles complete; exact historical prompts/source absent, residual 371.2→316.6 tok/s UNKNOWN. Review and commit only R16C deliverables; leave unrelated dirty changes untouched.
  - task: control/falcon-h1-3090-hicache-perf/tasks/R16C-multiturn-profile.md
  - unblock/reopen: clean baseline `481f2b485`; RTX3090 idle; use exclusive GPU lock.

## falcon-h1-3090-hicache-perf
- T001 Falcon FULL+MAMBA L2/L3 lifecycle and performance validation — ACTIVE
  - frontier: R7C L2 PASS; R11/R15 durable ACK PASS but no target KV Host eviction/L3 restore. L3 is independent of R16 performance gate.
  - task: control/falcon-h1-3090-hicache-perf/tasks/T001-f1-source-and-seam-audit.md
  - unblock/reopen: continue source-level eviction-path diagnosis and restore using existing durable evidence.
- F1-R16 GPU/Host baseline and R15 closure — ACTIVE
  - frontier: Run matched GPU-only and GPU+Host benchmark curves first; no formal baseline may include the unverified R15 candidate.
  - task: control/falcon-h1-3090-hicache-perf/tasks/F1-R16-baseline-r15-closure.md
  - unblock/reopen: RTX 3090 currently idle; stop every test-owned service and verify VRAM/ports after each configuration.
