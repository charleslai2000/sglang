ENTRY: ACCEPT

# DBG-20260909-HOST-ALLOC-WAKE — HOST_ALLOC liveness diagnosis

```text
status: done
task_id: DBG-20260909-HOST-ALLOC-WAKE
orchestration_epoch: 20260909-P4
role: debugger-deep
scope: read-only source and 3060 runtime/log inspection; this report only
```

## Conclusion

The live bundle has already fixed the *classification* defect: a positive
54,976-token storage hit whose cache-mode host allocation fails becomes
`revoked_alloc_failed -> DENIED_ALLOC -> WAIT_CAPACITY/HOST_ALLOC`, not a
storage miss.  It has **not** proved that the required full host span becomes
available before T13.

The remaining liveness gap is narrower than the dispatch premise:

1. The active `capacity_wake_applies()` **does include `HOST_ALLOC`**.  The
   older source that excluded it is a timestamped remote backup, not the
   deployed file.  Therefore changing that enum membership is neither the
   missing fix nor an explanation of this run.
2. `_reconcile_restore_states()` does run the HOST_ALLOC predicate every
   scheduler pass.  It did not issue a later retry because its active
   predicate requires both no prefetch-rate limit and
   `mem_pool_host.available_size() >= full_requested_span`.  For q/x/w this
   condition was false on every post-failure pass (assuming the deployed
   scheduler executed normally; no scheduler exception is logged).
3. That predicate observes only *already free* primary-host pages.  It cannot
   notice that a host-tree lock release has made pages **evictable**.  The
   allocator would try `alloc(full) -> evict_host(full) -> alloc(full)` on a
   reissue, but the scheduler refuses to reissue until the full span is free.
   This is a circular wait when the needed space is in newly evictable host
   cache rather than already free pool pages.

Thus the missing mechanism is an **allocability-change wake**, not another
unpaced retry and not an inference that a shorter checkpoint exists.  It must
cover both actual primary-host frees and transitions that make host entries
evictable.  Current code has neither a restore-visible generation nor waiter
registration for either source.

## Deployed identity and source facts

Read-only checks on `/root/sglang-3060-12g-hicache` show the deployed hashes
recorded by OPS-20260909-DEPLOY-CAPACITY-BUNDLE:

| File | SHA-256 | Relevant active locations |
| --- | --- | --- |
| `scheduler.py` | `efe922c97be391bb223c8c6dd371589d99e310b6e857b0ea4e15c3fae92e1abe` | `_reconcile_restore_states` 3116–3239; `_feed_restore_terminal` 3241–3277; `_restore_wait_capacity_fits` 3747–3791 |
| `hicache_restore.py` | `ec7954d18cee43dc39f7cf0263fff367aa93a03ccc38cf1fe80995c644b8875e` | `capacity_wake_applies` 513–531 |
| `unified_radix_cache.py` | `3021d3b0591a2e102c3d0f73d32680448080fb882fc9a2ef6722d4bca336cbe8` | `revoke_pending_prefetch` 5709–5818; `_try_alloc_storage_hit` 5854–5913; release drains 6433–6491 |

Specific facts:

- `revoke_pending_prefetch(..., alloc_failed=True)` emits
  `revoked_alloc_failed` (5712–5716, 5755–5756, 5790–5799).  Scheduler maps
  it to `DENIED_ALLOC`, with `genuine_miss=False` (3247–3256).  The immediate
  `prefetch_from_storage` outcome mapping has the same result (3039–3046).
- `capacity_wake_applies` returns true for `HOST_ALLOC` (518–530).  The
  pre-deploy backup
  `hicache_restore.py.bak-20260909-capacity-20260909-081116:492–506` is the
  source that says HOST_ALLOC is excluded; it is not the active SHA above.
- At each reconciliation pass, a HOST_ALLOC waiter reaches
  `_restore_wait_capacity_fits` because it is admitted by that enum predicate
  (3192–3210).  Its HOST_ALLOC branch rejects on active prefetch-rate limiting
  (3773–3778), then computes the same page-aligned full request and accepts
  only if `available_size >= requested` (3779–3791).  There is no call to
  `evict_host` in this predicate.
- On the actual allocation path, cache mode first tries the complete full
  span, then (for this no-ready-horizon run) invokes `evict_host(full)` and
  retries the full allocation (5871–5882).  Only afterward may it consider a
  crop; the hybrid crop guard rejects the unsafe crop (5883–5899).  This
  preserves the full positive frontier but leaves a HOST_ALLOC wait.
