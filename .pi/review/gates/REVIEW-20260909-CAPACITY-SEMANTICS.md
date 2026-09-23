ENTRY: ACCEPT

# Capacity semantics independent gate review

- Task ID: `REVIEW-20260909-CAPACITY-SEMANTICS`
- Orchestration epoch: `20260909-P4`
- Role: `reviewer`
- Invocation status: `done`
- Admission: `ACCEPT`
- Reviewed artifact: commit `93e6f54871547f237b515f4e3b9c8bc7c489a692`
- Branch: `3060-12g-qwen35-4b`
- Gate verdict: **REJECT**

## Scope and inputs

Read-only independent review of the requested commit in
`/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt`. The only file
written by this review is this gate report. Product code, remote hosts,
storage, and 3090 were not modified.

Reviewed:

- `HANDOFF-2026-09-07.md`;
- `DEBUG-20260909-POST-GUARD-CAPACITY.md`;
- `CODE-20260909-CAPACITY-SEMANTICS.md`;
- `CODE-20260909-PREFETCH-WAKE.md`;
- `TEST-20260909-P4-FRONTIER-GUARD.md`;
- prior gate `REVIEW-20260909-HYBRID-FRONTIER-GUARD.md`;
- the complete commit diff and surrounding source call paths;
- focused state-machine, scheduler-feed, and drain/revoke tests where the
  environment permitted execution.

## Blocking findings

### F1 — Positive allocation failure is still converted to a genuine miss

- Severity: **P0 / blocking**
- Location: `python/sglang/srt/managers/scheduler.py:3247-3254`
- Related locations: `python/sglang/srt/mem_cache/unified_radix_cache.py:5789-5799`
  and `scheduler.py:3043-3046`
- Evidence:

  1. `_try_alloc_storage_hit` calls
     `revoke_pending_prefetch(req_id, alloc_failed=True)` when a positive hit
     cannot allocate its full validated span (`unified_radix_cache.py:5897-5899`).
  2. `revoke_pending_prefetch` correctly releases the reservation first and
     records terminal outcome `"revoked_alloc_failed"`
     (`unified_radix_cache.py:5718-5721`, `5790-5799`).
  3. The normal post-drain path is `_reconcile_restore_states` step 1,
     `_feed_restore_terminal`. That function has explicit branches for
     `finalized`, `revoked_terminated`, and `revoked_backup_pending`, then
     maps every other value—including `"revoked_alloc_failed"`—to
     `REVOKED_MISS, genuine_miss=True` (`scheduler.py:3247-3254`).
  4. A genuine miss is then recorded as sticky miss evidence and admitted as
     recompute, rather than entering `WAIT_CAPACITY/HOST_ALLOC`. The branch
     added at `scheduler.py:3043-3046` is only for an immediate return from
     `prefetch_from_storage`; that function does not return
     `"revoked_alloc_failed"` for this drain allocation failure. The terminal
     string is consumed later by `_feed_restore_terminal`, so this branch does
     not repair the affected path.
  5. The new regression test itself specifies the required behavior:
     `CapacitySemanticsSchedulerFeedTests.test_positive_alloc_failure_maps_to_host_capacity_wait`
     expects `WAIT_CAPACITY` and `RestoreWaitReason.HOST_ALLOC`
     (`test/registered/unit/mem_cache/test_hicache_restore_scheduler_feed.py:216-226`). The current
     implementation cannot satisfy that assertion because of the catch-all
     mapping above.

- Acceptance impact: **fails the primary requirement**. A sidecar-positive
  hybrid hit whose full host staging allocation temporarily fails can still
  become a genuine miss and trigger full-history recompute. Reservation
  release is present, but retry/wake semantics are unreachable for this
  terminal outcome. The commit therefore does not preserve positive hits
  across capacity waits.

## Confirmed non-blocking properties

- The reservation release ordering is correct in the reviewed revoke path:
  `release_prefetch` runs before removing `ongoing_prefetch`, and the focused
  drain test passed for release and terminal classification.
