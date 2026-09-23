ENTRY: ACCEPT

# P0 vehicle barrier scheduler FIX2 independent gate

- Task ID: `REV-20260908-P0-VEHICLE-BARRIER-SCHEDULER-FIX2`
- Orchestration epoch: `2026-09-08-P0`
- Role: `reviewer`
- Invocation status: **done**
- Admission: **ACCEPT**
- Gate verdict: **REJECT**

## Scope and inputs

Read-only review of:

- `tools/p0_session_barrier_vehicle.py`
- `test/registered/unit/mem_cache/test_p0_trace_context_v4.py`
- prior `P0-VEHICLE-BARRIER-SCHEDULER-FIX1.md` gate and report
- `COD-20260908-P0-VEHICLE-BARRIER-SCHEDULER-FIX2.md`
- `TEST-20260908-P0-S25-LIVE-FIX2.md`
- `ARCH-20260908-P0-BUILD-COMPLETE-CONTRACT.md`
- accepted `P0-R7-JOIN-ROBUSTNESS-FIX5.md`

Only this gate and the assigned memory report were written. No reviewed Python
artifact, product source, launcher, remote host, engine, or live endpoint was
modified or run. The aggregate checkout remains dirty and the reviewed vehicle
and fixture are untracked; this review is against their exact current contents.

## Verdict summary

All five FIX1 blocking findings are closed in the nominal and independently
probed paths:

1. build HTTP/finished/`response.id` admission and final accounting are
   fail-closed;
2. terminal tailer errors are carried through the final warm-future drain and
   final bundle accounting;
3. warm responses require HTTP 200, `finished is True`, and a non-empty
   `response.id` RID;
4. a first product warm order is not overwritten by the later vehicle marker;
5. a conflicting node/hash identity invalidates readiness before warm.

The gate is nevertheless **REJECTED** because an additional blocking boundary
failure remains: a product `warm_lookup_start` observed before the durability
and residency barriers sets `lookup_before_barrier`, but `ready_for_warm()`
does not reject that state. Once later barriers arrive, the scheduler can
submit a client warm request despite prior warm-before-barrier evidence. This
violates the authoritative causal order and the explicit no-warm-before-exact-
barriers requirement.

## Findings

### F-6 — BLOCKING: prior product warm-before-barrier evidence does not invalidate readiness

- Location: `p0_session_barrier_vehicle.py:294-308` sets
  `state["lookup_before_barrier"]`; `:363-376` implements `ready_for_warm()`
  without checking that flag; `:1002-1015` promotes every ready session to a
  warm future.
- Evidence: an independent reducer probe ingested `build_complete`, then a
  product `warm_lookup_start`, then KV/Mamba and both exact barriers. The state
  retained `lookup_before_barrier=True`, but
  `ready_for_warm()` returned `True`. An independent scheduler probe then
  recorded `warm_submissions=['p0-s25-s00000']` for that session. The run later
  timed out restore, but the forbidden warm request had already been sent.
- Acceptance impact: the vehicle can issue a duplicate/client warm after the
  trace already proves a product warm happened before exact durability and
  residency barriers. The final row may be non-PASS because its causal order
  is bad, but the scheduler has already violated the gate and can perturb live
  S=25 behavior. The architectural causal contract requires
  `durability_barrier -> residency_barrier -> vehicle warm request /
  warm_lookup_start`; this path does not enforce that invariant before
  submission.
- Required closure: make any prior `lookup_before_barrier` terminal for warm
  readiness and add a focused regression that exercises the scheduler path,
  not only final-row rejection.

No review questions remain; F-6 is a finding, not a clarification request.

## Requirement review

