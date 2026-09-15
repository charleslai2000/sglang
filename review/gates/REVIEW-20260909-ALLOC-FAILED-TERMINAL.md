ENTRY: ACCEPT

# Allocation-failed terminal independent gate review

- Task ID: `REVIEW-20260909-ALLOC-FAILED-TERMINAL`
- Orchestration epoch: `20260909-P4`
- Role: `reviewer`
- Invocation status: `done`
- Admission: `ACCEPT`
- Reviewed artifact: commit `1e6a82194e7f5d071823e4abb68514c6d421e4b3`
- Branch: `3060-12g-qwen35-4b`
- Gate verdict: **ACCEPT**

## Scope and inputs

Read-only independent review of the requested commit in
`/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt`. The only file
written by this review is this gate report. Product code, remote hosts,
storage, and 3090 were not modified.

Reviewed:

- prior rejected gate `REVIEW-20260909-CAPACITY-SEMANTICS.md`;
- `CODE-20260909-ALLOC-FAILED-TERMINAL.md`;
- `DEBUG-20260909-POST-GUARD-CAPACITY.md`;
- `HANDOFF-2026-09-07.md`;
- the complete commit diff and surrounding scheduler/cache call paths;
- focused restore state, scheduler-feed, drain/revoke, crop-guard, and
  hybrid all-or-nothing tests.

## Findings

No blocking findings. No security or trust-boundary change was introduced.

### F1 from the prior gate is resolved

The exact affected path is now coherent:

1. A positive storage hit whose complete host staging allocation fails reaches
   `revoke_pending_prefetch(..., alloc_failed=True)` at
   `python/sglang/srt/mem_cache/unified_radix_cache.py:5896-5900` after the
   trailing-sidecar crop guard rejects an unsafe shorter frontier.
2. The revoke path releases the reservation before removing the operation
   (`unified_radix_cache.py:5718-5722`), records
   `"revoked_alloc_failed"` (`:5790-5799`), and does not add a miss marker.
   The existing focused drain test confirms the reservation and speculative
   counter are released.
3. `_feed_restore_terminal` now explicitly maps
   `"revoked_alloc_failed"` to `RestoreEvent.DENIED_ALLOC` with
   `genuine_miss=False` (`python/sglang/srt/managers/scheduler.py:3247-3256`).
   `wait_reason_for` maps that event to `RestoreWaitReason.HOST_ALLOC`, and
   the state transition enters `RestoreState.WAIT_CAPACITY`
   (`hicache_restore.py:122-125`, `:274-285`). Therefore no sticky miss
   epoch, anchor, or generation is recorded and no full-history miss
   recompute is triggered by this terminal.
4. The existing reconciliation path wakes this wait only when the host
   prefetch budget is available and the complete page-aligned requested span
   fits (`scheduler.py:3192-3234`, `:3773-3791`). It transitions through
   `CAPACITY_FITS` to `RESTORING` and reissues the normal prefetch, with the
   bounded restore timeout remaining as the fallback.

The real miss path remains distinct: zero-hit and below-threshold outcomes
remain `revoked_miss`, and the terminal consumer maps that value to
`REVOKED_MISS, genuine_miss=True` (`unified_radix_cache.py:5751-5758`,
`:5790-5799`; `scheduler.py:3255-3277`). The genuine-miss focused tests
continue to assert sticky miss evidence and non-waiting recompute behavior.

### Existing safety contracts remain intact

- The crop guard is unchanged and remains fail-closed for any shortened
  frontier with a `PoolHitPolicy.TRAILING_PAGES` transfer
  (`unified_radix_cache.py:147-154`, `:5883-5895`). A full validated hybrid
  allocation remains allowed; KV-only crops remain allowed.
- The all-or-nothing hybrid result check is unchanged
  (`unified_radix_cache.py:5304-5397`): any sidecar shortfall invalidates the
  result and releases all resources without publishing a partial hybrid
  restore.
- The commit changes only the terminal mapping and its regression assertions;
  it does not alter storage-query validation, allocation, reservation release,
  crop mutation, sidecar I/O, or hybrid finalization.

## Verification evidence

- `git show --stat` and the full diff confirmed exactly two changed tracked
  files: `scheduler.py` and
  `3090-dev/test_hicache_restore_scheduler_feed.py`.
- `git diff --check 1e6a82194e^ 1e6a82194e`: **PASS**.
- `PYTHONDONTWRITEBYTECODE=1 python3 -m py_compile` over the changed product
  modules, the restore state module, and the three focused test modules:
  **PASS**.
- `PYTHONDONTWRITEBYTECODE=1 python3 3090-dev/test_hicache_restore.py`:
  **91 passed, 1 unrelated synthetic-harness error** at
  `test_hicache_restore.py:988` because the stub cache lacks
  `_t38c_residency_lock`.
- `python3 3090-dev/test_drain_reentry.py
  BackupPendingRevokeTests.test_positive_alloc_failure_is_retryable_and_releases_reservation`:
  **PASS**. This independently verifies terminal classification, removal of
  the miss marker, reservation release, and speculative-counter release.
- The new focused scheduler-feed test was attempted with `PYTHONPATH=python`
  but collection is blocked by the environment's missing
  `orjson` (`ModuleNotFoundError`). Local availability is also missing
  `pytest` and `torch`. The mapping and wake path were therefore verified by
  source inspection plus the available pure state/drain tests; no live 3060
  runtime acceptance is claimed.
- `git status --short --branch` after review shows only the pre-existing
  untracked review/storage artifacts; no reviewed tracked file was modified.

## Questions versus findings

There are no review questions requiring clarification. The missing runtime
dependencies and the unrelated synthetic-harness error are evidence limits,
not implementation findings.

## Summary and followups

The prior gate's P0 finding is corrected. A positive hybrid L3 hit that cannot
obtain its complete host staging span now follows
`revoked_alloc_failed -> DENIED_ALLOC -> WAIT[HOST_ALLOC]`, without genuine
miss evidence. Its reservation is released, and the existing host-capacity
predicate provides a bounded retry path. Genuine storage misses, the
fail-closed crop guard, short-tail handling, and all-or-nothing hybrid
finalization remain intact.

Non-blocking followups under fresh Task IDs:

- run the focused scheduler-feed test in the project dependency environment
  with `orjson` available;
- perform separately authorized live 3060 capacity/retry validation if a
  runtime claim is required.

## Open issues

- Scheduler-feed runtime evidence remains pending on missing `orjson` (and the
  local environment also lacks `pytest` and `torch`).
- The focused restore harness retains the unrelated `_t38c_residency_lock`
  synthetic-stub error.
- No live post-fix 3060 run was part of this read-only gate.

Artifacts: this report only.
Status: `done`
