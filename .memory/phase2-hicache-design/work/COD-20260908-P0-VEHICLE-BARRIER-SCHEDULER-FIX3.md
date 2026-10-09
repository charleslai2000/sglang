ENTRY: ACCEPT

# COD-20260908-P0-VEHICLE-BARRIER-SCHEDULER-FIX3

- Task ID: `COD-20260908-P0-VEHICLE-BARRIER-SCHEDULER-FIX3`
- Orchestration epoch: `2026-09-08-P0`
- Role: `coder`
- Invocation status: **done**
- Admission: **ACCEPT**

## Scope

Changed only the authorized vehicle and focused fixture:

- `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/p0_session_barrier_vehicle.py`
- `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/test_p0_trace_context_v4.py`

No product cache/source/launcher was modified, and no remote or live command
was run.

## Repairs

1. `Reducer.ready_for_warm()` now explicitly rejects the sticky
   `lookup_before_barrier` state while preserving the existing identity,
   invalid-join, barrier-error, reducer-error, durability, and residency
   predicates.
2. Added a reducer rejection reason for `lookup_before_barrier`. The warm
   scheduler consumes that state terminally, records a fatal
   `warm not submitted` error, records the barrier wait as rejected, and never
   queues a warm future.
3. Added an F-6 scheduler-path regression that observes
   `build_complete -> warm_lookup_start -> KV/Mamba -> durability_barrier ->
   residency_barrier`, asserts readiness remains false, and asserts zero warm
   submissions. Existing valid post-barrier product lookup and synthetic
   marker causal assertions remain intact.

## Verification evidence

- `PYTHONPYCACHEPREFIX=/tmp/codex-pycache-vehicle-fix3 python3 test_p0_trace_context_v4.py` — **PASS** (`P0 trace-context V4.3 focused checks: PASS`).
- `PYTHONPYCACHEPREFIX=/tmp/codex-pycache-vehicle-fix3 python3 -m py_compile p0_session_barrier_vehicle.py test_p0_trace_context_v4.py` — **PASS**.
- Independent AST parse of both authorized files — **PASS**.
- Deterministic extracted scheduler probe — **PASS**; early product warm returned `lookup_before_barrier`, recorded fatal/no-warm, and made zero warm calls.
- `git diff --no-index --check` whitespace checks for both authorized files — **PASS**.
- No remote/live execution performed.

## Artifacts

- Vehicle repair: `3090-dev/p0_session_barrier_vehicle.py`
- Focused regression: `3090-dev/test_p0_trace_context_v4.py`
- This report: `COD-20260908-P0-VEHICLE-BARRIER-SCHEDULER-FIX3.md`

## Followups

- Dispatch a fresh independent reviewer task for the FIX3 gate.
- Keep live S=25 validation blocked until the fresh gate accepts the repair.

## Open issues

1. No live or remote acceptance evidence was collected under this
   authorization.
2. The aggregate checkout remains dirty and the authorized vehicle/fixture
   are untracked; no task-specific commit was created.

done
