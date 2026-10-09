ENTRY: ACCEPT

# REV-20260908-P0-VEHICLE-BARRIER-SCHEDULER-FIX4

- Task ID: `REV-20260908-P0-VEHICLE-BARRIER-SCHEDULER-FIX4`
- Orchestration epoch: `2026-09-08-P0`
- Role: `reviewer`
- Invocation status: **done**
- Admission: **ACCEPT**
- Gate verdict: **ACCEPT**

## Artifacts

- Gate: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/review/gates/P0-VEHICLE-BARRIER-SCHEDULER-FIX4.md`
- Reviewed vehicle: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/p0_session_barrier_vehicle.py`
- Reviewed fixture: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/test_p0_trace_context_v4.py`

## Evidence

- Focused fixture: **PASS**.
- `py_compile`: **PASS** for vehicle and fixture.
- Independent AST parse: **PASS** for vehicle and fixture.
- `git diff --no-index --check /dev/null`: **PASS** for both untracked
  authorized files; no whitespace diagnostics.
- Independent F-7 probe: a submitted warm worker sleeping `0.30s` with a
  `0.03s` watchdog returned from `_run_warm_scheduler` in `0.030s`; the worker
  was terminally recorded as over-deadline and `_write_bundle` returned
  `NOT_VERIFIED`.
- Independent F-8 parser probe: HTTP 200 plus `partial-id` and no
  `finish_reason`/`[DONE]` returned `finished=False`; valid terminal SSE
  returned `finished=True` with `rid_source=response.id`.
- Independent F-8 admission probe: the incomplete response was rejected in
  both build and warm paths with fatal admission errors.
- Focused prior-boundary recheck: build/warm HTTP and ID, late tailer error,
  warm order, identity conflict, early warm-before-barrier, original deadlock,
  watchdog/final accounting, and no warm-before-barrier — **PASS**.
- No remote or live execution was performed.

## Summary

FIX4 closes both rejected FIX3 blockers. The explicit warm executor lifecycle
does not wait for a running worker after the watchdog deadline, but it still
records a fatal terminal outcome so the final bundle cannot be accepted. The
stream parser is fail-closed for incomplete SSE and retains valid terminal SSE
behavior. All earlier FIX1/FIX2/FIX3 boundary repairs remain covered and pass.

The local vehicle/fixture gate is accepted. The supplied S=25 live FIX2 report
remains `NOT_VERIFIED` and is not converted into runtime acceptance.

## Followups

- Any live S=25 validation requires a separately authorized fresh Task ID and
  must establish the complete 25-session durable/warm evidence contract.

## Open issues

1. No live durable/warm acceptance evidence exists in the supplied FIX2 report;
   downstream runtime acceptance remains open.
2. The aggregate checkout is dirty and the reviewed files are untracked; there
   is no task-specific commit boundary.

done
