# CODE-20260909-CAPACITY-SEMANTICS

status: done
invocation_status: done
admission: ACCEPT
task_id: CODE-20260909-CAPACITY-SEMANTICS
orchestration_epoch: 20260909-P4
role: coder
branch: 3060-12g-qwen35-4b
commit: 93e6f54871547f237b515f4e3b9c8bc7c489a692

## Scope

Implemented the two confirmed post-guard HiCache correctness fixes in
`/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt`. No files in the
3090-hicache checkout or remote hosts were modified.

## Artifacts

Changed files in commit `93e6f54871`:

- `python/sglang/srt/mem_cache/unified_radix_cache.py`
- `python/sglang/srt/managers/scheduler.py`
- `python/sglang/srt/managers/scheduler_components/hicache_restore.py`
- `3090-dev/test_hicache_restore.py`
- `3090-dev/test_hicache_restore_scheduler_feed.py`
- `3090-dev/test_drain_reentry.py`

## Summary

Defect A: a positive storage hit whose complete validated host staging
allocation fails now uses the explicit `revoked_alloc_failed` terminal outcome
and feeds the existing `DENIED_ALLOC` / `WAIT[HOST_ALLOC]` transition. Revoke
still releases the prefetch reservation and staged resources, so the request
cannot block its own capacity wake. The wake checks availability for the
complete page-aligned requested span and retains the existing bounded timeout;
the existing `_storage_hit_crop_is_safe` guard and all-or-nothing discard
behavior are unchanged.

Defect B: when a device-resident historical prefix has no host restore
material and only a page-aligned suffix below the prefetch threshold remains,
the scheduler consumes the retry marker and uses the existing `DENIED_SHORT`
transition with an explicit immediate tail-admit judgment. The prefix remains
in `prefix_indices`, so only the suffix is recomputed and the request does not
enter the `REVALIDATE` busy loop. Other too-short cases retain their prior
state-machine behavior.

## Verification

- `python3 -m py_compile` passed for all three changed product modules and all
  three changed focused test files.
- `git diff --check` passed before commit.
- `python3 3090-dev/test_hicache_restore.py RestoreStateMachineTests CapacityWakeApplicabilityTests`
  passed: 47 tests.
- `python3 3090-dev/test_drain_reentry.py BackupPendingRevokeTests.test_positive_alloc_failure_is_retryable_and_releases_reservation`
  passed: 1 test.
- The scheduler-feed focused test module was blocked during collection by the
  environment's missing `orjson` dependency when run with `PYTHONPATH=python`.
- Broader legacy drain-harness execution was not used as acceptance evidence;
  unrelated pre-existing harness stubs fail on missing runtime attributes.
- No remote, deployment, or live 3060 runtime operation was performed.

## Followups

- Run `CapacitySemanticsSchedulerFeedTests` in the project environment with
  the normal runtime dependencies installed.
- Independent tester/reviewer acceptance remains a separate fresh Task ID.

## Open issues

- This implementation uses the existing observable complete-span host
  availability check plus the existing bounded restore timeout; it does not
  introduce a new allocator generation counter.
- No new lower-sidecar checkpoint was introduced; the existing
  `_storage_hit_crop_is_safe` fail-closed behavior remains authoritative.
- Existing unrelated test-harness dependency/stub failures remain outside
  this task.

Extra work requires a fresh Task ID.
