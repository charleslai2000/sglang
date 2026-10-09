ENTRY: ACCEPT

# CODE-20260909-ALLOC-FAILED-TERMINAL

```text
status: done
invocation_status: done
admission: ACCEPT
task_id: CODE-20260909-ALLOC-FAILED-TERMINAL
orchestration_epoch: 20260909-P4
role: coder
branch: 3060-12g-qwen35-4b
commit: 1e6a82194e7f5d071823e4abb68514c6d421e4b3
```

## Artifacts

- `python/sglang/srt/managers/scheduler.py`
- `3090-dev/test_hicache_restore_scheduler_feed.py`
- Commit `1e6a82194e` (`fix(hicache): preserve positive hits on alloc failure`)

The requested crop guard and short-tail path were not modified. No 3090
checkout, remote host, storage data, or unrelated source was changed.

## Summary

`Scheduler._feed_restore_terminal` now maps the drain terminal
`revoked_alloc_failed` explicitly to `RestoreEvent.DENIED_ALLOC` with
`genuine_miss=False`. The existing transition therefore enters
`WAIT_CAPACITY` with `RestoreWaitReason.HOST_ALLOC`; it does not arm sticky
miss evidence or trigger full-history recompute. Real `revoked_miss` continues
to use `RestoreEvent.REVOKED_MISS` with genuine-miss semantics.

The focused scheduler-feed regression now also asserts that miss epoch,
anchor, and generation remain unset for the positive allocation-failure
terminal. Existing drain behavior continues to verify reservation release and
the `revoked_alloc_failed` terminal classification.

## Verification

- `python3 -m py_compile` for the three changed product modules and three
  focused test modules: **PASS**.
- `git diff --check HEAD^ HEAD`: **PASS**.
- `PYTHONPATH=python python3 3090-dev/test_hicache_restore.py`: **91 passed,
  1 unrelated synthetic-harness error** (`_t38c_residency_lock` missing).
- Focused restore state/capacity tests: **47 passed**.
- `BackupPendingRevokeTests.test_positive_alloc_failure_is_retryable_and_releases_reservation`:
  **PASS**.
- `PYTHONPATH=python python3 3090-dev/test_hicache_restore_scheduler_feed.py
  CapacitySemanticsSchedulerFeedTests`: collection blocked by missing
  environment dependency `orjson` (`ModuleNotFoundError`).
- Working tree after commit retains only pre-existing untracked review/storage
  artifacts; no additional tracked changes remain.

## Followups

- Re-run `CapacitySemanticsSchedulerFeedTests` in the project environment with
  `orjson` available.
- Independent reviewer should re-run the capacity-semantics gate against
  commit `1e6a82194e`.

## Open issues

- Scheduler-feed runtime evidence remains pending on the missing `orjson`
  dependency.
- The unrelated synthetic restore-harness error remains outside this change.

Extra work requires a fresh Task ID.
