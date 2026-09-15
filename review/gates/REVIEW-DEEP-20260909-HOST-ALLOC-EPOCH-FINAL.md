# Deep Final Review: Host Allocation Epoch

## Dispatch

- Task ID: `REVIEW-DEEP-20260909-HOST-ALLOC-EPOCH-FINAL`
- Orchestration epoch: `20260909-P4`
- Role: `reviewer-deep`
- Reviewed commit: `ebaf9e5c499ce6b4f2cbd10d3bc69e51350f7038`
- Branch: `3060-12g-qwen35-4b`
- Scope: read-only review of this repository; this report is the only written artifact

## Verdict

**REJECT** — blocking findings remain. The commit is not ready for the final gate.

Invocation status: **done**.

## Evidence and executed checks

- The commit is exactly the requested seven-file change. No sibling 3090 repository,
  remote, storage, or unrelated product file is changed by the commit.
- `PYTHONDONTWRITEBYTECODE=1 python3 3090-dev/test_drain_reentry.py`: **31/31 passed**.
- `PYTHONDONTWRITEBYTECODE=1 python3 3090-dev/test_hicache_restore.py`: **92/92 passed**.
  The required dependency-free bundle is therefore **123/123 passed**.
- `py_compile` passed for the changed Python files and the directly involved
  `hicache_restore.py` module.
- `git diff --check ebaf9e5c49^ ebaf9e5c49` passed.
- Registered test collection was separately attempted and was blocked by missing
  environment dependencies, not assertion failures:
  - `registered.unit.managers.test_hicache_host_allocability`: `ModuleNotFoundError: orjson`.
  - `registered.unit.mem_cache.test_mem_pool_host`: `ModuleNotFoundError: torch`.
  - `3090-dev/test_hicache_restore_scheduler_feed.py`: `ModuleNotFoundError: orjson`.

No “stale fixture” disposition is used. The compatibility fixtures cited below are
present in the checked-out test corpus and were inspected as current evidence.

## Previously registered findings

The following prior findings are resolved or materially addressed in the reviewed diff:

- Effective zero-unit lock-release changes now advance the relevant generation once;
  direct probing produced generation/telemetry sequence `1/1`, then `2/2` after a
  subsequent effective evictable change. The zero-unit event records numeric zero
  telemetry safely.
- Auxiliary transfers are released before the host-allocation failure snapshot in both
  failure paths. The snapshot therefore observes post-drain state, removing the
  previously identified same-request self-wake boundary.
- `restore_hybrid_finalize` is emitted on both accepted and discarded hybrid outcomes,
  with bounded-looking field shape, IDs, per-sidecar counts, and result fields.
- Callback-absent host rollback now calls `free` before conditionally notifying the
  observer, preserving the HiRadix path where the callback is absent.
- The KV-only arbitrary crop is not called by the allocation drain path; the relevant
  static guard and dependency-free tests pass.
- FIFO waiter removal is immediate on terminal transitions, and the pure arbiter probe
  showed no same-generation self-wake (`first=r`, then `None` after post-cleanup, then
  `r` after a new generation).
- The scheduler wake decision is coalesced/capped per request/attempt/generation key,
  and the dependency-free FIFO/no-spin, budget, hybrid, and cleanup tests pass.

These passes do not clear the blocking defects below.

## Blocking findings

### F-HAE-FINAL-01 — P1 — optional duck-typed transfer compatibility is broken

The new `_host_alloc_hybrid_is_all_or_nothing` helper directly evaluates
`transfer.hit_policy` at `python/sglang/srt/mem_cache/unified_radix_cache.py:5648`.
The companion sidecar-count helper directly evaluates `transfer.indices_from_pool` and
then `transfer.keys`.

Existing current test fixtures use duck-typed `SimpleNamespace` transfers with
`name`, `keys`, and `indices_from_pool`, but without `hit_policy`, including:

- `3090-dev/test_storage_regression.py:2531-2535`
- `3090-dev/test_prefetch_budget_split_unit.py:358-362`

Direct source-loaded probing of the changed helper with that shape reproduces:

```text
AttributeError: 'types.SimpleNamespace' object has no attribute 'hit_policy'
```

The helper is called from `_handle_prefetch_result` before hybrid finalization returns,
so this is a deterministic compatibility failure, not merely an unexecuted test label.
The full supplemental fixtures cannot currently be collected because of the separately
registered `orjson`/`torch` dependency block; that does not weaken the direct failure
reproduction.

Disposition: **block merge**. Use safe optional accessors/defaults for observational
telemetry (including `hit_policy`, `indices_from_pool`, `name`, `keys`, and hit-page
maps), add a regression using the existing duck-typed shape, and rerun the registered
tests. Telemetry must never make an otherwise valid restore fail.

