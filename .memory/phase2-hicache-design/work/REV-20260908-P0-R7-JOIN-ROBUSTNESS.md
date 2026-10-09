# REV-20260908-P0-R7-JOIN-ROBUSTNESS

- Task ID / epoch: `REV-20260908-P0-R7-JOIN-ROBUSTNESS` / `2026-09-08`
- Role: `reviewer`
- Invocation status: `done`
- Admission: `ACCEPT`
- Gate verdict: **REJECT**

## Artifacts

- Gate report: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/review/gates/P0-R7-JOIN-ROBUSTNESS.md`
- Reviewed vehicle: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/p0_session_barrier_vehicle.py`
- Reviewed focused tests: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/test_p0_trace_context_v4.py`
- Reviewed emitter: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/python/sglang/srt/mem_cache/unified_radix_cache.py`

## Evidence

- Focused V4.3 checks: **PASS**.
- AST parse and `py_compile` for vehicle, focused test, and emitter: **PASS**.
- Valid fragment buffering, event order, and timeout check: **PASS**.
- Adversarial malformed-line check: **FAIL**. A complete malformed JSONL line
  followed by a valid event caused `EventTailer.wait_for` to return `True` even
  though `tailer.error` was set.
- The failure is at `EventTailer.wait_for` (`p0_session_barrier_vehicle.py:453-463`),
  which evaluates the readiness predicate before checking the sticky error;
  `_run` (`:439-445`) also continues after parse failure.
- FIX2 integer-node normalization, fail-closed emitter behavior, diagnostics
  default-off behavior, and build/barrier guard preservation: **PASS** by source
  inspection and focused fixture.
- No remote/live run was performed.

## Summary

The proposed R7 fix is partially correct: incomplete trailing fragments are
buffered until newline completion, valid event order and timeout behavior are
preserved, and build-complete diagnostics are marker-gated, reason-only, and do
not manufacture accepted evidence. The accepted FIX2 emitter semantics remain
intact.

The gate must reject because a malformed complete line does not remain
fail-closed when later valid evidence makes the readiness predicate true. This
can permit a warm request from a corrupted event stream and invalidates the
join-robustness acceptance requirement.

The requested `COD-20260908-P0-R7-JOIN-ROBUSTNESS` summary was not found in the
inspected workspace; the DEBUG report and accepted FIX2 gate were available.

## Followups

- Route the tailer repair to a fresh implementation Task ID.
- Add a deterministic malformed-before-valid readiness test.
- Re-run the independent reviewer gate before any new live run.

## Open issues

1. Blocking tailer fail-open after complete malformed JSONL.
2. Missing malformed-before-valid regression coverage.
3. Missing named R7 coder summary/provenance artifact.
4. Prior R7 live evidence remains `NOT_VERIFIED`; no new live run is permitted
   by this rejected gate.

