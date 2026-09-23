ENTRY: ACCEPT

# Deep review follow-up: HOST_ALLOC epoch correction

- Task ID: `REVIEW-DEEP-20260909-HOST-ALLOC-EPOCH-FOLLOWUP`
- Orchestration epoch: `20260909-P4`
- Reviewed revision: `a3d1dd631cb9f1aa1c0e40b30c29f19a8f224476`
- Base/follow-up comparison: `37cdf219e2..a3d1dd631c`
- Authorized scope: read-only review of this repository; this report is the only
  written artifact.

## Verdict

**REJECT.** The correction resolves several prior findings, but four blocking
findings remain. The evidence is conclusive; no Expert Gate is requested.

## Blocking findings

### F-03 residual: effective lock-release changes are still suppressed (P1)

`UnifiedRadixCache._bump_host_allocability` at
`python/sglang/srt/mem_cache/unified_radix_cache.py:3636-3668` treats its default
`returned_units=0` as an early-return condition. Its caller
`_bump_changed_host_allocability` at `:3670-3683` intentionally omits
`returned_units` when an evictability signature changes. Therefore an effective
lock-release change does not advance the cache-owned generation and does not emit
the promised `host_allocability_change` record. This is both the original
liveness defect and a telemetry defect; the prior logging exception was hidden by
dropping the event.

Evidence:

- Direct source-loaded probe of `_bump_changed_host_allocability` with an
  effective lock-release signature change produced
  `generation_after_effective_lock_change={'kv': 0}`.
- Direct call to `_bump_host_allocability('kv', 'lock_release_evictable')`
  produced `direct_lock_release_default_generation=0`.
- The added unit tests
  `test_lock_release_telemetry_uses_numeric_zero_units_and_schema` and
  `test_lock_release_advances_generation_only_on_effective_change` expect the
  opposite behavior and were not runnable because collection lacks `orjson`.

Disposition: **blocking**. Permit zero-unit causal changes when the before/after
evictability signature differs, emit numeric zero, and advance exactly once;
retain suppression for non-effective mutations. Re-run the two tests and an
explicit no-change control case.

### F-07: auxiliary cleanup can self-wake the same waiter (P1)

In `prefetch_from_storage` (`unified_radix_cache.py:5237-5250`) and the positive
hit revoke path (`:6083-6112`), auxiliary transfers are appended to a deferred
release queue and the failure snapshot is captured immediately afterward. The
actual per-pool free and generation bump occur later in `_drain_extra_release`
(`:6866-6894`). The scheduler records the failure cursor from that pre-drain
snapshot (`scheduler.py:3246-3251`) and the arbiter can then observe the
generation created by the request's own queued cleanup.

Reproduction/evidence: a pure `HostAllocWakeArbiter` simulation with a waiter
captured at Mamba generation 0, followed by the request's own release advancing
Mamba to generation 1, returned:

```text
eligible_after_queued_self_release= True
selected_after_queued_self_release= r
```

This violates the ARCH contract's post-cleanup snapshot and no-self-wake
requirements. It is not disproved by the arbiter's one-generation-grant logic;
the arbiter is being given a misleading causal vector.

Disposition: **blocking**. Complete the relevant auxiliary release/drain before
capturing the retry snapshot, or carry an explicit causal generation boundary
that excludes the current request's cleanup. Add a regression covering a staged
auxiliary allocation failure, the cleanup bump, and same-RID non-selection.

### F-06 residual: `host_alloc.v1` is incomplete and emission is not bounded (P2)

The schema constant exists (`hicache_restore.py:26`), and the cache helper adds
several common fields, but the event family is not complete or uniformly shaped:

- `restore_hybrid_finalize` is absent from the corrected diff and from the source
  search (`rg -n 'restore_hybrid_finalize|host_alloc.v1' ...` finds only the schema
  declaration for that event family).
- Scheduler wait and wake records (`scheduler.py:3265-3285`, `:3445-3485`)
  omit cache-instance and trace-context fields required by the ARCH contract.
- Cache retry records (`unified_radix_cache.py:5253-5281`, `:6167-6181`) do not
  carry the cache instance consistently; the pre-query failure path hard-codes
  `attempt_id=None`.
