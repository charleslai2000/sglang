status: done
artifacts:
  - /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/plan.md
  - /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/PLAN-3060-HICACHE-NEXT-20260910.md
evidence:
  - Read only the designated planning inputs: context.md, ledger.md, HANDOFF-2026-09-10-48H-SUMMARY.md, and the designated RH/HOST_ALLOC review, test, debug, runtime, capacity, and restore reports.
  - Current authoritative state records dependency-complete RH runtime tests as pending, clean matched durable blocker+A/B OFF/ON as not verified, feasible HOST_ALLOC wake as unproven, capacity figures as requiring complete-argument reconciliation, and no current product/deploy/live-trace authorization.
  - The plan explicitly separates correctness gates, measurement tasks, shared single-GPU serialization, and read-only architecture decisions.
summary:
  - Updated plan.md with a current-stage minimal executable DAG of twelve tasks.
  - P0 includes dependency-complete RH focused tests (T01) and feasible HOST_ALLOC wake liveness closure (T02).
  - P1 includes fresh durable KV+Mamba fixture and matched blocker+A/B OFF/ON trace with release epoch -> RH stage -> host-ready -> admission -> restore evidence (T03/T04), plus complete server-argument capacity reconciliation for FP8 KV approximately 65,536 versus allocator approximately 193,294 (T05).
  - P2 measures real agent lead time before deciding queue-only versus preannouncement (T06/T07), audits query_storage_hit_length timing by enter/exit/backend wait/lock wait/syscall/future wait before any async redesign (T08), defines and runs the C1/C4/C5/C6/C8 benchmark (T09/T10), keeps C2 outside the main line as sanity-only (T11), and gives FP8 scale quality an independent gate (T12).
  - The plan removes TFTT entirely, does not make TTFT below one second or GPU utilization near 100 percent hard gates, separates total throughput from aggregate output TPS and other throughput fields, binds capacity claims to complete server args, and states stop/rollback/evidence conditions.
open_issues:
  - T01 needs an already dependency-complete environment; no package installation is authorized by this plan.
  - T02 requires a deliberately feasible primary-host allocability change before timeout; existing evidence only proves safe classification, not successful wake.
  - T03/T04 and all runtime measurements need separate explicit live/deploy/storage authorization plus exclusive ownership of the 3060 service/GPU/storage.
  - T05 and T09 may remain blocked if complete server arguments or an authoritative total-throughput definition cannot be recovered without guessing.
  - T12 needs an explicit FP8 calibration/reference set; a functional HTTP success cannot serve as the quality oracle.
