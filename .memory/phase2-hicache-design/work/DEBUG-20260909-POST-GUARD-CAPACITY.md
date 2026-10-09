ENTRY: ACCEPT

# Post-guard 3060 P4 restore-capacity diagnosis

```text
status: done
task_id: DBG-20260909-POST-GUARD-CAPACITY
orchestration_epoch: 20260909-P4
role: debugger-deep
scope: read-only source, PID, log, and storage/runtime inspection
```

## Conclusion

`5b61e63993` did what it was intended to do: no request in the post-seed
batch reached a cropped Mamba sidecar boundary.  The four remaining failures
are instead two separate availability/state-machine faults.

1. **R2_q/R2_x are valid, full-frontier L3 hits that fail host allocation.**
   The guard refuses the only available arbitrary crop, then the cache-mode
   path classifies a positive (`54,976`) hit as `revoked_miss`.  Scheduler
   consumes that as a *genuine L3 miss* and recomputes.  q's in-flight
   prefetch fills the physical prefetch budget; x is correctly woken when q
   releases it, but x then fails the same host allocation.  Thus the budget
   wake is present; it is not the terminal defect.

2. **R2_y/R2_z have a resident 54,976-token prefix and only a 24-token
   suffix.**  There is no L3 query to revalidate.  `declined_too_short` is a
   terminal statement about that current suffix, but the scheduler admits a
   `WAIT[REVALIDATE]` device-match-decay bet.  It repeats the same decline 121
   times in about 2.4 seconds, then has no event that changes the 24-token
   suffix and idles until the 180-second timeout.  Recomputing the 24-token
   tail immediately is safe; waiting is avoidable latency/recompute.

There is **no evidence** that q/x lack every lower sidecar-complete checkpoint:
the guard deliberately performs no search/revalidation below the 54,976-token
frontier, and the preserved trace does not record q/x hashes at candidate
shorter frontiers.  The observed fact is narrower: the full validated
frontier could not allocate during this concurrent run.  Consequently, the
first hypothesis is only partly confirmed: no *full* feasible allocation was
available at those instants; whether a safe lower checkpoint existed is
unobserved.

## Deployed identity and guard oracle

- PID `76671` was alive on port 30000 and runs the supplied 3060 profile,
  including `max_running_requests=1`, cache host mode, `wait_complete`, retry
  interval `1`, retry maximum `120`, and restore timeout `180`.
- Remote `unified_radix_cache.py` SHA-256 was
  `395e55efc4d472547581d2a33d7b989933fb78990cf4a455d8daa0e02845a203`, the
  committed `5b61e63993` blob reported by the tester.
- `_storage_hit_crop_is_safe` at
  `unified_radix_cache.py:147-154` rejects a crop whenever a transfer uses
  `PoolHitPolicy.TRAILING_PAGES`.  In `_try_alloc_storage_hit`
  (`:5840-5897`), that check happens before `storage_hit_count` and
  `hash_value` are mutated.  A rejected crop therefore never reaches
  `_sync_trailing_keys` / sidecar IO.
- All ten post-seed requests have zero `hybrid_discard` and zero
  `Failed-to-fetch-Mamba`.  This rejects recurrence of the pre-guard frontier
  mismatch.

## Exact causal timelines

Times are remote, 2026-09-09 +08:00.  `t38c-probe.log` supplies query state;
the engine log supplies scheduler state.

### R2_q and R2_x: full valid hit -> host allocation failure

| Time | q | x | Meaning |
| --- | --- | --- | --- |
| 07:18:04.957 | `prefetch_issued`, requested 55,000 | — | q occupies the physical prefetch admission path. |
| 07:18:05.093 | — | first `declined_rate_limited`; `WAIT_CAPACITY/PREFETCH_BUDGET` | x is budget blocked, not storage-missing.  The trace records 121 budget waits. |
| 07:18:21.420 | `pc_storage_query`: KV=54,976, Mamba=54,976 | — | q's query and sidecar alignment agree at one full frontier. |
| 07:18:21.432 | `prefetch_revoke storage_hit=54976 miss_reason=alloc_failed` | — | Full host staging allocation failed after the cache-mode attempt/eviction path.  The guard prevented a shorter arbitrary allocation. |
| 07:18:21.433 | `restore_recompute cause=miss` | `restore_retry cause=capacity` | q's revoke releases the prefetch reservation; x's capacity wake occurs in the same millisecond. |
| 07:18:21.435 | — | `prefetch_issued` | This is positive evidence that the PREFETCH_BUDGET release/wake works. |
| 07:18:24.764 | — | `pc_storage_query`: KV=54,976, Mamba=54,976 | x independently obtains the same kind of sidecar-complete full hit. |
| 07:18:25.389-.390 | — | `prefetch_revoke ... alloc_failed`; `restore_recompute cause=miss` | The second full allocation fails and is again converted to a miss. |
| 07:18:28.234-.825 | R2_w IO/finalize 34,496 | R2_w IO/finalize 34,496 | The smaller already-issued W transfer completes only after q/x are terminal. |
| 07:18:51.110 | R2_w restore success | R2_w restore success | L3 IO and Mamba sidecar handling remain viable under this batch. |

