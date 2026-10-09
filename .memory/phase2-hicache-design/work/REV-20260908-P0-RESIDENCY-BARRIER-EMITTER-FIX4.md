STATUS: done

# REV-20260908-P0-RESIDENCY-BARRIER-EMITTER-FIX4

- Task ID: `REV-20260908-P0-RESIDENCY-BARRIER-EMITTER-FIX4`
- Orchestration epoch: `phase2-hicache-design / 2026-09-08`
- Invocation status: `done`
- Admission: `ACCEPT`
- Verdict: `REJECT`

## Summary

FIX4 is not accepted. The new completion-triggered re-entry is product-owned,
reentrant under the cache-owned `RLock`, and passes the no-next-request focused
case. However, the strict fold it re-enters does not check outstanding host
release queues. Therefore the final keyed completion can publish
`residency_barrier(cold_residency=true)` while a relevant release queue is still
non-empty.

## Finding

### B1 — BLOCKER/P0: release-queue predicate is missing

Location: `python/sglang/srt/mem_cache/unified_radix_cache.py:400-464`;
FIX4 re-entry at `:395-397`.

Evidence:

- The fold checks identity, build/durability readiness, device detach, live
  FULL/Mamba values, and every recorded keyed completion.
- It never inspects `cache.cache_controller.host_mem_release_queue`, extra host
  release queues, or outstanding target digests.
- A read-only adversarial probe modeled `host_mem_release_queue.empty() == False`,
  completed all expected tokens, and observed:
  `Queue fail-open probe: BARRIER PUBLISHED WITH NON-EMPTY RELEASE QUEUE`.
- The authoritative scope closure requires no outstanding relevant queue digest
  before publication (`ARCH-20260908-P0-SCOPE-CLOSURE.md:144-149`), and the
  evidence mapping requires no barrier while a release queue remains non-empty
  (`DBG-20260908-P0-RESIDENCY-EVIDENCE-MAPPING.md:88-91`).

Impact: the product can assert cold residency before the physical release is
complete, violating acceptance criterion 4 and potentially admitting an unsafe
warm transition.

## Passing evidence

- Focused emitter fixture: PASS, including no-next-request final-token trigger,
  F-3 run-ID collision, F-4 invalid contexts, recycle, cross-cache, and
  concurrency cases.
- V4.3 trace-context fixture: PASS.
- `py_compile`: PASS.
- AST parse: PASS.
- Product whitespace check and untracked fixture whitespace scan: PASS with no
  diagnostics.
- Independent wrong-token, cross-cache, and concurrent duplicate probes: PASS.
- No remote/live execution or claim.

## Required followup

Fresh implementation Task ID: restore an authoritative target-scoped queue/digest
predicate in the strict fold and add a focused non-empty-queue negative case;
then dispatch a fresh independent reviewer. Preserve all existing identity,
token, live-value, durability, root, forced-miss, and at-most-once protections.

## Open issues

- B1 is blocking and prevents gate acceptance.
- Live S=25/remote behavior remains a separate task and was not claimed.

## Artifacts

- Gate: `review/gates/P0-RESIDENCY-BARRIER-EMITTER-FIX4.md`
- Implementation report:
  `.memory/phase2-hicache-design/work/COD-20260908-P0-RESIDENCY-BARRIER-EMITTER-FIX4.md`
