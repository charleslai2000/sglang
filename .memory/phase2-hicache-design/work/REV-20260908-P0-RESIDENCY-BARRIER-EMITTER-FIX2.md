STATUS: done

# REV-20260908-P0-RESIDENCY-BARRIER-EMITTER-FIX2

## Verdict

REJECT — FIX2 does not satisfy the residency barrier gate.

The per-cache ledger/lock repair closes the previously observed five-field
F-1/F-2 failures in the supplied focused fixture: repeated physical recycle
does not republish, and a same-node cache cannot complete another cache's
token. The gate is still blocked by:

1. F-3 (blocking): _t38c_residency_identity at
   unified_radix_cache.py:146-167 omits run_id, returning
   (session_id, session_generation, build_rid, node_id, final_kv_hash).
   The authoritative contract requires
   B=(run_id, session_id, session_generation, build_rid, node_id,
   final_kv_hash). _t38c_durable_log adds the current run ID only after the
   residency ledger keys have already been formed.
2. F-4 (blocking evidence gap): the focused residency test has no missing
   context/missing V3-field case. Its missing-context coverage belongs to the
   build-complete emitter fixture, not the residency fold under review.

An independent AST probe changed only run_id from run-A to run-B and observed
the same identity tuple, proving the first blocker.

## Scope and independence

Reviewed the authorized product files and focused test directly, plus the FIX2
implementation report, rejected FIX1 gate/report, and authoritative contract.
The worktree has pre-existing dirty changes and no task-specific commit
boundary. The implementation report attributes FIX2 to
unified_radix_cache.py and the focused test and says Mamba changes were
pre-existing; this review did not silently attribute aggregate dirty changes
to FIX2.

No product/test/vehicle/remote files were modified. Only the authorized gate
and report artifacts were written. No live or remote claim is made.

## Evidence

- Focused emitter: PASS —
  python3 3090-dev/test_p0_residency_barrier_emitter.py.
- V4.3 suite: PASS —
  python3 3090-dev/test_p0_trace_context_v4.py.
- py_compile for both authorized product files and the focused test: PASS.
- AST parse for both authorized product files and the focused test: PASS.
- Tracked authorized-path git diff --check: PASS.
- Untracked focused-test no-index whitespace check: PASS with no diagnostics
  and expected status 1.
- Independent run-ID collision probe: FAIL for acceptance.
- Independent source probe confirms cache-owned lock fields and lock-guarded
  residency helper paths.
- No pytest, engine, remote, launcher, or live S=25 execution.

## Requirement assessment

- F-1 repeated-token-set deduplication: PASS for the five-field key tested.
- F-2 cache ownership/same-node isolation: PASS for the exercised distinct
  context path.
- Concurrent poll/release and stale-owner rejection: PASS in the focused
  fixture.
- Strict V3/durability/device/live-value/root/forced-miss predicates: PASS
  structurally for exercised paths.
- Exact six-field identity: FAIL (F-3).
- Missing residency-context independent test: FAIL (F-4).
- Exact payload/order: PASS structurally; runtime unverified.

## Required follow-up

Under fresh Task IDs, carry an authoritative non-empty run_id into the
residency identity and every lifecycle state key, keep the published V3
payload consistent, and add direct missing-context/missing-field/node-context
mismatch cases for the residency fold. Then obtain a fresh independent review
of the exact diff before any live task.

## Open issues

1. F-3 run-ID omission remains blocking.
2. F-4 missing residency-context evidence remains blocking.
3. Live residency/warm/restore behavior is unverified.
4. Aggregate dirty-worktree attribution remains a caveat.

## Status packet

- Status: done
- Artifacts: review/gates/P0-RESIDENCY-BARRIER-EMITTER-FIX2.md and this report.
- Evidence: source inspection, implementation/contract review,
  focused/static checks, and independent run-ID probing.
- Summary: reject FIX2; the five-field F-1/F-2 repair is insufficient for the
  required six-field identity and complete boundary evidence.
- Followups: fresh implementation/test/review Task IDs.
- Open issues: F-3, F-4, no live evidence, dirty attribution boundary.
