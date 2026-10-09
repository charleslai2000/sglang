# COD-20260908-P0-VEHICLE-BARRIER-SCHEDULER-FIX2

- Task ID: `COD-20260908-P0-VEHICLE-BARRIER-SCHEDULER-FIX2`
- Orchestration epoch: `2026-09-08-P0`
- Role: `coder`
- Invocation status: **done**
- Admission: **ACCEPT**

## Scope

Implemented only in the authorized vehicle and focused fixture:

- `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/p0_session_barrier_vehicle.py`
- `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/test_p0_trace_context_v4.py`

No product cache/source/launcher, remote host, engine, or live endpoint was
modified or run.

## Repairs

1. Build admission and final PASS accounting now require HTTP 200, exact
   `finished is True`, a nonempty build RID, and `rid_source == "response.id"`.
   Invalid builds are fatal and are not returned as build contexts.
2. Tailer errors are recorded as run-level terminal failures after the final
   warm-future drain and again after tailer shutdown before bundle verdict.
3. Warm admission and final PASS accounting require HTTP 200, exact
   `finished is True`, a nonempty warm RID, and `rid_source == "response.id"`.
   Invalid warm responses do not enter restore waiting.
4. Reducer warm order preserves the first product lookup/request order. The
   vehicle marker is only a fallback when no product warm order exists.
5. A second node/hash identity for the same session/build RID immediately
   marks `invalid_join`; warm readiness also requires exactly one identity and
   no reducer errors.

The existing exact V3 join, KV/Mamba ordering, durability/residency barriers,
no-warm-before-ready guard, watchdog, planned-session accounting, and separate
build/warm worker pools remain in place.

## Verification evidence

- `PYTHONPYCACHEPREFIX=/tmp/codex-pycache-vehicle-fix2 python3 3090-dev/test_p0_trace_context_v4.py` — **PASS**.
  This includes the original 3-session/2-worker deadlock regression and focused
  probes for all five FIX1 findings.
- `PYTHONPYCACHEPREFIX=/tmp/codex-pycache-vehicle-fix2 python3 -m py_compile 3090-dev/p0_session_barrier_vehicle.py 3090-dev/test_p0_trace_context_v4.py` — **PASS**.
- Independent AST parse of both authorized files — **PASS**.
- `git diff --no-index --check` against both untracked authorized files — **PASS**.
- No remote/live execution and no long-running dry-run performed.

## Artifacts

- Vehicle implementation: `3090-dev/p0_session_barrier_vehicle.py`
- Focused assertions/probes: `3090-dev/test_p0_trace_context_v4.py`
- This report: `COD-20260908-P0-VEHICLE-BARRIER-SCHEDULER-FIX2.md`

## Followups

- Obtain a fresh independent reviewer gate for FIX2.
- Only after that gate, schedule any separately authorized live validation.

## Open issues

1. No live or remote evidence was collected under this task authorization.
2. The target vehicle and focused fixture remain untracked in the aggregate
   checkout; no task-specific commit was created.

done
