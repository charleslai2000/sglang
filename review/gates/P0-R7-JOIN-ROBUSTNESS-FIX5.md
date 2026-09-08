ENTRY: ACCEPT

# P0 R7 join-robustness FIX5 independent gate

- Task ID: `REV-20260908-P0-R7-JOIN-ROBUSTNESS-FIX5`
- Orchestration epoch: `2026-09-08`
- Role: `reviewer`
- Invocation status: `done`
- Admission: `ACCEPT`
- Gate verdict: **ACCEPT** (FIX5 tailer/fixture robustness scope only)

## Scope and inputs

Read-only review of:

- `3090-dev/p0_session_barrier_vehicle.py`
- `3090-dev/test_p0_trace_context_v4.py`
- current worktree status and diff
- prior `review/gates/P0-R7-JOIN-ROBUSTNESS-FIX4.md`
- prior memory report `REV-20260908-P0-R7-JOIN-ROBUSTNESS-FIX4.md`
- accepted `P0-BUILD-COMPLETE-EMITTER-FIX1.md` and `P0-BUILD-COMPLETE-EMITTER-FIX2.md`
- R7 diagnosis and runtime evidence, including `DEBUG-20260908-P0-R7-MISSING-BUILD-JOIN.md` and `DEVOPS-20260908-P0-S25-LIVE-R7-EXACT.md`

No product, vehicle, launcher, ledger, remote, or live-run artifact was
modified by this review. The aggregate checkout remains dirty and has no
task-specific commit boundary; existing changes were not attributed to FIX5
beyond the explicitly reviewed source and fixture.

No repository-root `AGENTS.md` exists in either target repository. The only
discovered `docs/AGENTS.md` files are documentation-scoped and do not govern
the reviewed Python/vehicle files; the supplied orchestration contract was
followed.

## Findings

No blocking or non-blocking implementation findings identified for FIX5.

## Requirement review

### Parse-error publication and condition synchronization — PASS

`EventTailer._publish_error_locked` stores the sticky error and calls
`notify_all()` while the condition is held (`p0_session_barrier_vehicle.py:421-424`).
`_run` parses complete lines while holding the same condition and publishes
JSON decode/non-object failures through that locked helper
(`p0_session_barrier_vehicle.py:446-454`). Normal event ingestion is followed
by a condition notification (`:455-457`), and the OSError path uses the locked
publication helper (`:458-459`).

### Pre- and post-predicate error checks — PASS

`wait_for` checks `self.error` before invoking the readiness predicate and
checks it again after the predicate returns, while holding the condition before
success can be returned (`p0_session_barrier_vehicle.py:461-476`). This closes
the FIX4 race: a malformed complete line published while the predicate is
executing prevents a `True` result, and the parser cannot publish a new error
between the post-check and success return because the same condition is held.

### Incomplete-fragment retry — PASS

An unterminated trailing fragment remains in `pending` and is not parsed until
the subsequent read completes it with a newline
(`p0_session_barrier_vehicle.py:433-445`). The focused fixture covers this
sequence at `test_p0_trace_context_v4.py:380-408`; an independent probe also
confirmed no premature event followed by ordered delivery after completion.

### Complete malformed input fail-closed — PASS

Malformed complete JSONL sets a sticky error, wakes waiters, and cannot satisfy
`wait_for`, even when a later valid event is ingested. The focused fixture
covers malformed-before-later-valid input at
`test_p0_trace_context_v4.py:409-417`, and the predicate-controlled race is
covered at `:420-444`.

### Schema, identity, and barrier preservation — PASS

The vehicle still requires `p0_durable.v3` and the exact identity tuple
`(session_id, build_rid, node_id, final_kv_hash)` (`p0_session_barrier_vehicle.py:32-33`).
`Reducer.ingest` continues to reject schema/run mismatches, missing scoped
session IDs, incomplete identity, and RID conflicts
(`:210-245`). Warm readiness still requires build identity, explicit KV and
Mamba durability, ordered combined durability, cold residency, and no invalid
join/barrier error (`:343-354`). Warm issuance remains guarded by the durable
and cold predicates (`:323-341`), and final verdict logic still requires exact
identity, ordered barriers, successful restore, warm issuance, successful HTTP,
and completed warm response (`:678-701`). No schema, identity, or barrier
weakening was introduced by FIX5.

### Accepted emitter gates and diagnostics — PASS / unchanged

The accepted FIX1/FIX2 emitter gates remain the authoritative unit acceptance
for V3 producer identity, finalized node/hash readback, TP-leader gating,
conflict handling, and fail-closed lifecycle guards. The focused fixture still
executes those checks and passes. FIX5 changes only tailer synchronization and
its focused regression; it does not synthesize events or relax emitter guards.

### R7 runtime evidence — not acceptance evidence

The supplied R7 evidence remains terminal `NOT_VERIFIED`: 25 unresolved joins,
zero restore successes, and the prior transient malformed-line/tailer failure
diagnosis. No remote or live rerun was performed or authorized by this review.
This FIX5 gate therefore does not promote R7 to runtime acceptance.

## Evidence executed

From `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt`:

- `PYTHONPYCACHEPREFIX=/tmp/codex-pycache-r7-fix5 python3 3090-dev/test_p0_trace_context_v4.py` — **PASS** (`P0 trace-context V4.3 focused checks: PASS`).
- `PYTHONPYCACHEPREFIX=/tmp/codex-pycache-r7-fix5 python3 -m py_compile` over the vehicle, focused fixture, emitter, trace-context, controller, and HiRadix files — **PASS**.
- Independent `ast.parse` over those six reviewed files — **PASS**.
- Structural AST probe — **PASS**: the tailer uses locked error publication/notification and `wait_for` contains both pre- and post-predicate error checks.
- Independent predicate-controlled concurrent malformed-line probe — **PASS**, 40/40 iterations returned `False` after the parse error was published.
- Independent fragment/malformed sequence probe — **PASS**: incomplete fragment was retried after newline completion; malformed complete input followed by valid input remained fail-closed.
- `git diff --check` on the changed tracked Python files — **PASS**.
- `git diff --no-index --check /dev/null` on the untracked vehicle and fixture — no whitespace diagnostics; status `1` only reflects the expected file difference from `/dev/null`.
- Isolated vehicle `--dry-run` bundle — **PASS** for parser/reducer evidence: 25 rows, zero reducer errors, `execution_started=false`, and verdict `NOT_VERIFIED`.
- No engine, launcher, remote, deployment, or live run was started.

## Summary

FIX5 closes the FIX4 blocking race. Parse failures are published and notified
under the same condition used by `wait_for`; readiness checks the sticky error
both before and after predicate evaluation and holds the condition across the
final success decision. The focused fixture and independent 40-iteration race
probe reproduce the prior boundary and now fail closed. Incomplete fragments
remain retryable, while complete malformed records remain terminal for waits.

The exact V3 schema/identity join, ordered durability/residency barriers,
accepted emitter gates, and fail-closed final verdict logic remain intact. The
verdict is **ACCEPT for FIX5’s narrow robustness gate only**; the historical R7
live result remains `NOT_VERIFIED` and still requires a separate authorized
runtime task.

## Followups

- Preserve the no-live-run decision until a fresh authorized runtime task
  independently validates the repaired vehicle against a new evidence bundle.
- Keep the prior R7 evidence unchanged as a failed diagnostic baseline.

## Open issues

1. R7 live acceptance remains outstanding: 25 unresolved joins and zero
   restores in the supplied run.
2. The aggregate worktree is dirty and has no task-specific revision boundary,
   so broad authorship attribution remains a process caveat.

