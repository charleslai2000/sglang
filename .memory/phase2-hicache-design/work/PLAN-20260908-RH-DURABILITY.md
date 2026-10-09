# PLAN-20260908-RH-DURABILITY

## status

done

## invocation

- First-line admission: `ENTRY: ACCEPT`.
- Task ID: `PLAN-20260908-RH-DURABILITY`.
- Orchestration epoch: `E20260908-P0P1P2`.
- Role: `task-manager`.
- Authorized scope honored: read the supplied phase-2 memory, T38C reports, handoff, and active opt worktree; write only the plan artifact and this report.
- No product files, ledger, or context files were edited.

## artifacts

- [plan-rh-durability.md](/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/plan-rh-durability.md)
- [PLAN-20260908-RH-DURABILITY.md](/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/PLAN-20260908-RH-DURABILITY.md)

## evidence used

- `ledger.md` latest combined-task entry: P0 durability and 100% full restore precede deterministic P1 RH staging and P2 same-trace comparison; S=100/500/1000 are forbidden before all gates.
- `context.md`: Phase-2 production baseline remains RH OFF; RH is deferred until its focused validation is complete.
- `work/DBG-20260908-T38C.md`: raw KV can be present while Mamba trailing state clamps the usable fold to zero; KV-only acceptance is unsound.
- `work/EXP-20260908-T38C-PAIRED-TRACE-S25.md`: seven full warm samples yielded six KV+Mamba restores and one `s00002` missing query key; all observed writes reported successful API results.
- `work/TEST-20260908-T38C-PAIRED-TRACE-INDEPENDENT.md`: independent recomputation agrees with the key-set relation and warns that late asynchronous timing is not fully closed by the prior settle.
- `work/ORCH-20260908-T38C-METRICS-ADDENDUM.md`: 25 writes included two during the warm window, so sleep-based durability is explicitly rejected.
- `work/phase2-cap-e5-architect-e1.md` and `work/phase2-parked-v2-coder-e1.md`: existing engine event names, RH frontier/watermark values, parked-session KPI vocabulary, no-pause semantics, and later-scale no-go boundary.
- Active worktree inspection: `3090-24g-opt` has pre-existing uncommitted T38C product changes and parked-driver artifacts; the plan assigns disjoint future write sets and requires preservation.

## summary

The dispatch is valid and the requested executable DAG is complete. The scheduler is intentionally pending at P0 instrumentation: the current T38C evidence is diagnostic, not a durability PASS, because `s00002` remains a branch-specific missing Mamba key and the prior 300-second settle does not prove ACK/frontier completion.

The plan serializes product trace work, vehicle work, the focused S=25 RH-off retest, an independent P0 review, deterministic RH-on queue-horizon validation, an exact same-trace A/B, and an independent final review. It records disjoint write sets, exact KPI thresholds, the required per-session evidence schema, remote stop/cleanup rules, and the scale authorization barrier.

## followups

1. Dispatch `RH-DUR-P0-01` to `coder` with a fresh Task ID.
2. After its schema is accepted, dispatch `RH-DUR-P0-02` to `executor` for the isolated vehicle/collector.
3. Do not dispatch any P1 or scale task until the independent P0 reviewer returns PASS.

## open_issues

1. `s00002` remains unresolved among omission, write failure, key mismatch, recycle/removal, and late-write/barrier timing; the plan requires direct evidence for one branch.
2. The current T38C instrumentation has no keyed removal/recycle hook; P0 must add or explicitly prove the relevant lifecycle evidence before claiming PASS.
3. P2 “significant improvement” is operationalized in the plan as a paired bootstrap criterion with a reported p95 ratio; a contrary result requires reviewer FAIL/OPEN and a fresh decision, not a silent threshold change.