The startup log allocated a 131,073-token KV host pool and a 5.51-GB Mamba
host pool.  It does **not** log historical available/locked pages at q/x's
two allocator calls.  In particular, q/x allocation failure does not prove
that 54,976 could never fit after queued/pinned cache state changes.  W was
already in flight from 07:18:04.711 through 07:18:28.825, and the batch had
five concurrent submitted requests despite a one-request running limit; that
is concrete occupancy/timing pressure, but the exact unavailable allocation
breakdown is missing evidence.

### R2_y and R2_z: 24-token tail -> futile revalidation wait

| RID | First probe | Repeated disposition | Terminal |
| --- | --- | --- | --- |
| R2_y | 07:18:04.565: `matched_len=54976`, `suffix_len=24`, backuped anchor; 07:18:04.585 `declined_too_short` | 121 `RECOMPUTE requested=24 granted=0 reason=too_short` records, each retained as `WAIT_CAPACITY/REVALIDATE`; last at 07:18:06.995 | 07:21:04.586 `restore_recompute cause=timeout` |
| R2_z | 07:18:04.833: `matched_len=54976`, `suffix_len=24`, backuped anchor; 07:18:04.844 `declined_too_short` | 121 equivalent records; last at 07:18:07.287 | 07:21:05.399 `restore_recompute cause=timeout` |

The read-only trace query `grep` found **zero** `pc_get_v2` events for y/z.
Their failure is therefore not stale storage-query data, failed Mamba IO, or
sidecar revalidation.  It occurs before a storage query is issued.

## Source-level causal chain

### Positive q/x query is converted into a false terminal miss

1. `HybridCacheController._storage_hit_query`
   (`hybrid_cache_controller.py:848`) queries KV then
   `_align_storage_query_transfers` (`:943-958`) aligns the `TRAILING_PAGES`
   Mamba key to the returned KV frontier.  The q/x probe lines report the
   aligned result `kv=54976,mamba=54976`; this rejects stale/revalidation
   mismatch for these attempts.
2. `_try_alloc_storage_hit` (`unified_radix_cache.py:5840-5897`) first tries
   the complete `operation.storage_hit_count`, calls `evict_host` when
   appropriate, then considers the shorter cache-mode fallback.  For this
   hybrid operation, `_storage_hit_crop_is_safe` returns false, leaves
   `host_indices` absent, and invokes `revoke_pending_prefetch`.
3. `revoke_pending_prefetch` (`:5709-5758`) labels every nonzero,
   above-threshold hit that reaches this branch `alloc_failed`, but records
   the terminal outcome through the legacy revoke/miss channel.  It has no
   distinct positive-hit/unavailable-capacity terminal outcome.
4. `Scheduler._feed_restore_terminal` (`scheduler.py:3218+`) maps the
   resulting `revoked_miss` to `REVOKED_MISS, genuine_miss=True`.  That is why
   q/x produce `restore_recompute cause=miss`, even though their storage
   probes were positive.

The prefetch budget behavior is separate and working as implemented.
`prefetch_from_storage` (`unified_radix_cache.py:4901-4973`) returns
`declined_rate_limited` for x while q is active; `release_prefetch`
(`:4785-4810`) releases q's reservation on revoke, and
`Scheduler._reconcile_restore_states` (`scheduler.py:3169-3209`) immediately
emits x's `restore_retry cause=capacity`.  The observed wake proves that this
is not a missing PREFETCH_BUDGET wake.

### y/z turn a terminal current suffix into a wait with no useful wake

1. `_prefetch_kvcache` (`scheduler.py:3034-3057`) receives
`declined_too_short`.  Given retry interval 1 and `_restore_potential_for`,
it feeds `DENIED_SHORT` rather than admitting the 24-token recompute.
2. The transition table (`scheduler_components/hicache_restore.py:94-132`)
maps a fresh `DENIED_SHORT` to `WAIT_CAPACITY/REVALIDATE`; its own contract
describes this as the device-match-decay bet.  The trace shows the match does
not decay while the request remains blocked.
3. `_reconcile_restore_states` (`scheduler.py:3090-3213`) turns each
`_storage_prefetch_missed_rids` marker into a retry based on scheduler passes,
not a storage or residency-change event.  `capacity_wake_applies`
(`hicache_restore.py:487-506`) explicitly excludes REVALIDATE and HOST_ALLOC
from its capacity predicate.  The result is the observed fast 121-try loop,
then T13 timeout.

## Hypotheses distinguished

| Hypothesis | Verdict | Evidence |
| --- | --- | --- |
| No full sidecar-complete allocation at the observed q/x instants | Confirmed | Both positive 54,976 KV+Mamba queries end in allocator `alloc_failed`; no crop or sidecar fetch follows. |
| No safe lower checkpoint exists | Not established | No code path searches/revalidates q/x below 54,976, and no candidate-boundary inventory was preserved. |
| Missing PREFETCH_BUDGET release/wake | Rejected for x | q revoke is followed immediately by x `restore_retry cause=capacity` and re-issue. |
| Budget/prefetch interaction | Confirmed but secondary | q's active prefetch blocks x initially; it explains x's first wait, not the later terminal allocation failures. |
| Stale storage query/revalidation | Rejected | q/x KV and Mamba are co-aligned at 54,976; y/z issue no storage read at all; zero hybrid discard/Mamba fetch failures. |
| Test corpus or queue contamination | No corruption evidenced; concurrency is causal pressure | Batch 2 made no settled storage-file-count change.  Five concurrent submissions with `max_running=1`, W in flight, and resident y/z prefixes create the timing/occupancy regime.  There is no evidence of cross-RID query data or filesystem contamination. |

