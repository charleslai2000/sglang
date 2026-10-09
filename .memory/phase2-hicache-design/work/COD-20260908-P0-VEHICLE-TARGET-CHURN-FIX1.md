ENTRY: ACCEPT

# COD-20260908-P0-VEHICLE-TARGET-CHURN-FIX1

- Task ID: `COD-20260908-P0-VEHICLE-TARGET-CHURN-FIX1`
- Orchestration epoch: `2026-09-08-P0`
- Role: `coder`
- Invocation status: **done**
- Admission: **ACCEPT**

## Artifacts

Changed only the authorized implementation and focused fixture:

- `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/p0_session_barrier_vehicle.py`
- `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/test_p0_trace_context_v4.py`

Required report:

- `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/COD-20260908-P0-VEHICLE-TARGET-CHURN-FIX1.md`

## Summary

Added a deterministic auxiliary churn phase of `FROZEN["active"] + 1 = 9`
builds after `_run_build_phase` and before `_run_warm_scheduler`.

- Churn IDs use `p0-s25-churn-00000` through `p0-s25-churn-00008`.
- Builder seeds are disjoint from the 25 target seeds (`25..33`), and duplicate
  target or churn histories fail closed.
- Churn admission requires HTTP 200, terminal completion, and `response.id`.
- Successful churn requests establish only reducer build identity; they are not
  inserted into `build_rows`, planned/eligible accounting, or warm submission.
- Churn response metrics and per-request failures are emitted in
  `churn-builds.jsonl` and summarized in `verdict.json`.
- Any churn failure is fatal and prevents the warm scheduler from starting.
- Final accounting explicitly checks that churn IDs do not overlap planned IDs.

## Verification evidence

- `PYTHONPYCACHEPREFIX=/tmp/codex-pycache-vehicle-churn python3 -m py_compile 3090-dev/p0_session_barrier_vehicle.py 3090-dev/test_p0_trace_context_v4.py` — **PASS**.
- `python3 3090-dev/test_p0_trace_context_v4.py` — **PASS** (`P0 trace-context V4.3 focused checks: PASS`).
- Independent `ast.parse` over both authorized files — **PASS**.
- `git diff --no-index --check /dev/null` for both authorized files — **PASS**.
- Focused churn fixture verified 25 target rows remain, 9 churn IDs are excluded from reducer/build-warm final accounting, seeds/history are distinct, churn runs before warm scheduling, and HTTP/missing-ID churn failures are fatal.
- No remote or live execution performed.

## Followups

- Dispatch the separately authorized reviewer gate for this FIX1 change.
- Run fresh live S=25 validation only after independent gate acceptance.

## Open issues

1. The supplied FIX4 live evidence remains `NOT_VERIFIED`; this change does not claim runtime residency, warm, or restore acceptance.
2. Existing aggregate checkout changes remain outside this task's authorized scope.

done
