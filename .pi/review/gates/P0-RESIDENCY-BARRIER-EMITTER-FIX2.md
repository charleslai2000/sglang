# P0 residency-barrier emitter FIX2 independent gate review

- Task ID: REV-20260908-P0-RESIDENCY-BARRIER-EMITTER-FIX2
- Orchestration epoch: phase2-hicache-design / 2026-09-08
- Role: reviewer
- Invocation status: done
- Admission: ACCEPT
- Gate verdict: REJECT

## Scope and independence

Reviewed the authorized product files and focused emitter test directly, the
FIX2 implementation report, the rejected FIX1 gate/report, and the
authoritative build-complete contract. The worktree is a pre-existing dirty
worktree without a task-specific commit boundary; the implementation report
attributes only unified_radix_cache.py and the focused test to FIX2 and states
that Mamba changes were pre-existing. This review did not attribute the
aggregate dirty diff to FIX2.

No product file, test, vehicle, remote host, or launcher was modified. Only
the authorized gate and report artifacts were written. No live or remote claim
is made.

## Verdict summary

FIX2 closes the two specific FIX1 mechanics for the five-field identity tested:
the residency ledger is cache-owned, the cache lock surrounds the ledger
mutations, publication is keyed independently of the physical token set, and
same-node cross-cache completion is rejected by exact token ownership. The
focused emitter and V4.3 suites pass.

The gate remains REJECTED because the implementation does not use the
authoritative six-field logical identity. It omits run_id, which the contract
makes mandatory and which is explicitly part of
B=(run_id, session_id, session_generation, build_rid, node_id, final_kv_hash).
The required missing-context residency case is also not independently covered
by the supplied emitter test.

## Blocking findings

### F-3 — BLOCKING: residency identity omits mandatory run_id

Location: python/sglang/srt/mem_cache/unified_radix_cache.py:146-167,
:330-341, :374-375, and :5331-5339.

_t38c_residency_identity() validates V3/session/generation/build/node/hash but
returns only:

    (session_id, session_generation, build_rid, node_id, final_kv_hash)

The durable logger adds run_id later from the current environment, but that
run ID is not part of the cache-owned build, detach, completion, readiness, or
publication keys. The authoritative contract requires
B=(run_id, session_id, session_generation, build_rid, node_id, final_kv_hash)
and says engine relaunches require a fresh run ID.

Independent AST-extracted probe: two otherwise identical V3 contexts carrying
run-A and run-B produced the same five-field identity
('s', 1, 'b', 'node', 'hash'); the probe reported
run_id_distinguished: False.

Acceptance impact: a run boundary is not represented in the retry/dedup
ledger. A stale or reused cache lifecycle can therefore collide with a new
run, suppress a valid barrier, or associate a barrier's current logger
envelope with state registered under another run. This violates the exact
identity criterion and the contract's cross-run isolation rule.

Required follow-up: carry an authoritative non-empty run ID into the
residency logical identity and every associated state key, preserve it in the
published V3 payload, and add a regression probe that changes only run ID.
Do not weaken the vehicle to ignore the missing field.

### F-4 — BLOCKING acceptance-evidence gap: missing residency context is not tested

Location: test/registered/unit/mem_cache/test_p0_residency_barrier_emitter.py:126-299.

The focused emitter fixture constructs every cache with a complete V3 context.
It tests warm ambiguity, stale generation, host-only/partial detach,
durability absence, forced-miss, repeated polling, repeated recycle, and
same-node cache isolation, but it does not invoke the residency fold with a
missing context or with missing V3 identity fields. The missing-context cases
in test_p0_trace_context_v4.py exercise the build-complete emitter, not the
residency barrier functions under review.

Acceptance impact: criterion 5 requires an independent missing/ambiguous
context test. Source inspection indicates the identity helper is intended to
fail closed, but the required evidence is absent, so the FIX2 gate cannot be
accepted.

Required follow-up: add focused residency cases for None/absent context,
missing schema/session/generation/build/node/hash, and node-context mismatch;
assert no event and no ledger mutation in each case.

## Requirement assessment

| Requirement | Result | Evidence |
|---|---|---|
| F-1 repeated recycle deduplication | PASS for the implemented five-field key | Focused test uses a distinct second digest/token set and observes one event. |
| F-2 cache ownership and same-node isolation | PASS for the exercised distinct-context path | Per-cache ledgers/lock are present; explicit cross-cache token is rejected. |
| Concurrent poll/release fail-closed behavior | PASS in focused fixture | Concurrent completion/poll handoff completes with one publication; polling snapshots identities before calls. |
| Strict producer predicates | PASS structurally for exercised path | V3, build/durability membership, device detach, exact completed tokens, live-value absence, root/tombstone suppression, and post-drain poll are present. |
| Exact six-field identity including run_id | REJECT | F-3: identity tuple is five fields and run ID is added only by the logger. |
| Required boundary tests | REJECT | F-4: no missing residency-context case in the focused emitter suite. |
| Exact payload/order and no remote/live claim | PASS structurally; live unverified | Product logger/event placement is preserved; no remote run performed. |
| Focused/static checks | PASS | Focused emitter, V4.3, py_compile, AST, and whitespace checks pass. |

## Evidence executed

From /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt:

- python3 test/registered/unit/mem_cache/test_p0_residency_barrier_emitter.py — PASS.
- python3 test/registered/unit/mem_cache/test_p0_trace_context_v4.py — PASS.
- PYTHONPYCACHEPREFIX=/tmp/codex-p0-residency-fix2-review-pycache
  python3 -m py_compile over both authorized product files and the focused
  test — PASS.
- ast.parse over both authorized product files and the focused test — PASS.
- Tracked authorized-path git diff --check — PASS.
- Untracked focused-test no-index whitespace check — PASS with no diagnostics
  and expected status 1.
- Independent run-ID identity probe — FAIL for acceptance: two run IDs
  collide in the residency identity.
- Source ownership probe — cache-owned residency lock and lock-guarded helper
  paths are present.
- No pytest, engine, remote, launcher, or live S=25 run was performed.

## Followups

- Fresh coder Task ID: include run ID in the authoritative residency identity
  and its lifecycle state, preserving fail-closed behavior.
- Fresh coder/test Task ID: add focused direct missing-residency-context and
  run-boundary probes.
- Fresh reviewer Task ID: rerun the complete focused/adversarial suite and
  inspect the new exact diff before any live acceptance task.

## Open issues

1. Gate is REJECTED on F-3 and F-4.
2. No live residency/warm/restore evidence is claimed.
3. The aggregate worktree remains dirty without a task-specific commit
   boundary; FIX2 attribution is based on the supplied implementation report
   and current source inspection.

## Status packet

- Status: done
- Artifacts: this gate file and
  .memory/phase2-hicache-design/work/REV-20260908-P0-RESIDENCY-BARRIER-EMITTER-FIX2.md.
- Evidence: source review, supplied reports/contracts, focused/static checks,
  and an independent run-ID collision probe.
- Summary: FIX1's five-field F-1/F-2 mechanics are improved, but the required
  six-field identity and missing-context evidence are not complete.
- Followups: fresh implementation/test/review Task IDs as listed above.
- Open issues: F-3, F-4, no live evidence, dirty attribution boundary.
