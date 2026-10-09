# CODE-20260909-HOST-ALLOC-EPOCH-FINAL-FIX

ENTRY: ACCEPT

status: done

Task ID: `CODE-20260909-HOST-ALLOC-EPOCH-FINAL-FIX`  
Orchestration epoch: `20260909-P4`  
Branch: `3060-12g-qwen35-4b`  
Commit: `ebaf9e5c49` (`fix(hicache): close host alloc epoch follow-up findings`)

## Artifacts

Changed and committed only the authorized 3060 product/test files:

- `python/sglang/srt/managers/scheduler.py`
- `python/sglang/srt/mem_cache/unified_radix_cache.py`
- `python/sglang/srt/mem_cache/pool_host/group.py`
- `3090-dev/test_drain_reentry.py`
- `3090-dev/test_hicache_restore.py`
- `test/registered/unit/managers/test_hicache_host_allocability.py`
- `test/registered/unit/mem_cache/test_mem_pool_host.py`

Pre-existing untracked `.memory/`, `review/gates/`, and `storage/` artifacts in the 3060 repository were not staged or modified by the commit.

## Summary

- F-03: effective `lock_release_evictable` signature changes now advance the pool generation exactly once even when returned units are zero; telemetry serializes numeric zero values. Unchanged lock releases remain no-ops. Existing generation tests cover zero direct-free, effective direct-free, and changed-signature behavior.
- F-07: auxiliary staged transfers are released before the HOST_ALLOC failure snapshot is captured. The cleanup path records the post-cleanup generation boundary, clears owned transfer handles, and the scheduler arbiter regression verifies that the same RID cannot wake from its own cleanup generation.
- F-06: HOST_ALLOC telemetry now carries the required request/cache/trace identity, attempt IDs, monotonic and wall timestamps, generation vectors, wait deadlines, per-pool required/free/evictable values, failed domains, and retry outcomes. `restore_hybrid_finalize` emits KV and per-sidecar expected/fetched values plus all-or-nothing and terminal state. Wake-decision telemetry is coalesced by RID/attempt/generation signature, capped for repeated holds, and bounded by key-map eviction; it remains observational and is not used by fit or wake authority.
- F-08: `HostPoolGroup` always frees owned slots first; the callback is optional observation. A callback-absent rollback regression was added.
- Cleaned the verified 3090-dev fixture gaps for `_t38c_residency_lock`, the two-value digest API, fake tree component-device lookup, and the adjacent current API surfaces required for the fixture to execute. No production 3090 files were changed.
- Preserved full-span hybrid behavior and genuine-miss separation. Positive allocation failure remains retryable/non-miss, while zero-hit genuine miss behavior remains unchanged.

## Evidence

Passed:

- `python3 3090-dev/test_drain_reentry.py` — 31/31
- `python3 3090-dev/test_hicache_restore.py` — 92/92
- `python3 -m py_compile` over all touched Python product and test files
- `git diff --cached --check`
- Branch/status verification confirmed `3060-12g-qwen35-4b`; commit contains only the seven listed files.

The dependency-free suite is therefore 123/123 passing. Its coverage rechecked timeout/cancel cleanup, FIFO wait behavior, no-change/no-self-spin behavior, genuine-miss handling, full-span retry behavior, and the no-crop source guard.

Blocked at collection by environment dependencies, with no assertion failures:

- `PYTHONPATH=python:test python3 -m unittest registered.unit.managers.test_hicache_host_allocability -v` — missing `orjson`
- `PYTHONPATH=python:test python3 -m unittest registered.unit.mem_cache.test_mem_pool_host -v` — missing `torch`

## Followups

- Re-run the two registered unit modules in an environment containing `orjson`, `torch`, and the repository test dependencies.
- Independent gate/reviewer acceptance remains with the named reviewer owner.

## Open issues

- Registered unit verification is environment-blocked by missing `orjson` and `torch`; this is recorded rather than bypassed.
