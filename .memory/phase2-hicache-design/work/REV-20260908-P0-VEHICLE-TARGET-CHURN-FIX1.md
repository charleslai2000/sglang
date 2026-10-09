ENTRY: ACCEPT

# REV-20260908-P0-VEHICLE-TARGET-CHURN-FIX1

- Task ID: `REV-20260908-P0-VEHICLE-TARGET-CHURN-FIX1`
- Orchestration epoch: `phase2-hicache-design / 2026-09-08`
- Role: `reviewer`
- Invocation status: **done**
- Admission: **ACCEPT**
- Gate verdict: **ACCEPT**

## Artifacts

- Gate: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/review/gates/P0-VEHICLE-TARGET-CHURN-FIX1.md`
- Reviewed vehicle: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/p0_session_barrier_vehicle.py`
- Reviewed fixture: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/test_p0_trace_context_v4.py`

## Summary

ACCEPT. Independent source review, focused tests, syntax checks, and an
adversarial churn-failure probe satisfy all seven acceptance criteria. The
implementation adds nine deterministic auxiliary builds after all 25 target
builds and before warm scheduling, keeps them out of target accounting, and
fails closed with separate churn evidence on admission failures.

## Evidence

- `PYTHONPYCACHEPREFIX=/tmp/codex-review-pycache python3 -m py_compile /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/p0_session_barrier_vehicle.py /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/test_p0_trace_context_v4.py` — PASS.
- `python3 /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/test_p0_trace_context_v4.py` — PASS: `P0 trace-context V4.3 focused checks: PASS`.
- Independent AST parsing and whitespace checks — PASS.
- Independent adversarial churn probe — PASS: `calls=34 churn_count=9 failures=3 target_rows=25 churn_rows_excluded=True`; failure classes were HTTP, unfinished, and missing `response.id`.
- Direct source inspection confirms target build completion precedes churn, churn precedes warm scheduling, successful churn identity establishment follows response admission, and warm readiness retains exact durability/residency/causal/watchdog gates.

## Findings

None.

## Followups

- A fresh live S=25 run may proceed under its own Task ID after this gate.
- Live runtime evidence must still prove durability, residency, warm, and restore acceptance.

## Open issues

1. Supplied live acceptance remains `NOT_VERIFIED`; no live execution was
   performed by this reviewer.
2. Existing unrelated checkout dirt and untracked files remain outside scope.

done