- `_host_allocability_telemetry_seq` is incremented but never used to coalesce,
  sample, or cap records. `_log_host_alloc_telemetry` calls `logger.info` for
  each causal event despite its “bounded” docstring.

Disposition: **blocking**. Define and implement the complete event matrix and
required fields, including `restore_hybrid_finalize`, then demonstrate bounded
emission under repeated mutations. If the contract is intentionally narrowed,
update and re-approve the ARCH gate before implementation acceptance.

### F-08: callback-less rollback leaks auxiliary slots and changes out-of-scope
HiRadix behavior (P1)

`HostPoolGroup._notify_host_free` (`pool_host/group.py:58-62`) returns before
calling `self.free` when `host_allocability_change_fn` is unset. The corrected
`resolve_host_transfers` rollback (`:173-176`) uses this helper, so a partial
auxiliary allocation failure can leave already allocated slots unreleased when
the observer is not wired. The callback is wired by Unified's
`_apply_stack_result` (`hybrid_pool_assembler.py:1685-1690`), but the HiRadix
attachment paths (`:1882+` and `:1956+`) set the pool/controller references and
do not set this callback. The shared `HostPoolGroup` change therefore alters
HiRadix behavior, which the ARCH scope explicitly excludes, and can leak on its
rollback path.

Disposition: **blocking**. Always perform the owning `free` first; make the
generation callback optional observation only. Add a callback-absent rollback
test and either preserve HiRadix behavior or obtain an explicit scope decision.

## Prior findings rechecked

- **F-01: resolved for Unified, with scope caveat.** The corrected Unified
  `_try_alloc_storage_hit` uses full-length allocation and optional full-length
  eviction retry. Static search found no call to `_storage_hit_crop_is_safe` in
  the Unified path and no lower-frontier/minimum allocation. HiRadix retains
  separate crop logic, consistent with the stated out-of-scope boundary.
- **F-02: substantially resolved in the wired Unified path, but not sufficient
  for acceptance.** Rollback/release now operates per transfer/pool, the Unified
  assembler wires observers, and queued drains bump KV and each auxiliary pool.
  F-03 and F-08 show that generation correctness is still conditional on the
  observer path and that one rollback path is unsafe without it.
- **F-04: resolved by inspection.** Direct abort, timeout, request abort, and
  state departure remove the FIFO entry; the idle reconciliation and selector
  also discard absent/non-waiting entries. The relevant 3090-dev tests reached
  these paths except where stale fixtures failed earlier.
- **F-05: resolved in the corrected call sites.** Optional operation attributes
  use `getattr`/safe defaults. The dependency-free positive-allocation-failure
  fixture lacking `pool_transfers` passed.

## Required semantic checks

- **No self-wake:** **fails**, per F-07 above.
- **One generation grant:** arbiter source has FIFO selection, exact-vector
  suppression, and post-attempt vector recording (`hicache_restore.py:76-148`);
  a pure arbiter smoke test passed. Full registered coverage was unavailable.
- **All-or-nothing hybrid:** static inspection of
  `_check_hybrid_prefetch_result` shows partial auxiliary transfer failure
  invalidates/releases the operation; no crop fallback was found.
- **Real miss semantics:** the corrected revoke/terminal branches distinguish
  `revoked_miss` from `revoked_alloc_failed`; the dependency-free flag-off and
  partial-hit miss tests passed.
- **Existing prefetch wake:** frontier-ready reconciliation still reissues
  prefetch and the relevant dependency-free restore tests passed where their
  fixtures were complete.
- **RH OFF:** the flag-off path bypasses speculative ready-horizon reservation
  and retains physical-capacity miss behavior. The specific flag-off drain test
  was blocked by its stale fixture lock, not by a detected HOST_ALLOC semantic
  failure.
- **Branch scope:** the corrected commit changes only eight files and adds no
  3090 product code or remote/runtime change. The shared callback regression in
  F-08 is nevertheless an out-of-scope HiRadix effect.

## Stale-fixture error classification