### F-HAE-FINAL-02 — P1 — cache-side host-allocation mutation telemetry is unbounded

`_log_host_alloc_telemetry` in `unified_radix_cache.py:150-171` emits every record. The
new `_bump_host_allocability` path increments `_host_allocability_telemetry_seq` at
lines `3656-3669`, but does not use that sequence to coalesce, sample, or cap
`host_allocability_change` records. The only cap/coalescing logic added in this commit
is for scheduler-side `restore_host_alloc_wake_decision` events at
`scheduler.py:410-429`.

A direct source-loaded mutation probe called `_bump_host_allocability(..., "direct_free", 1)`
5,000 times and captured **5,000 mutation records**, with generation and telemetry
sequence both reaching 5,000. This falsifies the helper docstring's “bounded” claim and
leaves high mutation/release rates able to produce unbounded log volume. The prior gate
explicitly registered this as F-06, and the final acceptance input requires a complete
and bounded `host_alloc.v1` schema.

Disposition: **block merge**. Bound the mutation event family as well as wake decisions,
or define and implement an explicitly request-correlated sampling/coalescing policy that
preserves complete acceptance joins. Prove the bound with a repeated-mutation test;
do not only test wake-event repetition.

### F-HAE-FINAL-03 — P2 — discarded hybrid finalize reports the wrong restore state

On the hybrid-discard path, `_handle_prefetch_result` emits
`restore_hybrid_finalize` with `result="discarded"` and
`restore_state_after="RECOMPUTE"` at `unified_radix_cache.py:5512-5525`.
That same path records terminal outcome `"finalized"` at `:5758`. The scheduler maps
`"finalized"` to `RestoreEvent.FINALIZED` at `scheduler.py:3618-3619`, and the restore
state machine maps `RESTORING + FINALIZED` to `RestoreState.READY` at
`hicache_restore.py:282-284`.

Thus the emitted finalize record says `RECOMPUTE` while the subsequent request state
transition is `READY` (with zero loaded material). This makes the new schema unsuitable
for joining the telemetry record to the actual terminal disposition and can mislead
operators diagnosing a discarded hybrid restore.

Disposition: **block the telemetry gate until semantics are made explicit and consistent**:
either emit the actual post-feed state, or change the terminal/state transition and its
tests so the recorded state is the intended state. Add an assertion covering the discard
path.

## Plausible risks and non-blocking follow-ups

- Generation-change records emitted during request-scoped auxiliary cleanup carry
  `causal_rid=None` and `trace_context=None` at `unified_radix_cache.py:3667-3668`, even
  though the callers have a request ID. This may prevent a complete causal join for
  cleanup mutations. It is a follow-up unless the authoritative telemetry contract
  requires those fields whenever caller context exists; if it does, it should be promoted
  to a blocking schema defect in the next revision.
- `_host_alloc_hybrid_is_all_or_nothing` derives its flag from `TRAILING_PAGES`, while
  `_check_hybrid_prefetch_result` treats every non-KV-derived transfer as part of its
  all-or-nothing shortfall check. This is a plausible semantic mismatch for any
  non-KV-derived `ALL_PAGES` configuration. No production configuration proving that
  combination was available in this review, so it is not classified as a confirmed
  blocker.

## Live-test prerequisites

Before a re-review can accept the gate:

1. Fix F-HAE-FINAL-01 through F-HAE-FINAL-03 and add focused regressions for each.
2. Run the 123/123 dependency-free suite again, plus the registered tests in an
   environment providing `orjson`, `torch`, and the repository's normal test/runtime
   dependencies.
3. Run the authoritative live 3060/SM86/GDC acceptance scenarios at the pinned revision,
   including lock release, direct free, queued drain, auxiliary-only cleanup, hybrid
   all-or-nothing/per-domain feasibility, FIFO/no-spin, and telemetry join checks.
4. Keep 3090 and durability/fleet/performance conclusions out of the acceptance claim;
   this review found no commit-level 3090 scope expansion and has no live 3060 evidence.

## Open issues

- F-HAE-FINAL-01: unsafe direct attribute access in observational telemetry.
- F-HAE-FINAL-02: unbounded cache-side mutation telemetry.
- F-HAE-FINAL-03: discarded hybrid finalize state mismatch.
- Registered tests remain environment-blocked by missing `orjson` and `torch`.
- Live 3060 evidence remains a prerequisite and was not claimed here.

## Followups

Re-dispatch a fresh deep-review Task ID after the fixes, focused on the three blockers,
registered test execution, and live 3060 evidence. No additional work is accepted under
this Task ID.