- The existing `_storage_hit_crop_is_safe` fail-closed guard remains before
  the `storage_hit_count`/`hash_value` mutation and before queue submission
  (`unified_radix_cache.py:5883-5899`); no arbitrary trailing-sidecar crop
  was reintroduced.
- The all-or-nothing hybrid result/discard path was not changed by this
  commit.
- The explicit short resident-tail predicate is page-aligned, requires a
  nonempty device prefix and no host hit, and dispatches
  `DENIED_SHORT(short_tail_recompute=True)` to immediate tail recompute
  (`hicache_restore.py:384-408`, `scheduler.py:3055-3075`). Its pure
  state-machine tests passed, and the marker is consumed before the tail
  admission, preventing the known `REVALIDATE` loop in the modeled case.
- KV-only/full-fit behavior was not structurally altered by the crop guard;
  the full-fit path continues to allocate at the validated hit length, and
  the guard is only consulted for a shorter fallback.
- `capacity_wake_applies` now includes `HOST_ALLOC`, and the wake predicate
  checks the complete page-aligned requested KV span before waking
  (`hicache_restore.py:513-531`, `scheduler.py:3771-3789`). This is the
  intended shape, but it cannot compensate for F1 until the terminal outcome
  is mapped correctly.

## Verification evidence

- `git show --stat` and the full diff confirmed six changed files, matching
  the coder report.
- `git diff --check 93e6f54871^ 93e6f54871`: **PASS**.
- `python3 -m py_compile` passed for all three changed product modules and all
  three changed focused test files.
- `python3 test/registered/unit/mem_cache/test_hicache_restore.py`: **91 passed, 1 unrelated
  harness error** (`_t38c_residency_lock` missing in the synthetic cache).
  The changed pure transition and capacity tests passed, including the
  resident-tail and `HOST_ALLOC` wake tests.
- `python3 test/registered/unit/mem_cache/test_drain_reentry.py
  BackupPendingRevokeTests.test_positive_alloc_failure_is_retryable_and_releases_reservation`:
  **PASS**.
- The scheduler-feed test module could not collect with
  `PYTHONPATH=python` because the environment lacks `orjson`. This prevented
  direct execution of the regression that exposes F1; static control-flow
  inspection is conclusive because the terminal consumer's catch-all branch
  is visible in the committed source.
- The full drain-reentry harness had 11 synthetic-stub errors in unrelated
  backup/residency tests (`_t38c_residency_lock`, missing `pool_transfers`,
  and missing fake tree-core methods). These are evidence limitations, not
  additional findings against this commit.
- No live runtime or remote 3060 test was performed by this review; the
  supplied prior runtime evidence was independently read and considered.

## Questions versus findings

There are no review questions requiring clarification. The missing
`orjson`/runtime dependencies and pre-existing synthetic-harness failures are
test-environment limitations, not questions or reasons to waive F1.

## Summary and followups

The commit preserves the safety guard, all-or-nothing hybrid discard, and the
modeled short-tail escape, and it releases the failed prefetch reservation.
However, the principal capacity-semantic fix is incomplete at the actual
drain-to-scheduler boundary: `revoked_alloc_failed` is still interpreted as a
genuine miss. This is a blocking regression against the stated acceptance
criteria, so the gate verdict is **REJECT**.

Required followup under a fresh Task ID:

- Add an explicit `revoked_alloc_failed` branch in `_feed_restore_terminal`
  that feeds `RestoreEvent.DENIED_ALLOC` with non-miss semantics, then execute
  the scheduler-feed regression and a full focused restore/revoke matrix.
- Recheck that the corrected terminal path retains reservation release,
  wakes only for the complete span, and cannot reintroduce unsafe hybrid
  cropping or the short-tail `REVALIDATE` loop.

## Open issues

- F1 blocks acceptance until corrected and independently retested.
- Scheduler-feed runtime execution remains pending on the environment's
  missing `orjson` dependency.
- No live post-fix 3060 capacity run is part of this gate.

Artifacts: this report only.
Status: `done`
