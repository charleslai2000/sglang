ENTRY: ACCEPT

# P0 vehicle barrier scheduler FIX3 independent gate

- Task ID: `REV-20260908-P0-VEHICLE-BARRIER-SCHEDULER-FIX3`
- Orchestration epoch: `2026-09-08-P0`
- Role: `reviewer`
- Invocation status: **done**
- Admission: **ACCEPT**
- Gate verdict: **REJECT**

## Scope and inputs

Read-only review of:

- `tools/p0_session_barrier_vehicle.py`
- `test/registered/unit/mem_cache/test_p0_trace_context_v4.py`
- the rejected FIX2 gate/report
- `COD-20260908-P0-VEHICLE-BARRIER-SCHEDULER-FIX3.md`
- `TEST-20260908-P0-S25-LIVE-FIX2.md`
- `ARCH-20260908-P0-BUILD-COMPLETE-CONTRACT.md`

Only this gate and the assigned memory report were written. No reviewed Python
artifact, product source, launcher, remote host, engine, or live endpoint was
modified or run.

## Verdict summary

FIX3 closes the previously reported F-6 boundary in the exercised path: an
early product `warm_lookup_start` makes `ready_for_warm()` false, remains
sticky after later barriers, and is terminally removed by the scheduler before
any warm future is submitted. The FIX1/FIX2 nominal boundaries also remain
covered and passed: build and warm HTTP/finished/ID admission branches, late
tailer failure accounting, first product warm order, conflicting identity,
and separation of build workers from warm barrier waits.

The gate is nevertheless **REJECTED**. Two blocking fail-closed issues remain:

1. the watchdog is not a hard terminal bound once a warm future has started;
2. `post_chat()` can classify an incomplete streaming response as finished.

These findings prevent a safe P0 vehicle acceptance even though the focused
fixture and static checks pass.

## Findings

### F-7 — BLOCKING: submitted warm worker can outlive the watchdog and delay final accounting

- Location: `p0_session_barrier_vehicle.py:986-1057`, especially the
  `ThreadPoolExecutor` context and `future.result(timeout=...)` at
  `:1051-1057`.
- Evidence: an independent local probe made the admitted warm worker sleep for
  `0.20s` with `watchdog_s=0.03`. The scheduler recorded
  `warm worker exceeded watchdog timeout`, but `_run_warm_scheduler()` returned
  after approximately `0.201s`, not at the watchdog deadline, because leaving
  the executor context performs `shutdown(wait=True)` for the still-running
  future.
- Acceptance impact: the claimed watchdog bound does not bound the scheduler
  or the final bundle. A hung or indefinitely slow warm call can prevent final
  accounting and verdict emission indefinitely. The focused watchdog fixture
  only exercises sessions still waiting for barriers; it does not exercise a
  submitted future that exceeds the deadline.
- Required closure: make timeout handling terminal for the scheduler lifecycle
  (or explicitly prove the HTTP worker cannot outlive the deadline under the
  accepted transport contract) and add a focused regression for a submitted
  warm future exceeding the watchdog, including final accounting.

### F-8 — BLOCKING: incomplete SSE response with an ID is admitted as `finished=True`

- Location: `p0_session_barrier_vehicle.py:518-543` and `:576-600`, with the
  admission result derived at `:593`.
- Evidence: an independent local `post_chat()` probe supplied HTTP 200 and a
  single SSE data line containing `id="partial-id"` but no terminal
  `finish_reason`/completion marker. The returned metrics were:
  `{'http': 200, 'finished': True, 'rid': 'partial-id',
  'rid_source': 'response.id', 'finish_reason': None}`.
  The expression at `:593` treats any non-empty 200 body as finished.
- Acceptance impact: the FIX1/FIX2 HTTP/finished/`response.id` gate can admit a
  truncated or otherwise incomplete streamed build or warm response. That
  response can establish a build context or enter warm/restore accounting,
  violating the required fail-closed response boundary and weakening final
  PASS evidence.