- `evict_host` does synchronously drive tree host eviction and frees returned
  values (3574–3584).  Queued completion/release paths also call
  `mem_pool_host.free` (6433–6491).  Neither path records a host-capacity
  generation or wakes a HOST_ALLOC waiter.
- Critically, `UnifiedTreeCore.dec_host_lock_ref` only releases locks and
  refreshes `evictable_host_leaves` (unified_tree_core.py:680–687).  The host
  eviction walker selects only those leaves (full_component.py:230–257).
  Unlocking can therefore make a later `evict_host` successful without
  increasing `mem_pool_host.available_size`; no existing scheduler condition
  sees that change.
- The nearby `_ready_host_release_epoch` is not a restore wake API.  It is a
  Ready-Horizon causal epoch synthesized from observed `available_size` growth
  (`scheduler.py:3585–3613`); it has no registration, consumption, or
  evictability signal for ordinary `WAIT_CAPACITY/HOST_ALLOC` requests.

## Observed live causal chain

All values below are from the preserved active engine log
`/tmp/qwen35-4b-hicache-p4-capacity-bundle-20260909-20260909-081116.log`.

| Request | Prefetch-budget wake | Positive aligned query / allocation failure | Terminal state |
| --- | --- | --- | --- |
| q | `08:18:35.106 restore_retry cause=capacity` | `08:18:44.944 prefetch_revoke storage_hit=54976 ... alloc_failed` | `08:18:44.946 WAIT_CAPACITY/HOST_ALLOC`; `08:20:50.012 timeout recompute` |
| x | `08:18:44.946 restore_retry cause=capacity` | `08:18:55.675 ... alloc_failed` | `08:18:55.677 WAIT_CAPACITY/HOST_ALLOC`; `08:20:50.223 timeout recompute` |
| w | `08:18:55.677 restore_retry cause=capacity` | `08:19:06.405 ... alloc_failed` | `08:19:06.407 WAIT_CAPACITY/HOST_ALLOC`; `08:20:50.223 timeout recompute` |

The accompanying tester report supplies the request-correlated probe evidence
that each allocation failure followed one full KV+Mamba query at 54,976
tokens, with no hybrid discard, Mamba fetch failure, `revoked_full_miss`, or
`revoked_insufficient`.  y finalized a 54,976-token restore at 08:18:35 and z
at 08:19:23.  q/x/w produce no later `restore_retry` after entering
HOST_ALLOC.

The source conjunction makes that absence meaningful: after each host wait,
the active predicate either still saw a rate-limited prefetch budget or fewer
than 54,976 already-free primary-host tokens.  The log does **not** contain
request-time host `available`, `locked`, `evictable`, allocator result, or
generation counters, so it cannot distinguish those two failed clauses or
prove permanent physical impossibility.  Nor does it establish any lower
sidecar-complete checkpoint.  The only supported physical conclusion is that
the full span was not allocatable at the three original attempts and was never
shown already free afterward.

## Why a free-only poll is insufficient

`evict_host` is called only from `_try_alloc_storage_hit`, after the scheduler
has elected to reissue.  A successful request can release a host lock and
thereby make a resident, L3-backed host leaf reclaimable; that changes
`evictable_host_leaves`, not the allocator's free count.  Existing q/x/w
waiters require the free count to reach their entire span before they take the
path that would evict the newly reclaimable leaf.  No event is emitted by:

- `dec_host_lock_ref` / host-LRU eligibility change;
- `evict_host` / `_free_values`; or
- queued `append_host_mem_release` then `_drain_release`.

Actual frees do not strictly require a callback because the existing
per-pass free-count predicate will see a full span.  They should nevertheless
bump the same generation for observability and uniform correctness.  A
generation is essential for the lock-release/evictability case, where free
count does not grow at all.

## Minimal safe fix contract (recommendation only)

Introduce one cache-owned, monotonic **primary-host allocability epoch** and
record its value on a `DENIED_ALLOC` transition.  It is an invalidation signal,
not a promise that a request can now fit.

1. Bump it only after a change that can make a new complete primary-host
   allocation feasible:
   - a completed primary-host pool free (direct tree eviction and queued
     primary release drains); and
   - a `dec_host_lock_ref` that changes the set/amount of host-evictable
     material.
   Do not bump it on failed `alloc`, budget-reservation release, or a generic
   scheduler pass.  Auxiliary/Mamba allocation changes must either be included
   in the feasibility epoch with their own complete-span checks or leave the
   waiter parked; do not claim a KV-only generation proves a hybrid allocation.
