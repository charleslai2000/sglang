ENTRY: ACCEPT

# REV-20260908-P0-VEHICLE-BARRIER-SCHEDULER-FIX3

- Task ID: `REV-20260908-P0-VEHICLE-BARRIER-SCHEDULER-FIX3`
- Orchestration epoch: `2026-09-08-P0`
- Role: `reviewer`
- Invocation status: **done**
- Admission: **ACCEPT**
- Gate verdict: **REJECT**

## Artifacts

- Gate: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/review/gates/P0-VEHICLE-BARRIER-SCHEDULER-FIX3.md`
- Reviewed vehicle: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/p0_session_barrier_vehicle.py`
- Reviewed fixture: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/test_p0_trace_context_v4.py`

## Evidence

- Focused fixture — **PASS**.
- `py_compile` — **PASS** for vehicle and fixture.
- AST parsing — **PASS** for vehicle and fixture.
- Untracked-file whitespace checks — **PASS**.
- Independent F-6 probe — **PASS**: early product warm evidence leaves
  `ready_for_warm()` false and the scheduler makes zero warm submissions.
- Independent original build deadlock probe — **PASS**: 3/3 build calls and
  contexts completed with zero readiness checks during the build phase.
- Independent late tailer error, warm-order, identity, and response-admission
  branches are covered by the focused fixture and prior FIX2 evidence.
- Independent submitted-worker watchdog probe — **FAIL**: a `0.20s` warm
  worker with a `0.03s` watchdog delayed scheduler return to about `0.201s`
  because executor shutdown waited for the worker.
- Independent incomplete-SSE response probe — **FAIL-CLOSED VIOLATION**: HTTP
  200 plus a response ID and no terminal completion marker returned
  `finished=True`.
- No remote or live execution was performed.

## Summary

FIX3 correctly closes the rejected FIX2 F-6 issue in the tested scheduler
path and preserves the previously repaired identity, response-admission,
tailer, warm-order, and build-pool separation behavior. The implementation
cannot be accepted because the watchdog is not a hard bound once a warm future
has started, and the response parser admits incomplete streamed responses as
finished. Both are blocking fail-closed/acceptance issues.

## Followups

- Fresh coder Task ID required for the submitted-worker watchdog/final
  accounting repair and regression.
- Fresh coder Task ID required for strict streamed-response completion
  admission and build/warm regression coverage.
- Fresh independent reviewer Task ID required after both repairs.
- Keep live S=25 validation blocked until the fresh gate is accepted.

## Open issues

1. F-7: `_run_warm_scheduler()` can wait past its watchdog while its executor
   context shuts down a still-running warm future.
2. F-8: `post_chat()` line 593 treats any non-empty HTTP 200 response body as
   `finished=True`, including an incomplete SSE body with an ID.
3. The supplied S=25 FIX2 live evidence remains `NOT_VERIFIED`; no runtime
   acceptance is claimed.
4. The aggregate checkout remains dirty and the authorized vehicle/fixture are
   untracked; no task-specific revision was created.

done
