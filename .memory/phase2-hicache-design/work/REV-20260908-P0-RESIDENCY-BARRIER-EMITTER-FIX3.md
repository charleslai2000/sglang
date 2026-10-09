ENTRY: ACCEPT

STATUS: done

# REV-20260908-P0-RESIDENCY-BARRIER-EMITTER-FIX3

## Verdict

ACCEPT — FIX3 satisfies the local residency-barrier emitter gate. The two
blocking FIX2 findings are closed:

1. `_t38c_residency_identity` validates the required V3 context, including a
   non-empty string `run_id`, and returns the exact six-field identity
   `(run_id, session_id, session_generation, build_rid, node_id,
   final_kv_hash)`.
2. The focused fixture directly folds `None`, absent context, every missing V3
   field, and a node-context mismatch, asserting no event and no cache-owned
   ledger mutation.

## Scope and independence

Reviewed:

- `python/sglang/srt/mem_cache/unified_radix_cache.py`
- `3090-dev/test_p0_residency_barrier_emitter.py`
- FIX3 implementation report
- rejected FIX2 gate/report
- authoritative build-complete contract

The aggregate worktree is dirty without a task-specific commit boundary. The
FIX3 implementation report attributes the scoped change to the two authorized
files; unrelated dirty files were not attributed to FIX3. No product/test,
vehicle, launcher, remote, or live artifact was modified.

## Evidence

- Focused emitter fixture — PASS. It reports the F-3 run-ID collision probe,
  all F-4 invalid-context cases, and the complete emitter suite.
- V4.3 trace-context fixture — PASS.
- `py_compile` for the authorized product and focused test files — PASS.
- AST parse for both authorized files — PASS.
- Product `git diff --check` — PASS.
- Untracked test no-index whitespace check — expected status 1, no diagnostics.
- Independent probe of `_t38c_residency_identity` — missing, empty,
  whitespace-only, and non-string run IDs all returned `None`.
- Independent cross-run token probe — a `run-a` token was rejected by the
  `run-b` cache and did not complete or join its lifecycle ledger.

Source review confirms:

- `_t38c_residency_detached`, `_t38c_residency_completed`,
  `_t38c_residency_barriers`, `_t38c_build_identities`, and
  `_t38c_durability_ready` use the six-field identity.
- The cache lock covers detach registration, completion, polling/publication,
  reset, and session retirement.
- Publication requires successful build/durability readiness, a device detach,
  all expected token completions, no live FULL/Mamba values, and a non-root,
  non-forced-miss node. Publication is recorded only after the exact event is
  logged, so logger failure remains fail-closed.
- Queue drains record token completion and the final control-queue poll retries
  pending folds.

No remote/live execution or claim was made.

## Summary

FIX3 is accepted for the local independent implementation gate. F-1/F-2
protections remain intact, F-3 run-ID isolation is evidenced, and F-4 direct
residency invalid-context coverage is evidenced.

## Followups

- Run a separate authorized launcher/live task for fresh P0 residency and warm/
  restore evidence.
- Preserve an explicit task boundary before any broader merge/release review.

## Open issues

1. Live/remote residency and warm/restore behavior is outside this gate.
2. Aggregate dirty-worktree attribution has no task-specific commit boundary.

## Status packet

- Status: `done`
- Artifacts: `review/gates/P0-RESIDENCY-BARRIER-EMITTER-FIX3.md` and this report.
- Evidence: source inspection, contract/FIX2 comparison, focused/V4.3/static
  checks, and independent adversarial probes.
- Summary: local FIX3 gate ACCEPT.
- Followups: separate live/remote validation task.
- Open issues: no live claim; dirty attribution boundary.
