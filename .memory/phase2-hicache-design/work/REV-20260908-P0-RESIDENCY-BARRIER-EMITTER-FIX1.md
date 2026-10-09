STATUS: done

# REV-20260908-P0-RESIDENCY-BARRIER-EMITTER-FIX1

## Verdict

**REJECT** — the narrow emitter gate is not accepted.

The retry is product-owned and the nominal focused proof is green, but two
blocking boundary findings prevent acceptance:

1. `unified_radix_cache.py:398-418` deduplicates with a key containing the
   entire expected-token set. A second real detach/free cycle for the same
   exact `(run_id, session_id, session_generation, build_rid, node_id,
   final_kv_hash)` therefore emits a second residency barrier. Independent
   AST-extracted probing produced two records from two distinct lifecycle token
   sets for one identity.
2. `unified_radix_cache.py:143-147,378-430` stores retry state in module-global
   maps keyed only by node ID and mutates/iterates them without a common lock.
   An independent cross-cache probe seeded completion in cache A and caused
   cache B, with a different session/generation/build identity and no B detach,
   to publish using A's global expected set. This violates the no cross-node/
   session-join and concurrency boundary.

## Scope and independence

Reviewed the two authorized product files and focused fixture directly, plus
the supplied implementation/architecture/debugger reports and prior accepted
gates. The gate file was absent before review and was created as the gate
artifact. Product files and tests were not modified. No remote live run was
performed or claimed. The worktree is dirty without a task-specific commit;
the implementation report identifies Mamba instrumentation as pre-existing,
and this review did not attribute the aggregate dirty diff to FIX1.

## Acceptance evidence

- Focused emitter test: **PASS**.
- Trace-context focused test: **PASS**.
- `py_compile` for both product files and the focused test: **PASS**.
- AST parse for both product files and the focused test: **PASS**.
- `git diff --check` for authorized paths: **PASS**.
- Product retry placement: **PASS structurally**; the poll runs after queued
  release drains in `_drain_storage_control_queues_impl`.
- Exact V3 payload inputs and nominal fail-closed guards: **PASS by source and
  focused fixture**.
- Repeated lifecycle idempotency: **FAIL** (blocking F-1).
- Global ownership/concurrency isolation: **FAIL** (blocking F-2).
- Live S=25/runtime evidence: intentionally not run and not required for this
  rejection.

## Required follow-up

Under a fresh coder Task ID, make the barrier ledger ownership explicit and
atomic, scope expected/completed/publication state to the authoritative
run/session/generation/build/node/hash lifecycle, suppress duplicate logical
barriers across new token sets, and add focused tests for repeated recycle,
node-ID collision, multi-cache isolation, and concurrent polling. Then obtain a
fresh independent reviewer gate before any remote live run.

## Status packet

- Status: `done`
- Artifacts: `review/gates/P0-RESIDENCY-BARRIER-EMITTER-FIX1.md` and this report.
- Evidence: source inspection, focused/static checks, repeated-lifecycle probe,
  and cross-cache probe.
- Summary: product-owned retry is present, but the implementation is not
  acceptable for strict exact-identity residency evidence.
- Followups: fresh implementation and fresh independent review.
- Open issues: F-1 duplicate logical barrier; F-2 global cross-cache/session
  join and unsynchronized retry state; no live evidence.
