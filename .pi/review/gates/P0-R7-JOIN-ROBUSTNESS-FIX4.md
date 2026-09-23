ENTRY: ACCEPT

# P0 R7 join-robustness FIX4 independent gate

- Task ID: `REV-20260908-P0-R7-JOIN-ROBUSTNESS-FIX4`
- Orchestration epoch: `2026-09-08`
- Role: `reviewer`
- Invocation status: `done`
- Admission: `ACCEPT`
- Gate verdict: **REJECT**

## Scope and inputs

Read-only review of:

- `tools/p0_session_barrier_vehicle.py`
- `test/registered/unit/mem_cache/test_p0_trace_context_v4.py`
- current worktree diff and status
- rejected `review/gates/P0-R7-JOIN-ROBUSTNESS.md`
- architecture contract and accepted emitter gates
- R7 evidence, including `DEVOPS-20260908-P0-S25-LIVE-R7-EXACT.md`

No product, vehicle, launcher, ledger, remote, or live-run artifact was
modified by this review. The current checkout has a dirty aggregate worktree
with no task-specific commit boundary; unrelated pre-existing changes were not
silently attributed to FIX4.

## Findings

### F-1 — High / blocking: tailer readiness remains fail-open across a parse-error race

Location: `tools/p0_session_barrier_vehicle.py:439-447` and `453-464`.

FIX4 correctly moves the sticky-error check before the readiness predicate, but
the check and predicate are not an atomic decision. The parser assigns
`self.error` outside `self.condition` and continues after a complete malformed
line. `wait_for` checks `self.error`, then invokes `predicate()`, and never
rechecks the error before returning success. A complete malformed line can
therefore be observed while the predicate is running, after the initial error
check but before `wait_for` returns.

An independent deterministic probe entered the predicate, appended
`{malformed-race}` plus a newline, waited until `tailer.error` was populated,
then returned `True`. The observed result was:

```text
race_wait_result= True
race_tailer_error= invalid JSONL: Expecting property name enclosed in double quotes: line 1 column 2 (char 1)
race_probe= FAIL_OPEN
```

This still permits a caller to treat a corrupted event stream as ready when a
malformed record arrives concurrently with the readiness check. It violates
the required fail-closed behavior even though the simpler malformed-before-
valid regression now fails closed. The repair must make parse-error publication
and readiness success mutually ordered/atomic, or make parse failure terminal
and ensure readiness cannot return true after it.

Acceptance impact: **merge-blocking**. FIX4 does not yet establish the
error-before-predicate fail-closed contract under concurrent arrival.

### F-2 — Medium / blocking evidence gap: the focused fixture does not cover the race

Location: `test/registered/unit/mem_cache/test_p0_trace_context_v4.py:408-414`.

The new fixture appends a complete malformed line followed by a valid event and
asserts that `wait_for` returns false. That regression passes, but it does not
interleave a parse failure with an executing readiness predicate, so it cannot
lock the F-1 boundary. Add a deterministic predicate-controlled interleaving
that asserts `wait_for` is false whenever `tailer.error` becomes non-null before
the wait returns.

Acceptance impact: the required focused evidence is incomplete for the
fail-closed concurrency boundary.

## Requirement review

- Incomplete-fragment retry: **PASS**. An unterminated JSON object is retained
  in `pending` until a newline arrives; after completion it is parsed once and
  delivered in arrival order.
- Complete malformed line followed by valid event: **PASS** for the covered
  deterministic sequence. The valid record may still be ingested, but the
  sticky error is checked first and readiness remains false.
- Error-before-predicate fail-closed behavior: **FAIL** under F-1's concurrent
  boundary. The source order is improved, but the success decision is not
  synchronized with parse-error publication.
- Schema/identity/barrier gates: **PASS** by focused fixture and source
  inspection. The vehicle still requires exact `p0_durable.v3` records and the
  exact identity tuple, and still requires build, KV, Mamba, durability, and
  cold-residency ordering before warm issuance.
- Emitter guards and diagnostics: **PASS** for this review surface. The
  marker-gated reason-only diagnostic remains default-off at
  `unified_radix_cache.py:277-280`; the accepted emitter still preserves V3
  schema, request/build RID equality, finalized node/hash readback, TP leader
  gating, and fail-closed missing/invalid cases.
- R7 live evidence: **not acceptance evidence**. The supplied R7 run remains
  `NOT_VERIFIED` with 25 unresolved joins and zero restores; no new live run
  was started.

## Evidence executed

From `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt`:

- `PYTHONPYCACHEPREFIX=/tmp/codex-pycache-r7-fix4 python3 test/registered/unit/mem_cache/test_p0_trace_context_v4.py` — **PASS**.
- `PYTHONPYCACHEPREFIX=/tmp/codex-pycache-r7-fix4 python3 -m py_compile` over
  the vehicle, focused fixture, emitter, and related changed source files —
  **PASS**.
- Independent `ast.parse` over 9 reviewed vehicle/fixture/product files —
  **PASS**.
- `git diff --check` — **PASS**. The vehicle and fixture are untracked;
  `git diff --no-index --check /dev/null <file>` returned the expected status
  1 for each and produced no whitespace diagnostics.
- Independent fragment/retry, malformed-before-valid, and non-object-followed-
  by-valid probes — **PASS** for the deterministic cases.
- Independent predicate/parse-error interleaving probe — **FAIL** as shown in
  F-1: `wait_for` returned `True` while `tailer.error` was non-null.
- No engine, launcher, remote, deployment, or live run was started.

## Summary

FIX4 repairs the previously rejected deterministic boundary: valid incomplete
fragments are retried after newline completion, and a complete malformed line
followed by valid evidence no longer makes `wait_for` succeed. The accepted
V3 emitter, identity, schema, barrier, and diagnostic gates remain intact in
the reviewed source and focused fixture.

The gate nevertheless remains **REJECTED** because readiness can still return
true if a complete malformed line is parsed while the predicate is executing.
That is a direct fail-open path for the required event-stream safety contract.

## Followups

- Under a fresh implementation Task ID, make parse-error state publication and
  readiness success atomic/terminal; do not repair it in this review.
- Add and run the deterministic concurrent interleaving regression, then rerun
  this independent gate.
- Keep the no-live-run decision until the corrected gate is accepted; the prior
  R7 bundle remains `NOT_VERIFIED`.

## Open issues

1. F-1: concurrent parse-error/readiness race can return `True` after
   `tailer.error` is set.
2. F-2: focused fixture lacks the concurrent interleaving regression.
3. Prior R7 runtime evidence remains `NOT_VERIFIED` with 25 unresolved joins
   and zero restores.
4. The aggregate worktree is dirty and lacks a task-specific revision boundary.
