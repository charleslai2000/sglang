ENTRY: ACCEPT

# REV-20260908-P0-R7-JOIN-ROBUSTNESS-FIX5

- Task ID / epoch: `REV-20260908-P0-R7-JOIN-ROBUSTNESS-FIX5` / `2026-09-08`
- Role: `reviewer`
- Invocation status: `done`
- Admission: `ACCEPT`
- Gate verdict: **ACCEPT** for FIX5 tailer/fixture robustness only

## Artifacts

- Gate report: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/review/gates/P0-R7-JOIN-ROBUSTNESS-FIX5.md`
- Reviewed vehicle: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/p0_session_barrier_vehicle.py`
- Reviewed focused fixture: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/test_p0_trace_context_v4.py`

## Evidence

- Focused V4.3 fixture: **PASS**.
- Vehicle, fixture, emitter, trace-context, controller, and HiRadix compilation:
  **PASS**.
- AST parse of six reviewed files: **PASS**.
- Structural synchronization probe: **PASS**; parse-error publication and
  notification are condition-locked, with pre- and post-predicate error checks.
- Independent concurrent malformed-line reproduction: **PASS**, 40/40
  predicate-controlled iterations returned false after error publication.
- Independent incomplete-fragment retry and malformed-complete fail-closed
  probe: **PASS**.
- Tracked and untracked diff whitespace checks: **PASS** with no diagnostics.
- Isolated dry-run bundle: **PASS** for parser/reducer-only evidence (25 rows,
  zero reducer errors, execution not started, verdict `NOT_VERIFIED`).
- No remote/live run was performed.

## Summary

FIX5 repairs the FIX4 race rejection. The tailer publishes sticky parse errors
and notifies waiters while holding the same condition used by `wait_for`.
`wait_for` checks the error before and after predicate evaluation and holds the
condition through the final success decision. The prior concurrent malformed
line boundary now fails closed, incomplete fragments remain retryable, and
complete malformed records remain fatal for readiness waits.

Independent inspection found no weakening of the exact `p0_durable.v3` schema,
the `(session_id, build_rid, node_id, final_kv_hash)` identity join, ordered
KV/Mamba/durability/residency barriers, or accepted V3 emitter guards.

## Findings

No blocking or non-blocking findings.

## Followups

- A fresh authorized runtime task must independently validate R7 with a new
  evidence namespace before any live acceptance decision.
- Preserve the supplied failed R7 bundle as diagnostic evidence.

## Open issues

1. Supplied R7 runtime evidence remains `NOT_VERIFIED` with 25 unresolved joins
   and zero restores; FIX5 does not change that result.
2. The aggregate checkout is dirty and lacks a task-specific revision boundary,
   limiting broad diff attribution.

