ENTRY: ACCEPT

# P0 vehicle barrier scheduler FIX4 independent gate

- Task ID: `REV-20260908-P0-VEHICLE-BARRIER-SCHEDULER-FIX4`
- Orchestration epoch: `2026-09-08-P0`
- Role: `reviewer`
- Invocation status: **done**
- Admission: **ACCEPT**
- Gate verdict: **ACCEPT**

## Scope and inputs

Read-only review of:

- `tools/p0_session_barrier_vehicle.py`
- `test/registered/unit/mem_cache/test_p0_trace_context_v4.py`
- rejected FIX1, FIX2, and FIX3 gates/reports
- `COD-20260908-P0-VEHICLE-BARRIER-SCHEDULER-FIX4.md`
- `TEST-20260908-P0-S25-LIVE-FIX2.md`
- `ARCH-20260908-P0-BUILD-COMPLETE-CONTRACT.md`
- `ARCH-20260908-P0-SCOPE-CLOSURE.md`

Only this gate and the assigned reviewer report were written. No reviewed
Python artifact, product source, launcher, remote host, engine, or live
endpoint was modified or run.

## Verdict summary

FIX4 closes both blocking FIX3 findings and preserves the previously accepted
boundaries. The warm scheduler now accounts for every submitted future at the
watchdog deadline, cancels pending work where possible, records a fatal
terminal outcome for running over-deadline work, and shuts down the executor
with `wait=False`. An independent submitted-worker probe returned at the
`0.03s` watchdog in `0.030s` while the worker slept for `0.30s`; final bundle
accounting was `NOT_VERIFIED`.

The HTTP parser now requires a parsed `finish_reason` or `[DONE]` for a 200
streamed response to be marked finished. Independent parser and admission
probes rejected HTTP 200 + response ID without terminal SSE evidence for both
build and warm, while a valid terminal SSE response remained accepted.

No blocking finding remains for this authorized vehicle/fixture gate. The
supplied live S=25 FIX2 evidence remains `NOT_VERIFIED`; this gate is local
vehicle acceptance and is not live runtime acceptance.

## Findings

None.

## Requirement review

| Requirement | Result | Evidence |
|---|---|---|
| F-7 submitted worker beyond watchdog returns bounded without executor wait | PASS | `p0_session_barrier_vehicle.py:1053-1070`; independent `0.30s` worker / `0.03s` watchdog probe returned in `0.030s`, recorded `warm worker exceeded watchdog timeout`, and bundle verdict was `NOT_VERIFIED`. |
| F-8 strict SSE completion for build and warm | PASS | `p0_session_barrier_vehicle.py:518-605`, build admission `:852-862`, warm admission `:962-973`; independent HTTP 200 + ID + no `finish_reason`/`[DONE]` probe produced `finished=False` and fatal rejection on both paths. |
| Valid SSE remains accepted | PASS | Independent terminal SSE with `finish_reason=stop` and `[DONE]` produced `finished=True`, non-empty response ID, and `rid_source=response.id`. |
| Build response HTTP/finished/response.id boundary | PASS | Current build admission and final accounting require HTTP 200, `finished is True`, non-empty RID, and `rid_source=response.id`; focused fixture and independent incomplete-SSE/build probes pass. |
| Warm response HTTP/finished/response.id boundary | PASS | Current warm admission and final accounting require HTTP 200, `finished is True`, non-empty RID, and `rid_source=response.id`; focused fixture and independent incomplete-SSE/warm probes pass. |
| Late tailer error | PASS | Scheduler records terminal tailer failure after future handling at `:1067-1068`; main repeats the terminal check after tailer shutdown at `:1137-1143`. Focused late-error probe passes. |
| First product warm order | PASS | Reducer preserves product lookup order and uses the vehicle marker only as fallback; focused causal-order probe passes. |
| Conflicting exact identity | PASS | Readiness requires one identity and no invalid join at `:363-377`; focused conflict probe passes. |
| Early warm-before-barrier | PASS | `lookup_before_barrier` is sticky, rejected by readiness, and terminally removed before submission at `:1019-1025`; focused scheduler probe records zero warm calls. |
| Original build deadlock | PASS | Build phase does not wait on readiness; focused 3-session/2-worker fixture observes all build calls and zero build-phase readiness checks. |
| No warm-before-exact barriers | PASS | Warm submission is gated on identity, KV/Mamba evidence, durability barrier, residency barrier, no early lookup, no errors, and a final worker-side recheck. |
| Frozen configuration / static hygiene | PASS | Focused fixture, `py_compile`, AST parse, and `git diff --no-index --check` all passed; frozen S=25/active=8/build-workers=8/history=55K/RH-off validation remains unchanged. |

## Evidence executed

- `PYTHONPYCACHEPREFIX=/tmp/codex-pycache-review-fix4 python3 test/registered/unit/mem_cache/test_p0_trace_context_v4.py` — **PASS** (`P0 trace-context V4.3 focused checks: PASS`).
- `PYTHONPYCACHEPREFIX=/tmp/codex-pycache-review-fix4 python3 -m py_compile tools/p0_session_barrier_vehicle.py test/registered/unit/mem_cache/test_p0_trace_context_v4.py` — **PASS**.
- Independent `ast.parse` over both authorized files — **PASS**.
- `git diff --no-index --check /dev/null` over both authorized untracked files — **PASS**; expected comparison status was normalized and no whitespace diagnostics were emitted.
- Independent F-7 submitted-worker probe — **PASS**: scheduler elapsed `0.030s` with watchdog `0.03s` while worker slept `0.30s`; fatal terminal accounting present; `_write_bundle` returned `NOT_VERIFIED`.
- Independent F-8 parser probe — **PASS**: HTTP 200 + ID + incomplete SSE returned `finished=False`; terminal `finish_reason` + `[DONE]` returned `finished=True`.
- Independent F-8 admission probe — **PASS**: incomplete SSE was rejected by both `_run_build_phase` and `_run_warm_scheduler` with fatal response-admission errors.
- Focused fixture rechecked prior FIX1/FIX2/FIX3 boundaries: build/warm HTTP and ID, late tailer error, warm order, identity conflict, early warm-before-barrier, original deadlock, watchdog/final accounting, and zero warm submission before exact barriers — **PASS**.
- No engine, launcher, remote host, live endpoint, or remote command was started.

## Supplied live evidence

`TEST-20260908-P0-S25-LIVE-FIX2.md` remains terminal
`NOT_VERIFIED`/fail-closed. It stopped after eight builds and contains no
exact final-node durability barriers, warm requests, or restore successes. It
is not acceptance evidence for this gate and does not authorize a live rerun.

## Followups

- A separately authorized live S=25 tester may proceed only under a fresh Task
  ID and must produce complete runtime evidence; this gate does not claim it.
- Preserve the current exact vehicle/fixture revision boundary when using this
  gate for downstream dispatch.

## Open issues

1. Live S=25 durable/warm acceptance remains **NOT_VERIFIED** because the
   supplied FIX2 run was stopped at the historical eight-build scheduling
   blocker.
2. The aggregate checkout remains dirty and the two reviewed files are
   untracked; no task-specific commit boundary exists.

done
