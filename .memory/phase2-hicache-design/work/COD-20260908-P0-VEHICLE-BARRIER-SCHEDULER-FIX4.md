ENTRY: ACCEPT

# COD-20260908-P0-VEHICLE-BARRIER-SCHEDULER-FIX4

- Task ID: `COD-20260908-P0-VEHICLE-BARRIER-SCHEDULER-FIX4`
- Orchestration epoch: `2026-09-08-P0`
- Role: `coder`
- Invocation status: **done**
- Admission: **ACCEPT**

## Scope

Changed only the authorized vehicle and focused fixture:

- `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/p0_session_barrier_vehicle.py`
- `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/test_p0_trace_context_v4.py`

No product cache/source/launcher was modified, and no remote or live command
was run. Existing unrelated checkout changes were preserved.

## Repairs

1. F-7: replaced the warm scheduler's `ThreadPoolExecutor` context shutdown
   with explicit lifecycle management. Submitted warm futures are checked
   without blocking after the watchdog deadline, pending work is cancelled
   where possible, running over-deadline workers receive fatal terminal
   accounting, and `shutdown(wait=False, cancel_futures=True)` prevents final
   bundle accounting from waiting on a stuck worker.
2. F-8: streamed responses are now finished only when a parsed
   `finish_reason` or `[DONE]` terminal marker is present. HTTP 200 plus a
   nonempty body/ID without terminal evidence remains `finished=False`; valid
   completed SSE behavior is retained.
3. Added deterministic F-7 watchdog/fatal/`NOT_VERIFIED` bundle regression and
   F-8 incomplete-SSE parser, build-admission, warm-admission, and valid-SSE
   regressions.

## Verification evidence

- `PYTHONPYCACHEPREFIX=/tmp/codex-pycache-vehicle-fix4 python3 -m py_compile 3090-dev/p0_session_barrier_vehicle.py 3090-dev/test_p0_trace_context_v4.py` — **PASS**.
- `PYTHONPYCACHEPREFIX=/tmp/codex-pycache-vehicle-fix4 python3 3090-dev/test_p0_trace_context_v4.py` — **PASS** (`P0 trace-context V4.3 focused checks: PASS`). This includes deterministic F-7 and F-8 probes.
- Independent `ast.parse` over both authorized files — **PASS**.
- `git diff --no-index --check /dev/null` checks over both authorized files — **PASS**.
- No remote/live execution performed.

## Artifacts

- Vehicle repair: `3090-dev/p0_session_barrier_vehicle.py`
- Focused regressions: `3090-dev/test_p0_trace_context_v4.py`
- Coder report: `COD-20260908-P0-VEHICLE-BARRIER-SCHEDULER-FIX4.md`

## Followups

- Dispatch a fresh independent reviewer task for the FIX4 gate.
- Keep live S=25 validation blocked until a fresh gate accepts the repair.

## Open issues

1. Supplied live S=25 FIX2 evidence remains `NOT_VERIFIED`; no runtime
   acceptance is claimed.
2. Independent reviewer acceptance is still required for F-7/F-8.
3. The aggregate checkout remains dirty with unrelated prior changes and no
   task-specific commit boundary.

done