## Minimal fix locations and contracts

### A. Preserve positive-hit capacity semantics (q/x)

The narrowest correctness fix belongs at the cache-mode no-allocation path in
`_try_alloc_storage_hit` / `revoke_pending_prefetch`, with the corresponding
terminal mapping in `_feed_restore_terminal`.

Required contract:

> Once L3 has positively validated a hybrid frontier, failure to allocate its
> complete host staging span is **capacity unavailability**, never evidence
> that the L3 frontier is missing.  It must not set the per-anchor
> negative/miss state.  It may wait until an observable host-capacity change
> and re-query, or time out/recompute; it may not crop that frontier unless a
> lower sidecar-complete frontier has itself been validated.

A distinct `revoked_alloc_failed` terminal outcome mapped to `DENIED_ALLOC`
(not `REVOKED_MISS`) is the smallest classification change.  Its retry must
be driven by a host-pool release/availability generation or a real monotonic
timer; the present `retry_poll_interval=1` is scheduler-pass paced and burned
121 retries in roughly 2.4 seconds for y/z.  Do not retain the prefetch
reservation while waiting, otherwise the wait blocks its own budget wake.

Selecting a lower checkpoint is a separate availability feature: after the
full allocation fails, query/check the candidate shorter prefix and its
trailing Mamba key together, then allocate only if that same frontier is
complete.  The guard alone has no such lookup, so it must remain fail-closed.

### B. Do not idle a known 24-token tail (y/z)

The narrowest fix is in `Scheduler._prefetch_kvcache` / the
`DENIED_SHORT` admission decision.  A too-short suffix with no registered
state-change event capable of enlarging it must transition directly to
`ADMIT_RECOMPUTE`; it must not be parked merely because the prompt was
theoretically prefetchable before its current resident match.

If the device-match-decay bet is retained, its contract needs an explicit
residency-generation wake and bounded real-time retry.  A bare scheduler-loop
poll is neither: it creates the demonstrated busy retry then a 180-second
timeout while the prefix is unchanged.

## Recommended next experiment

Use a fresh authorized task and a deterministic runtime/unit harness with
request-joined pool telemetry (`required`, `available`, `locked`, `evictable`,
and allocation-generation) at every `_try_alloc_storage_hit` call.

1. Seed q/x, deliberately retain enough unrelated host residency to make the
   full 54,976 allocation fail, then release it.  Assert a positive
   KV+Mamba hit produces a capacity wait (not `revoked_miss`), performs no
   unsafe crop, wakes only after the release generation, and restores if the
   full span fits.
2. In a paired case, make a smaller q/x prefix physically sidecar-complete;
   assert it is explicitly revalidated before IO.  In the negative pair,
   assert it waits/times out/recomputes without sidecar IO.
3. Set a 54,976 resident prefix with a 24-token tail and assert immediate
   admission/recompute of that tail, zero `pc_get_v2`, and no REVALIDATE wait.

This experiment resolves the only remaining capacity question—whether q/x
have a usable lower checkpoint—without weakening the guard.

## Artifacts and evidence limits

- Remote source (read-only):
  `/root/sglang-3060-12g-hicache/python/sglang/srt/mem_cache/unified_radix_cache.py`,
  `hybrid_cache/hybrid_cache_controller.py`,
  `managers/scheduler.py`, and
  `managers/scheduler_components/hicache_restore.py`.
- Remote logs (read-only):
  `/tmp/qwen35-4b-hicache-p4-reconstruct-sm86-20260909-json.log` and
  `/tmp/t38c-probe.log`.
- Read prior reports: `DEBUG-20260909-MAMBA-FILE-MISMATCH.md`,
  `CODE-20260909-HYBRID-FRONTIER-GUARD.md`,
  `REVIEW-20260909-HYBRID-FRONTIER-GUARD.md`,
  `TEST-20260909-P4-FRONTIER-GUARD.md`, and
  `OPS-20260909-MAMBA-INVENTORY.md`.
- No product code, runtime process, storage, service configuration, or 3090
  product files were changed.  This report is the only write.

## Followups

- Fresh implementation Task ID for either availability contract above.
- Fresh test/runtime Task ID for the requested capacity/revalidation matrix.

## Open issues

- The logs lack per-request host `available/locked/evictable` counters at the
  two q/x allocation calls; exact allocator occupancy cannot be reconstructed.
- The q/x shorter-prefix hash and sidecar existence set was not captured, so
  lower-checkpoint feasibility remains unknown.
- No conclusion is made about eventual capacity after R2_w finalization;
  q/x had already been converted to terminal misses before that event.
