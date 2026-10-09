ENTRY: ACCEPT

# COD-20260908-P0-VEHICLE-BARRIER-SCHEDULER-FIX1

- Task ID: `COD-20260908-P0-VEHICLE-BARRIER-SCHEDULER-FIX1`
- Orchestration epoch: `2026-09-08-P0`
- Role: `coder`
- Invocation status: **done**
- Admission: **ACCEPT**

## Artifacts

- Vehicle: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/p0_session_barrier_vehicle.py`
- Focused fixture: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/test_p0_trace_context_v4.py`

## Summary

Implemented the authorized two-phase scheduler fix. Build futures now perform
only prompt construction, HTTP build, response-ID validation, and
`reducer.establish_build`; they do not wait for durability or readiness. A
separate warm scheduler tracks built sessions, submits warm work only after
`reducer.ready_for_warm`, limits active warm futures to `args.build_workers`,
and lets warm workers wait for restore evidence.

The scheduler records one barrier outcome for every planned session,
represents build failures in `build_rows`, preserves exact reducer identity and
barrier semantics, and fails closed on tailer errors, barrier watchdog expiry,
warm submission loss, and restore watchdog expiry. Frozen CLI validation and
the existing V3/R7 tailer behavior were not changed.

## Verification evidence

- Focused dependency-free checks: **PASS** —
  `python3 3090-dev/test_p0_trace_context_v4.py` completed with
  `P0 trace-context V4.3 focused checks: PASS` before the later dry-run was
  interrupted.
- Deterministic scheduler fixture: included and exercised by the focused
  checks with `build_workers=2`, three sessions, one readiness-gated warm,
  two barrier watchdog failures, and sticky tailer-error fail-closed handling.
- `python3 -m py_compile` for the vehicle and focused fixture: **PASS**.
- AST parse for both changed files: **PASS**.
- `git diff --no-index --check` for both untracked changed files: **PASS**.
- Targeted-process check after interruption: no vehicle or focused-test process
  remained.
- No live, remote, engine, launcher, or product-Python execution was run.

The requested dry-run bundle command was interrupted by the user before a
result was obtained; it is not used as acceptance evidence and was not rerun.

## Changed files

- `p0_session_barrier_vehicle.py`: separated build admission from warm/barrier
  scheduling and added bounded fail-closed terminal accounting.
- `test_p0_trace_context_v4.py`: added the deterministic scheduler fixture.

## Followups

- Independent tester/reviewer may assess the implementation under a fresh task
  if required by orchestration gates.

## Open issues

- No live S=25 acceptance evidence was produced; this coder task does not claim
  P0 PASS.
- The interrupted dry-run has no verdict artifact attributable to this task.

done