- Required closure: require the protocol's terminal completion evidence for a
  streamed response (and reject incomplete/ambiguous bodies), then add focused
  build and warm probes showing HTTP 200 + ID without completion remains
  terminally invalid.

## Requirement review

| Requirement | Result | Evidence |
|---|---|---|
| F-6 early product warm-before-barrier | PASS for the exercised path | Independent reducer probe and the new focused scheduler fixture retained `lookup_before_barrier=True`, returned `ready_for_warm=False`, recorded `lookup_before_barrier`, and made zero warm calls. |
| Build HTTP/finished/response.id admission | **REJECT** | Synthetic invalid HTTP/finished/ID branches pass, but the actual `post_chat()` parser admits an incomplete 200 SSE response as finished (F-8). |
| Warm HTTP/finished/response.id admission | **REJECT** | The scheduler branch rejects missing/invalid metrics, but it trusts the same incomplete-response parser (F-8). |
| Late tailer error | PASS | Focused fixture and independent late-error path record a terminal fatal after restore/future handling. |
| First product warm order | PASS | Focused fixture preserves the first product lookup order over the later vehicle marker. |
| Conflicting exact identity | PASS | Focused fixture produces two identities, `invalid_join=True`, and `ready_for_warm=False`. |
| Original build scheduling deadlock | PASS | Independent 3-session/2-worker probe observed 3 build calls, 3 contexts, zero readiness checks during build, and no fatal errors. |
| Watchdog and final accounting | **REJECT** | Barrier-pending watchdog path passes, but a submitted future exceeds the deadline and executor shutdown waits (F-7). |
| Static/focused checks | PASS | Focused fixture, `py_compile`, AST parse, and whitespace checks all passed. |
| Remote/live validation | NOT RUN | Prohibited by dispatch; supplied FIX2 live report remains `NOT_VERIFIED`. |

## Evidence executed

- `PYTHONPYCACHEPREFIX=/tmp/codex-pycache-review-fix3 python3 test_p0_trace_context_v4.py` — **PASS**.
- `PYTHONPYCACHEPREFIX=/tmp/codex-pycache-review-fix3 python3 -m py_compile p0_session_barrier_vehicle.py test_p0_trace_context_v4.py` — **PASS**.
- Independent `ast.parse` over both authorized files — **PASS**.
- `git diff --no-index --check /dev/null` over both untracked authorized files — **PASS**.
- Independent F-6 reducer/scheduler probe — **PASS** for zero warm submissions.
- Independent original build deadlock probe — **PASS** for 3 builds with zero readiness checks during build.
- Independent submitted-worker watchdog probe — **FAIL** for the hard deadline: `0.201s` elapsed with a `0.03s` watchdog.
- Independent incomplete-SSE response probe — **FAIL-CLOSED VIOLATION**: HTTP 200 + response ID + no completion marker returned `finished=True`.
- No engine, launcher, remote host, live endpoint, or remote command was started.

## Supplied live evidence

`TEST-20260908-P0-S25-LIVE-FIX2.md` remains terminal
`NOT_VERIFIED`/fail-closed. It contains no exact final-node durability
barriers, warm requests, or restore successes and is not acceptance evidence
for FIX3.

## Followups

- Fresh coder Task ID: close F-7 with a hard watchdog/final-accounting design
  and regression.
- Fresh coder Task ID: close F-8 with strict streamed-response completion
  admission and build/warm regressions.
- Fresh independent reviewer Task ID: rerun this gate after both repairs.
- Keep live S=25 validation blocked until a fresh gate accepts the vehicle.

## Open issues

1. F-7 submitted-worker watchdog overrun remains blocking.
2. F-8 incomplete streamed response admission remains blocking.
3. Supplied FIX2 live evidence remains `NOT_VERIFIED`; no runtime PASS is
   claimed.
4. The aggregate checkout has no task-specific commit boundary; the reviewed
   vehicle and fixture are untracked.

done