The reported 12 errors are verified as fixture gaps, not product regressions in
the corrected HOST_ALLOC code. Exact runs:

```text
python3 test/registered/unit/mem_cache/test_drain_reentry.py
31 tests: 20 passed, 11 errors

python3 test/registered/unit/mem_cache/test_hicache_restore.py
92 tests: 91 passed, 1 error
```

The 11 drain-reentry errors classify as follows:

1. `test_above_threshold_partial_hit_parks_at_the_drain` — fixture constructs
   `UnifiedRadixCache` with `object.__new__` and omits `_t38c_residency_lock`.
2. `test_drain_backup_ack_wakes_frontier_waiters` — fake
   `ordered_key_set_digest` returns scalar `""`; production code unpacks the
   current two-value API.
3. `test_drain_backup_parent_ack_promotes_child_acked_earlier` — same stale
   scalar digest stub.
4. `test_drain_backup_partial_ack_does_not_promote_and_clears_guard` — same
   stale scalar digest stub.
5. `test_drain_backup_unpersisted_node_does_not_wake` — same stale scalar digest
   stub.
6. `test_finish_count_poll_persists_after_pop_loop` — fake tree lacks
   `get_component_device_value`.
7. `test_gap_node_deleted_mid_gapfill_is_skipped` — same fake-tree omission.
8. `test_register_trigger_dedupes_already_submitted_chain` — same fake-tree
   omission.
9. `test_register_trigger_persists_anchor_chain` — same fake-tree omission.
10. `test_write_back_drain_does_not_recurse` — same fake-tree omission.
11. `test_write_back_evict_flushes_after_demote` — fake cache omits
    `_t38c_residency_lock`.

The one restore error is:

12. `test_flag_off_drain_precheck_never_parks` — fake cache omits
    `_t38c_residency_lock`.

Evidence for the classification is the traceback location in each run, the
production initialization of `_t38c_residency_lock` in
`UnifiedRadixCache.__init__`, the current two-value production digest API, and
the fact that the omitted tree method is outside the corrected HOST_ALLOC
changes. These fixtures must still be updated and rerun before claiming a clean
branch test result; they are not evidence that the product code is clean.

## Commands and environment evidence

Passed:

```text
python3 -m py_compile \
  test/registered/unit/mem_cache/test_drain_reentry.py \
  python/sglang/srt/managers/scheduler.py \
  python/sglang/srt/managers/scheduler_components/hicache_restore.py \
  python/sglang/srt/mem_cache/hybrid_cache/hybrid_pool_assembler.py \
  python/sglang/srt/mem_cache/pool_host/group.py \
  python/sglang/srt/mem_cache/unified_radix_cache.py \
  test/registered/unit/managers/test_hicache_host_allocability.py \
  test/registered/unit/mem_cache/test_mem_pool_host.py
git diff --check 37cdf219e2 a3d1dd631c
```

The dependency-free `3090-dev` results are the 111 passed / 12 fixture errors
classified above. Registered tests were collection-blocked by missing
dependencies:

```text
PYTHONPATH=python:test python3 -m unittest \
  registered.unit.managers.test_hicache_host_allocability -v
-> ModuleNotFoundError: No module named 'orjson'

PYTHONPATH=python:test python3 -m unittest \
  registered.unit.mem_cache.test_mem_pool_host -v
-> ModuleNotFoundError: No module named 'torch'

PYTHONPATH=python python3 test/registered/unit/mem_cache/test_hicache_restore_scheduler_feed.py
-> ModuleNotFoundError: No module named 'orjson'
```

No live 3060 run was available. No remote host/storage or 3090 was modified.

## Followups / open issues

1. Fix F-03, F-07, F-06, and F-08, then obtain an independent review of the
   revised evidence.
2. Update stale 3090-dev fixtures and rerun all 123 dependency-free cases; the
   current 111/12 result is not a clean pass.
3. Install/provide `orjson`, `torch`, and the test runner in the authorized test
   environment, then run the registered focused tests.
4. Resolve the Pattern Intake / Novel Mechanism / ARCH governance status before
   terminal implementation acceptance; those artifacts were still proposed or
   blocked, not approval authority.

Status: `done`
