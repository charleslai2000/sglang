status: done
artifacts:
  - /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/plan.md
  - /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/PLAN-3060-HICACHE-CORRECTIONS-20260910.md
evidence:
  - Read the dispatch-designated current plan, context, ledger tail, and prior planning report.
  - The prior plan contained duplicate T03/T05 IDs and placed capacity/profile work in parallel before the desired clean A/B gate; the revised plan replaces it with unique phase-based IDs and canonical ordering.
  - User-fixed metric and governance constraints were incorporated: no TFTT, TTFT<1s and near-100% GPU utilization are optimization targets, C1/C4/C5/C6/C8 main matrix, C2 out-of-band sanity, separated throughput fields, complete server-argument binding, independent FP8 quality gate, and exclusive serialized 3060 runtime ownership.
summary:
  - Rewrote plan.md as a minimal executable DAG with canonical sequence: P0-A RH tests -> P0-B HOST_ALLOC liveness -> P0-C capacity/profile freeze -> P1 fresh identity-preserving causal A/B -> P2-A lead-time/query timing -> P2-B benchmark/capacity matrix -> P3 soak/restart/pressure/fallback; Q-FP8 is independent and blocks final production quality sign-off.
  - P1 is one causal deliverable and explicitly requires the chain SPEC_BUDGET park -> reservation/release epoch transition -> RH wake -> L3->L2 stage -> Host-ready -> admission -> L2->L1 restore -> generation, with cached_tokens>0, zero full-prefix recompute, hybrid_discard=0, and RID/session/node/build/generation continuity.
  - HOST_ALLOC remains a P0 hard liveness gate. Capacity/profile freeze is P0-C and precedes P1. Production scorecard now requires scenario-specific TTFT P95 (L1/L2/RH-staged L3/cold L3), cache-induced idle, and restore_wait/queue_wait/compute/decode breakdown; cold L3 is not assigned the <1s target.
  - Added explicit independent authorization, single-service/GPU/storage serialization, stop/rollback, evidence, and open-issue rules; retained C2 outside the mainline.
followups:
  - Orchestrator should verify the revised plan against the user acceptance checklist before dispatching execution tasks.
open_issues:
  - Dependency-complete test environment, feasible HOST_ALLOC event, complete capacity server args, fresh durable A/B fixture, authoritative total-throughput formula, runtime timing authorization, and FP8 calibration/reference coverage remain unresolved execution inputs.