2. For `WAIT_CAPACITY/HOST_ALLOC`, retain the captured epoch.  Reconcile may
   wake only when (a) prefetch budget permits an issue and (b) current epoch is
   newer than the captured epoch.  Do **not** use a periodic retry as the
   liveness mechanism.
3. On that one reissue, let the existing authoritative allocator perform
   `alloc(full) -> evict_host(full) -> alloc(full)`.  Do not require
   `available >= full` beforehand: that is the circular gate.  Do not crop,
   mark a miss, or search a lower frontier.  If allocation still fails, return
   to HOST_ALLOC and snapshot the current epoch, so the same change cannot
   self-spin it.
4. Serialize a bounded/FIFO number of HOST_ALLOC wake attempts per epoch (one
   is the safest minimal policy).  This prevents three waiters from stampeding
   a single release.  A successful claim or a subsequent relevant capacity
   change advances the next opportunity.  Prefetch reservation must already
   remain released while waiting, as the current revoke path does; otherwise a
   waiter could block its own wake.

This is a new state-machine/allocator boundary, so implementation needs the
required Pattern Intake and Novel Mechanism declaration before its gate work.

## Regression design

Add deterministic scheduler/cache tests with an aligned KV+Mamba 54,976-token
positive hit and explicit fake host-pool/tree telemetry.

1. **Unlock-to-evict success.** Start with free < 54,976 and a locked
   L3-backed host leaf large enough to satisfy the deficit when unlocked.
   First attempt must produce `revoked_alloc_failed`, `DENIED_ALLOC`,
   `WAIT/HOST_ALLOC`, no miss evidence, no crop, and released prefetch
   reservation.  Unlock it; assert allocability epoch advances, exactly one
   retry invokes full `evict_host`, and the full KV+Mamba restore reaches
   READY/success.
2. **Actual-free success.** With no evictable leaf, drain a primary-host
   release large enough for the full span.  Assert the epoch/wake, one full
   reissue, and success.  Cover both direct tree free and queued release drain
   if they are distinct code paths.
3. **No change, no spin.** Keep both free and evictability unchanged across
   many scheduler passes.  Assert zero HOST_ALLOC retries, a stable wait clock,
   then only T13 recompute.  This rejects reuse of the 121-pass paced retry.
4. **Insufficient change and fairness.** Release/unlock less than the full
   need with several waiters.  Assert at most the configured FIFO candidate
   retries for that epoch; its re-failure snapshots the epoch and does not
   loop.  A later sufficient epoch restores one full aligned frontier.  Assert
   no arbitrary crop or lower-checkpoint assumption in either case.
5. **Hybrid failure guard.** If primary KV capacity changes but required Mamba
   staging remains unavailable, assert no false success/miss and no busy loop;
   the request remains waitable until a relevant complete feasibility change
   or T13.

## Artifacts, evidence, followups, open issues

Artifacts/evidence:

- this report;
- prior live test report
  `.memory/phase2-hicache-design/work/TEST-20260909-CAPACITY-BUNDLE-LIVE.md`;
- active remote source hashes and locations above;
- preserved engine log and `/tmp/t38c-probe.log` (read-only).

Summary: The test demonstrates positive-hit liveness failure, but not that the
active source excludes HOST_ALLOC or that physical host capacity is permanently
impossible.  The active scheduler polls a free-only predicate; the missing
contract is an event/generation for host **allocability**, especially lock
release -> evictable transition, followed by one bounded retry through the
existing full-span allocator/evictor.

Followups:

- Fresh architecture/gate task for the allocability-epoch contract and Novel
  Mechanism declaration.
- Fresh coder and tester tasks for implementation and the regression matrix.
- Add request-correlated `available`, `evictable`, `locked`, required-span,
  epoch-before/after, and retry-decision telemetry before another live test.

Open issues:

- Missing runtime counters prevent attribution of q/x/w's failed predicate to
  rate limit versus free-span shortage and prevent proving that unlock events
  occurred before T13.
- Lower safe sidecar-complete checkpoint availability is unobserved and must
  not be inferred.
- The exact hybrid auxiliary-pool feasibility condition requires explicit
  telemetry in the implementation task.
