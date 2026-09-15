# R122 host-headroom gate — v2 CORRECTION (FROZEN, orchestrator)

- Supersedes the gate BASIS of `P1-R122-HEADROOM-GATE-ADDENDUM.md`
  (sha256 `92ad1c29…1aea25`). The v1 gate *intent* (two moments, sequential
  chain, Gate B = "F1 released so T is genuinely allocatable") is user-ratified
  and UNCHANGED. Only the pool/measurement basis is corrected, because v1's
  `host_allocable := full_free + full_evictable` measured the WRONG pool.
- Disposition of the v1 file: RETAINED, not deleted; annotated INVALID on basis.
  This v2 governs.

## Defect in v1 (source-verified by the R122 run AND independently)

`full_free`/`full_evictable` come from `_component_available_size(
ComponentType.FULL)` = the **device** KV pool (`token_to_kv_pool_allocator`,
`unified_radix_cache.py:4366-4368 -> :3018-3021`), size 65536. The predicate
that actually blocks a restore is `HOST_ALLOC` against the **L2 host** pool
(`host_allocability_snapshot` -> `cache_controller.mem_pool_host`,
`unified_radix_cache.py:3838-3876`), size 131073. The v1 citation of
"host allocable ~65534 at R121 raw.log:270084" is a `[P2A] promotion_reserve`
**device** line. Hence a literal v1 gate PASSES (63488 / 65534) while the host
pool is 2786. v1 basis = INVALID.

## Correct basis (v2)

The authoritative fresh host-pool reading is emitted by the server on its own
normal execution path via `host_alloc.v1` events (no new interface needed):
`restore_host_alloc_wait`, `restore_host_alloc_wake_decision`,
`restore_host_alloc_retry_result`, `host_allocability_change`.

Allocation DOES evict reclaimable host pages (R121
`restore_host_alloc_retry_result` host-alloc:330: `free_before=2144`,
`reclaimed=22526`, `free_after=24670`, `evictable_after=0`). Therefore:

```text
host_allocable := free_after_reclaim  (authoritative: retry_result.per_pool.kv.free_after)
# NOT raw free_before, and NOT the device pool.
```

**Gate A** (before F1 stage): `host_allocable >= F1_D_req + margin`.
**Gate B** (before T stage, after T wake; the critical one):
`host_allocable >= T_D_req + margin`, AND F1's host allocation is evidenced
RELEASED (`restore_host_alloc_wake_decision` predecessor terminal state
`RELEASED`, or `host_allocability_change`); if F1 still holds host, wait
(bounded), re-measure, else fail-fast.

## Verified R121 blocker (new evidential finding; overturns "new capacity only")

R121 host-alloc timeline for T (`r121-p3-R-T`):
```text
00:33:09 wait:26   free 98   evict 6080   req 27328  hold_no_generation
00:33:31 wake W26  free 2144 evict 4094   req 27328  grant   (pred = F1 RELEASED, global_grant_used)
00:33:53 retry     free_before 2144 -> free_after 24670, reclaimed 22526, evictable_after 0,
                   alloc1/alloc2 = false, required 27328  => revoked_alloc_failed (-2658)
00:34:09 wake W27  free 24672 evict 42942  req 27328  hold_no_generation
00:34:09 release W27 terminal_reason=restore_event:TIMEOUT -> restore_recompute cause=timeout
```
So R121 did NOT fail for lack of a grant: the RH host-alloc arbiter **granted T**
(F1 predecessor `RELEASED`). The concrete blockers were:
1. instantaneous capacity: free_after_reclaim 24670 < 27328 (**-2658**), evictable
   exhausted at that instant; and
2. F1's host pages (42942) became reclaimable only at 00:34:09, exactly when T's
   ~60s restore deadline expired (`hold_no_generation` also because
   `_host_alloc_wait_eligible` requires ALL blocked domains' generations to
   advance: kv advanced 1229->1230 but mamba stayed 1853).
=> The binding issue is a **headroom-availability-vs-deadline/wake-eligibility
race**, not an absolute "the profile can never hold T" limit. "Only
flush/close or new capacity would change that" (R122 report §Why-no-rerun) is
SUPERSEDED.

## Frozen R123 objective (unchanged chain; corrected basis)

Exhibit, on one bundle: `T FULL_DURABLE(D_req)` -> `T NOT_DEVICE_RESIDENT` ->
Gate A -> F1 issue -> T SPEC_BUDGET park -> F1 revoke/release (epoch +1) ->
T wake -> **Gate B** -> T stage (L3->L2) -> Host-ready -> admission ->
`kv_fetched == D_req` -> Mamba restore complete -> generation.
`durable-prefix recompute == 0`; `hybrid_discard == 0`; PARTIAL/shortfall within
`D_req` = FAIL; HTTP completed; identity continuous. `D_req = durable boundary`
(tail outside it allowed and must be evidenced).

Preferred mechanism (evidence-driven, no profile/param change): use the
R121-faithful decoy recipe (F1 > 39321 spec budget; F1+F2+T + sessioned
pressure) to make T non-device-/non-host-resident, then let the decoy pages
reach the **completed/evictable** state so the allocator can reclaim them, so
that at T's restore T sees `free_after_reclaim >= D_req`. Do NOT require
`F1+T` simultaneous residency.

## Forbidden (unchanged)
Server restart; profile/param change; `/flush_cache` (detaches L3); `/close_session`
(changes generation/L3 anchor). GPU operations under `/mnt/data/gpu/3090.lock`.
