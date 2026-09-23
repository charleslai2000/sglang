STATUS: done

# P0 residency-barrier emitter FIX4 independent gate review

- Task ID: `REV-20260908-P0-RESIDENCY-BARRIER-EMITTER-FIX4`
- Orchestration epoch: `phase2-hicache-design / 2026-09-08`
- Role: `reviewer`
- Invocation status: `done`
- Admission: `ACCEPT`
- Gate verdict: `REJECT`

## Scope and independence

Reviewed the authorized product file and focused fixture directly, the FIX4
implementation report, accepted FIX3 gate, and authoritative contract/scope
closure. The worktree is dirty and has no task-specific commit boundary; review
attribution is limited to the authorized product/test paths and the FIX4
completion-trigger change. No product/test file, remote host, live environment,
vehicle, or launcher was modified. No remote or live claim is made.

## Blocking finding

### B1 — BLOCKER/P0: completion-triggered fold ignores outstanding release queues

- Location: `python/sglang/srt/mem_cache/unified_radix_cache.py:400-464`,
  especially the predicate block at `:424-440` and the FIX4 re-entry at
  `:395-397`.
- Evidence: `_t38c_residency_barrier` checks node/root/tombstone, V3 identity,
  build identity, durability readiness, a device detach, FULL/Mamba live-value
  absence, and all recorded keyed completions. It never reads
  `cache.cache_controller.host_mem_release_queue`,
  `extra_host_mem_release_queues`, or any outstanding queue digest. The FIX4
  completion hook calls this fold immediately after the last recorded token is
  completed, so a pending release queue cannot prevent publication.
- Independent probe: an AST-extracted product fold was given a cache with
  `host_mem_release_queue.empty() == False`; all expected device/host tokens
  were completed. The result was
  `Queue fail-open probe: BARRIER PUBLISHED WITH NON-EMPTY RELEASE QUEUE`.
- Contract evidence: the scope-closure acceptance rule requires the relevant
  Host release queues to contain no outstanding digest before the barrier
  (`ARCH-20260908-P0-SCOPE-CLOSURE.md:144-149`), and the prior evidence mapping
  requires no barrier while a release queue remains non-empty
  (`DBG-20260908-P0-RESIDENCY-EVIDENCE-MAPPING.md:88-91`). This also directly
  violates FIX4 acceptance criterion 4's queue predicate.
- Acceptance impact: the product can publish `cold_residency=true` before the
  corresponding release has actually drained, allowing a false cold state and
  unsafe downstream warm admission. The completion-triggered re-entry must
  preserve the same queue fail-closed condition as the accepted residency
  contract.

Required correction: add/restore an authoritative, target-scoped queue/digest
predicate to the existing strict fold and extend the focused fixture with a
non-empty relevant-queue negative case. Do not relax identity, token, live-value,
durability, root, or tombstone checks. This is a new implementation task and
requires a fresh Task ID.

## Requirement assessment

| Requirement | Result | Evidence |
|---|---|---|
| Completion trigger is product-owned and needs no later request/drain | PASS structurally | `_t38c_note_completion` re-enters `_t38c_residency_barrier` under the cache-owned `RLock`; focused no-next-request probe passed. |
| No-next-request: final exact token emits exactly one; repeat/poll stays one | PASS | `python3 test/registered/unit/mem_cache/test_p0_residency_barrier_emitter.py`; named no-next-request probe passed. |
| Six-field identity, cache-owned `RLock`, F-1/F-2/F-3/F-4 protections | PASS locally | Source review and focused fixture; F-3/F-4 output and recycle/cross-cache/concurrency checks passed. |
| No publication before expected tokens, queues, live values, build/durability, root/forced-miss predicates | **FAIL** | B1: expected tokens and other predicates are checked, but release queues are not inspected; independent fail-open probe published. |
| Missing/ambiguous, stale generation, partial/host-only, recycle, cross-cache, run-ID cases | PASS in fixture | Focused fixture output passed all named cases. |
| Focused/V4.3/static/adversarial checks | PARTIAL / gate fails | Focused emitter, V4.3, `py_compile`, AST, whitespace, and wrong-token/concurrent-duplicate probes passed; queue fail-open adversarial probe failed the required negative property. |
| No remote/live claim | PASS | No remote host or live run was used. |

## Independently executed evidence

From `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt`:

- `python3 test/registered/unit/mem_cache/test_p0_residency_barrier_emitter.py` — PASS.
- `python3 test/registered/unit/mem_cache/test_p0_trace_context_v4.py` — PASS.
- `PYTHONPYCACHEPREFIX=/tmp/codex-p0-residency-fix4-review-pycache python3 -m py_compile python/sglang/srt/mem_cache/unified_radix_cache.py test/registered/unit/mem_cache/test_p0_residency_barrier_emitter.py` — PASS.
- AST parse of both authorized files — PASS.
- Product `git diff --check` — PASS; untracked fixture no-index check had no diagnostics (expected status 1).
- Independent wrong-token, cross-cache-token, and concurrent duplicate-completion probes — PASS.
- Independent non-empty release-queue fail-open probe — **FAIL**, as described in B1.
- No pytest, engine, launcher, vehicle, remote, or live S=25 run was performed.

## Questions

None. The blocker is directly reproducible from the current product fold and
does not require external clarification.

## Status packet

- Status: `done`
- Artifacts: this gate and
  `.memory/phase2-hicache-design/work/REV-20260908-P0-RESIDENCY-BARRIER-EMITTER-FIX4.md`.
- Evidence: direct source review, FIX3/contract review, required focused/static
  checks, and independent adversarial probes.
- Summary: **REJECT FIX4** because completion-triggered residency publication is
  fail-open with a non-empty relevant release queue.
- Followups: fresh coder Task ID to restore the queue predicate and add the
  negative fixture; then a fresh independent reviewer gate.
- Open issues: B1 remains blocking; live/remote residency remains unverified.
