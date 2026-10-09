ENTRY: ACCEPT

# CODE-20260909-HOST-ALLOC-EPOCH

```text
status: done
task_id: CODE-20260909-HOST-ALLOC-EPOCH
orchestration_epoch: 20260909-P4
role: coder
target_branch: 3060-12g-qwen35-4b
commit: 37cdf219e2
```

## Artifacts

- Commit `37cdf219e2` — `fix(hicache): wake host allocation by allocability generation`
- Focused deterministic unit coverage:
  `test/registered/unit/managers/test_hicache_host_allocability.py`

## Changed files

- `python/sglang/srt/mem_cache/unified_radix_cache.py`
  - Added cache-owned instance-qualified per-pool generations and snapshots.
  - Bumps occur after completed direct frees, queued release drains, and
    lock-release changes to host-evictable leaves/amount.
  - Carries typed allocation-failure facts after cleanup, including failed
    domains, sidecar facts, and the post-cleanup snapshot.
  - Preserves full-span allocation and the existing hybrid crop guard.
- `python/sglang/srt/managers/scheduler_components/hicache_restore.py`
  - Added typed snapshot/failure/cursor contracts and the FIFO wake arbiter.
- `python/sglang/srt/managers/scheduler.py`
  - Replaced the HOST_ALLOC free-level predicate with blocked-domain generation
    eligibility and one global FIFO grant per observed generation vector.
  - Failed retries rotate to the FIFO tail and suppress their post-attempt
    vector; no legacy paced-miss retry is armed for allocation pressure.
  - Added request/attempt-correlated key-value telemetry for wait, wake, retry,
    generation, pool levels, domains, and outcome fields.
- `python/sglang/srt/managers/schedule_batch.py`
  - Added transient HOST_ALLOC cursor and attempt metadata to `Req`.
- `python/sglang/srt/mem_cache/hybrid_cache/hybrid_cache_controller.py`
  and `hybrid_pool_assembler.py`
  - Connected controller-owned direct primary frees to the cache-owned bump
    callback without moving wake or allocation authority into the controller.
- `test/registered/unit/managers/test_hicache_host_allocability.py`
  - Covers unlock-to-evict opportunity, actual-free opportunity, no-change
    no-spin, insufficient-change FIFO fairness, independent auxiliary-domain
    blocking, and trailing-sidecar crop/all-or-nothing protection.

Deliberate simplification: telemetry is emitted through the existing logger
boundary as stable key-value event records rather than introducing a new
persistence or monitoring schema. Pool identifiers in transient snapshots are
normalized to their string names. Auxiliary staging failure before the L3
query has no positive sidecar hit count by construction; it still records the
failed auxiliary domain and required staging span conservatively.

## Verification evidence

Passed:

```text
python3 -m py_compile \
  python/sglang/srt/managers/scheduler_components/hicache_restore.py \
  python/sglang/srt/managers/schedule_batch.py \
  python/sglang/srt/managers/scheduler.py \
  python/sglang/srt/mem_cache/hybrid_cache/hybrid_cache_controller.py \
  python/sglang/srt/mem_cache/hybrid_cache/hybrid_pool_assembler.py \
  python/sglang/srt/mem_cache/unified_radix_cache.py \
  test/registered/unit/managers/test_hicache_host_allocability.py
git diff --cached --check
dependency-free FIFO/generation smoke check: PASS
```

Attempted focused restore/state tests:

```text
PYTHONPATH=python:test python3 -m unittest \
  registered.unit.managers.test_hicache_host_allocability \
  registered.unit.managers.test_hicache_restore_prefetch_budget -v
```

Blocked before collection because the environment does not provide `orjson`.
`python3 -m pytest` is also unavailable because `pytest` is not installed.
No CUDA, storage, remote-host, 3090, deployment, or live runtime verification
was performed.

## Summary

The accepted 3060-only mechanism is implemented and committed. Existing
all-or-nothing finalization, positive-hit non-miss classification, crop guard,
T13 timeout, storage format, Ready Horizon state, and 3090 branch were left
unchanged. The implementation uses cache snapshots only as wake invalidation
signals; allocators and evictors remain the fit authority.

## Followups

- Run the focused unittest files in an environment with the repository test
  dependencies installed.
- Independent tester/reviewer gates and any separately authorized live 3060
  runtime verification remain outstanding.

## Open issues

- Full focused unit execution is environment-blocked by missing `orjson` and
  `pytest`; compile and pure-policy smoke evidence passed.
- No claim is made for remote runtime behavior, durability, or 3090 behavior.

Extra work requires a fresh Task ID.

## Follow-up — CODE-20260909-HOST-ALLOC-EPOCH-FOLLOWUP

```text
status: done
task_id: CODE-20260909-HOST-ALLOC-EPOCH-FOLLOWUP
orchestration_epoch: 20260909-P4
commit: a3d1dd631c
base: 37cdf219e2
```

Resolved F-01 through F-06 in the authorized 3060 branch. The positive-hit
HOST_ALLOC path is full-span-only; auxiliary rollback and transfer release
callbacks notify the owning pool generation; lock-release telemetry uses
numeric zero units; FIFO entries are removed on state departure, timeout,
queue-limit abort, direct abort, and idle cleanup; optional operation metadata
uses duck-typed defaults; and HOST_ALLOC records use `host_alloc.v1` with
request, attempt, timestamps, identity, generation, deadline, per-pool,
failure, wake, and terminal fields.

Changed product/test files:

- `python/sglang/srt/mem_cache/unified_radix_cache.py`
- `python/sglang/srt/mem_cache/pool_host/group.py`
- `python/sglang/srt/mem_cache/hybrid_cache/hybrid_pool_assembler.py`
- `python/sglang/srt/managers/scheduler.py`
- `python/sglang/srt/managers/scheduler_components/hicache_restore.py`
- `test/registered/unit/managers/test_hicache_host_allocability.py`
- `test/registered/unit/mem_cache/test_mem_pool_host.py`
- `3090-dev/test_drain_reentry.py`

Verification:

- `py_compile` for all changed Python files: PASS.
- `git diff --check`: PASS.
- Dependency-free arbiter/schema smoke: PASS.
- Positive alloc-failure compatibility test: PASS.
- Full `3090-dev/test_drain_reentry.py test_hicache_restore.py`: 111 passed;
  12 known stale fixture errors remain (residency lock, backup digest, and
  fake tree-component surfaces documented by the deep review).
- Registered focused tests: collection blocked by missing `orjson` and
  `torch`; `pytest` is not installed. These dependency gaps are reported
  separately and were not worked around by weakening coverage.

Open issues: independent tester/reviewer gates and separately authorized live
3060 evidence remain outstanding. No 3090 product, RH/durability, storage
format, remote, or deployment scope was changed.

Extra work requires a fresh Task ID.
