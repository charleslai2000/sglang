ENTRY: ACCEPT

# REV-20260908-P0-R7-JOIN-ROBUSTNESS-FIX4

- Task ID / epoch: `REV-20260908-P0-R7-JOIN-ROBUSTNESS-FIX4` / `2026-09-08`
- Role: `reviewer`
- Invocation status: `done`
- Admission: `ACCEPT`
- Gate verdict: **REJECT**

## Artifacts

- Gate report: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/review/gates/P0-R7-JOIN-ROBUSTNESS-FIX4.md`
- Reviewed vehicle: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/p0_session_barrier_vehicle.py`
- Reviewed focused fixture: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/test_p0_trace_context_v4.py`

## Evidence

- Focused V4.3 fixture: **PASS**.
- Compilation of vehicle, fixture, emitter, and related changed source files:
  **PASS**.
- AST parse of 9 reviewed files: **PASS**.
- `git diff --check` and untracked-file whitespace checks: **PASS** with no
  whitespace diagnostics.
- Incomplete-fragment retry and deterministic malformed-before-valid tests:
  **PASS**.
- Independent concurrent predicate/parse-error probe: **FAIL** —
  `EventTailer.wait_for` returned `True` after `tailer.error` became
  `invalid JSONL: ...`.
- No remote/live run was performed.

## Summary

FIX4 fixes the prior deterministic fail-open sequence and preserves the
accepted exact V3 schema/identity/barrier gates and marker-gated diagnostics.
However, `EventTailer._run` writes `self.error` without the condition lock and
`wait_for` does not recheck the error after executing its predicate. A malformed
complete record arriving during predicate evaluation can therefore produce a
successful readiness result for a corrupted stream. This is merge-blocking.

## Followups

- Fresh implementation task: make parse-error publication and readiness success
  atomic or terminal, and add the concurrent interleaving regression.
- Rerun the independent gate before authorizing any live run.

## Open issues

1. Blocking tailer error/readiness race (F-1).
2. Missing focused regression for that race (F-2).
3. Prior R7 live evidence is still `NOT_VERIFIED` (25 unresolved joins,
   zero restores).
4. Dirty aggregate worktree has no task-specific revision boundary.
