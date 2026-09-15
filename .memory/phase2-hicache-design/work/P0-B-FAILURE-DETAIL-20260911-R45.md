# P0-B R42 HOST_ALLOC failure detail — R45

- Task ID: `P0-B-FAILURE-DETAIL-20260911-R45`
- Invocation: `ses-p0b-failure-detail-r45-20260911`
- Role: `scout`
- Epoch: `2026-09-11`
- Status: `done`
- Scope: read-only local inspection of the staged R42 report/transcript, R43 report, the HOST_ALLOC unit fixture, and production scheduler/arbiter/cache snapshot code. No product/test edits, remote access, 3090 use, or production execution.

## Artifacts and evidence

- R42 report: `.memory/phase2-hicache-design/work/P0-B-FOCUSED-RERUN-20260911-R42.md`
- R42 transcript: `/tmp/p0b-focused-r42-transcript.txt`
- R43 report: `.memory/phase2-hicache-design/work/P0-B-R42-TRIAGE-20260911-R43.md`
- Test: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/test/registered/unit/managers/test_hicache_host_allocability.py`
- Production sources: `python/sglang/srt/managers/scheduler.py`, `python/sglang/srt/managers/scheduler_components/hicache_restore.py`, and `python/sglang/srt/mem_cache/unified_radix_cache.py` in the same checkout.

## Exact three failures

R42 collected nine HOST_ALLOC tests: six passed and exactly these three failed. All three are assertion failures returning `None`; no production traceback is shown.

1. `HostAllocabilityWakeTests.test_auxiliary_blocked_hybrid_requires_auxiliary_generation`
   - Assertion: `test_hicache_host_allocability.py:127`.
   - Transcript: `/tmp/p0b-focused-r42-transcript.txt:14-32`.
   - Expected: `"hybrid"`; observed: `None`.
   - Fixture setup: blocked domains are `("kv", "mamba")`, auxiliary requirement is `{"mamba": 1}`, cursor generations are `kv=0,mamba=0`.
   - The intermediate `kv=1,mamba=0` snapshot at test line 124 expects `None` and passes. The final snapshot at line 126 is `kv=1,mamba=1`, `free_kv=54976`, `free_mamba=1`; line 127 expects the waiter to be selected.

2. `HostAllocabilityWakeTests.test_no_change_no_spin_and_failed_retry_rotates_fifo`
   - Assertion: `test_hicache_host_allocability.py:98`.
   - Transcript: `/tmp/p0b-focused-r42-transcript.txt:33-54`.
   - Expected: `"first"`; observed: `None`.
   - Fixture setup: two queued requests (`first`, `second`), both initially blocked on `kv`, cursor generation `kv=0`, initial free units `1024`.
   - The unchanged snapshot assertion at line 95 expects `None` and passes. The next synthetic snapshot at line 97 is `kv=1`, `free_kv=1024`, `evict_kv=2048`; line 98 expects `first`.

3. `HostAllocabilityWakeTests.test_unlock_to_evict_and_actual_free_are_generation_opportunities`
   - Assertion: `test_hicache_host_allocability.py:77`.
   - Transcript: `/tmp/p0b-focused-r42-transcript.txt:55-72`.
   - Expected: `"unlock"`; observed: `None`.
   - Fixture setup: one queued `unlock` request blocked on `kv`, initial cursor generation `kv=0`, `free_kv=1024`, `evict_kv=0`.
   - Synthetic snapshot at test line 76 changes generation to `kv=1`, keeps free units at `1024`, and changes evictable units to `54976`; line 77 expects `unlock`.

R42's suite summary is at transcript lines 87-90: the three named IDs failed, six passed, and exit was 1. R42 report lines 38-39 record the same result; R43 lines 27-41 pin the names, assertion locations, expected values, and observed `None` values.

## Production semantics relevant to classification

- `Scheduler._select_host_alloc_waiter()` (`python/sglang/srt/managers/scheduler.py:3600-3629`) requires a non-rate-limited controller, a queued `WAIT_CAPACITY` request whose reason is `RestoreWaitReason.HOST_ALLOC`, and `_host_alloc_wait_eligible(req)`.
- `_host_alloc_wait_eligible()` (`scheduler.py:3481-3492`) requires the current cache instance to match the cursor and requires a strictly greater generation for **every** blocked domain. It does not use `free_units_by_pool` or `evictable_units_by_pool` as independent eligibility predicates.
- The arbiter's `choose()` (`hicache_restore.py:111-123`) selects the first eligible queued RID for a generation vector and suppresses the vector already granted. `record_attempt_result()` rotates a failed waiter (`hicache_restore.py:125-144`), preserving FIFO behavior.
- The production cache owns snapshot construction (`unified_radix_cache.py:3775-3819`): generations come from `_host_allocability_generations`; free units come from host-pool availability; evictable units come from `_host_evictable_signature()`. The mutation helper increments generation only on an actual cache-owned allocability change (`unified_radix_cache.py:3760-3773` and nearby bump code).

## Source-version / fixture mismatch finding

The R42 test is not using a production cache. `_SnapshotCache` (`test_hicache_host_allocability.py:49-56`) returns a manually supplied mutable `HostAllocabilitySnapshot`; `_request()` (`:31-46`) manually supplies the cursor and blocked-domain contract. Each failing case then mutates snapshot fields directly (`:76`, `:97`, `:124-126`). Thus the run tests scheduler/arbiter logic against synthetic snapshots, not an allocator mutation path.

There is also a checkout/version boundary: R42 transferred the test from the local `sglang-3090-24g-opt` tree, while execution occurred in remote `/root/sglang-3060-12g-hicache`; R42 records the test hash and transfer verification at lines 19-32. The local 3090-opt checkout currently has unrelated uncommitted product/test changes and does not contain this test at the parallel `sglang-3090-24g-hicache` path. Therefore the available evidence cannot prove that the remote production source and local source were identical beyond the recorded transferred file hashes.

The immediate failure mechanism is consistent with a fixture/API contract mismatch: the production predicate is generation-only and domain-complete, while the test comments/assertions describe free/evictable changes as “generation opportunities” but provide only a hand-edited snapshot. R43 correctly classified this as unresolved fixture/API or source-version mismatch, not a proven product allocator failure. No production exception or allocator result is present in the three traces.

## Safe-fix classification and bounded coder recommendation

All three failures are **safe to investigate/fix in tests only**, subject to preserving the production predicate and FIFO oracle. A coder may:

1. Align `_SnapshotCache` and request cursors with the exact current `HostAllocabilitySnapshot`/`host_allocability_snapshot()` contract, including cache instance and all blocked-domain generations.
2. Verify the intended source revision used by the rerun before changing expected values; do not treat the test hash alone as proof that production scheduler/cache sources match.
3. Rerun only the three exact IDs and retain the FIFO assertions (`first`, then `second` after rotation) and the hybrid requirement that both `kv` and `mamba` generations advance.

The coder must not weaken `_host_alloc_wait_eligible()` to wake on free or evictable counts alone, remove the arbiter vector suppression, or change production allocator/generation semantics based on these failures. If a fixture-corrected rerun still returns `None`, that is the point to open a separate production-contract investigation; R42 does not establish one.

## Summary

`done`: The exact R42 HOST_ALLOC failures are three assertion-level `None` results at test lines 127, 98, and 77, with expected IDs `hybrid`, `first`, and `unlock`. Their synthetic snapshots advance generations, but the test does not exercise production cache mutation or prove source parity with the remote R42 checkout. Production requires cache-instance equality and strictly advanced generations for every blocked domain, then FIFO arbiter admission. A bounded, test-only fixture/API alignment and exact-ID rerun is safe; no product fix is justified by the current evidence.

## Followups

- Fresh coder dispatch: inspect source parity and correct only the HOST_ALLOC fixture/API setup if needed; rerun the three exact IDs.
- Reviewer dispatch after rerun: compare fixture vectors and expected FIFO/hybrid semantics against the production predicate before accepting any assertion change.

## Open issues and limits

- The original remote checkout/source is not available locally for a fresh comparison; only R42's recorded transfer hashes and staged transcript are available.
- No tests were rerun in this read-only scout invocation.
- Existing workspace changes predate this invocation; this report is the only artifact written here. The checkout is already dirty, so unrelated changes must be excluded when reviewing any later coder diff.
- Search was limited to the named phase2 memory directory, `/tmp/p0b-focused-r42-transcript.txt`, the named 3090-opt checkout, and targeted HOST_ALLOC/arbiter/snapshot symbols. Unrelated repositories, remote hosts, production, and 3090 runtime assets were not scanned.