| Requirement | Result | Evidence |
|---|---|---|
| Build HTTP/finished/response.id admission and final row | PASS for FIX1 repair | Independent probes rejected HTTP 500, `finished=False`, and non-`response.id` build responses before context promotion; the focused fixture also checks malformed final accounting. |
| Terminal tailer error, including post-future | PASS for FIX1 repair | Independent late-error tailer injected a valid restore then set an error; scheduler recorded a terminal fatal and `_write_bundle` returned `NOT_VERIFIED`, not `PASS`. |
| Warm HTTP/finished/response.id admission | PASS for FIX1 repair | Independent 200/finished/no-ID response produced a fatal and no restore wait or warm state. |
| First product warm causal order is stable | PASS for FIX1 repair | Independent product lookup + restore + vehicle marker probe preserved the first product order and returned `restore_ready=True`. |
| Conflicting node/hash identity invalidates readiness | PASS for FIX1 repair | Independent conflicting identity probe produced `identity_count=2`, `invalid_join=True`, and `ready_for_warm=False`. |
| Original build/warm scheduling deadlock regression | PASS structurally and in focused fixture | Focused fixture passed; independent 3-session/2-worker probe observed all builds submitted with zero readiness checks during build, while the separate warm path submitted only after exact barriers. Frozen source keeps both pools bounded at 8. |
| No warm-before-exact barriers | **REJECT** | F-6: early product warm evidence leaves `ready_for_warm=True` after later barriers and the scheduler submits warm. |
| Watchdog and final accounting | PASS for exercised repairs, but gate remains rejected | Focused watchdog fixture passed; late tailer errors are fatal. F-6 still violates the pre-submission invariant even though the resulting row is not accepted. |
| Frozen validation, exact V3 joins, and no fixed-sleep success | PASS structurally | `_validate_frozen` enforces S=25, active/build-workers=8, history 55K, RH off; the focused fixture and AST review preserve exact identity/barrier predicates. |

## Evidence executed

- `PYTHONPYCACHEPREFIX=/tmp/codex-pycache-vehicle-fix2-review python3 test_p0_trace_context_v4.py` — **PASS** (`P0 trace-context V4.3 focused checks: PASS`).
- `PYTHONPYCACHEPREFIX=/tmp/codex-pycache-vehicle-fix2-review python3 -m py_compile p0_session_barrier_vehicle.py test_p0_trace_context_v4.py` — **PASS**.
- Independent `ast.parse` over both authorized files — **PASS**.
- `git diff --no-index --check /dev/null` over both untracked authorized files — **PASS**; exit status was normalized for the expected `/dev/null` comparison.
- Independent FIX1 repair probes — **PASS** for all five repairs: build admission/final accounting, late tailer error, missing warm ID, warm-order preservation, and conflicting identity readiness.
- Independent scheduling probe — **PASS** for the build deadlock/no-premature client warm/watchdog scenario.
- Independent F-6 probe — **FAIL** for the required invariant: early product warm evidence left `ready_for_warm=True` and caused one warm submission after barriers.
- No engine, launcher, remote host, live endpoint, or remote command was started.

## Supplied live evidence

`TEST-20260908-P0-S25-LIVE-FIX2.md` remains terminal `NOT_VERIFIED`/fail-closed:
the prior run stopped after eight builds with no exact final-node barriers,
warm requests, or restores. It is not acceptance evidence for this gate and
does not authorize a new live run. A fresh live S=25 run remains disallowed
until a fresh implementation Task ID closes F-6 and this gate is re-reviewed.

## Followups

- Fresh coder Task ID: make `lookup_before_barrier` terminal for
  `ready_for_warm()` and add the early-product-warm scheduler regression.
- Fresh reviewer Task ID: repeat this independent gate after that repair; do
  not reuse this rejected gate as acceptance.
- Only after a fresh accepted gate, dispatch a separately authorized live S=25
  tester task.

## Open issues

1. F-6 remains a blocking scheduler invariant failure.
2. The supplied live FIX2 evidence has no durable/warm acceptance and remains
   `NOT_VERIFIED`.
3. The aggregate worktree has no task-specific commit boundary; broad
   authorship attribution remains a process caveat.

done
