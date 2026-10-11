# R124 — orchestrator correction of the tester report (verified against the bundle)

Status: the tester's R124 verdict (`P1-SPEC-BUDGET-CONTROLLED-EVICTION-20260911-R124.md`,
sha256 `9c599adf…`) is **substantially wrong**. Bundles/checksums are valid
(`sha256sum -c` all OK); the EVIDENCE is good, the INTERPRETATION is not. Product
code unchanged; server untouched. All claims below are re-derived from
`work/R124-bundle/raw.log` and `probe.log` with line numbers.

## Correction 1 — the L3 durable pipeline is NOT broken (claim REFUTED)

Tester: "its L3 durable publish/ack path does not function", based on
`restore_disposition rid=r124-p1-build-T … RECOMPUTE granted=0 reason=revoked:miss`.

- A build request's FIRST storage query is ALWAYS a miss (the prefix is new);
  `RECOMPUTE` is the correct build outcome. In R121 the same happened for
  `build-T` (`probe.log:76`, `kv_hit_pages=0`). It is NOT evidence of a defect.
- Decisive counter-evidence: the decoy `r124-p1-R-F1` — built in THIS run —
  **restored 42752 tokens from L3**: `probe.log` `pc_l3_host completed_tokens=42752`;
  `raw.log:392551-392554` `restore_disposition … granted=42752` then
  `restore_success n_tokens=42750`; `pc_storage_query kv_hit_pages=42752`
  (`probe.log` lines 2862/3078).
- `residency_barrier_outcome result=False` reasons are `build_not_ready` /
  `nonterminal_not_build_registered`, i.e. the known telemetry-incomplete
  `durability_barrier` path (registered P0-B observability gap), not a write
  failure. `backup_ack_drain result=complete completed_tokens=2048` recurs.
- => The "server-side durable publication broken" blocker is **REFUTED**.

## Correction 2 — T WAS non-resident and DID park SPEC_BUDGET (claims WRONG)

Tester: T "stayed resident (`device_hit=2048/host_hit=22080`)" and C2 FAIL
"not a unique-cause HOST_ALLOC park". Those `device_hit=2048/host_hit=22080`
numbers are from **R122**, not R124.

- `raw.log:287482` (and :287491, :287560) `rh_match_prepare rid=r124-p1-R-T …
  result=prepared reason=current_match fill_len=27170 device_hit_tokens=0
  host_hit_tokens=0` => T is **NON_DEVICE_RESIDENT and NON-HOST_RESIDENT**
  (`current_match` is the radix/anchor match, not residency).
- `raw.log:287483` `rh_preadmission_decision rid=r124-p1-R-T … staging_eligible=True
  restore_potential=True`.
- `raw.log:287493` `rh_preadmission_decision rid=r124-p1-R-T … wait_reason='SPEC_BUDGET'
  negative_cache_blocked=True negative_cursor=42775 spec_budget=42775 > 39321
  decision=exclude reason=negative_cache` => **T parks under SPEC_BUDGET**, the
  C2 condition. (The contract's C2 is the SPEC_BUDGET park; the tester required a
  HOST_ALLOC park, which is not C2.)
- C2 = PASS (park), NON_RESIDENT = PASS.

## Correction 3 — the actual chain break (what really happened)

Full window trace (raw.log line: event):
```text
287483 R-T preadmit hold state_funnel (staging_eligible=True)
287484 R-F1 ISSUED prefetch_length=42775
287493 R-T preadmit exclude negative_cache wait_reason=SPEC_BUDGET cursor=42775   <- C2 park
287575 R-T admission pos=1 qlen=3 running_bs=0 can_run=0                         <- T admitted
287621 R-F1 REVOKE miss_reason=alloc_failed
287622 R-F1 DISP disposition=WAIT (HOST_ALLOC park)
287630 R-F1 preadmit spec_release_epoch 8->9
287640 R-F1 ISSUED prefetch_length=42775  (F1 woke)
392544 R-F1 DISP PARTIAL (42752 vs 42775)
392554 R-F1 SUCCESS n_tokens=42750
```
So: T parked SPEC_BUDGET at 287493, but was **admitted (to recompute) at 287575
BEFORE the spec-budget release at 287630**, so the RH never issued T a prefetch
(`prefetch_issued(rid=R-T)=0`). T never reached HOST_ALLOC. That is the real
unmet leg — a scheduling race, NOT a durability failure.

## Correction 4 — the wake fix was NOT exercised in R124 (agree with tester)

The only HOST_ALLOC waiter was F1 (`host_alloc.v1` wait=1/wake=3/retry=1):
```text
287626 wait   free_kv 518 evict 3966 (4484 < 42752)  gen kv125/mamba176  blocked=[kv,mamba]
287627 wake   hold_no_generation (correct: kv insufficient)  mamba 176->177, kv 125->125
287636 wake   GRANT  gen kv125->139 AND mamba176->191   <- BOTH advanced
```
The grant at 287636 had BOTH domains advanced, so the OLD all-generations rule
would also have granted => the new capacity clause was not the deciding factor.
The fix remains unit-verified but **not runtime-exercised**.

## Net corrected R124 result

| item | tester | corrected (verified) |
|---|---|---|
| L3 durable pipeline | "broken" | WORKS (F1 restored 42752) |
| T NON_RESIDENT | FAIL | **PASS** (device_hit=0 host_hit=0) |
| T SPEC_BUDGET park (C2) | FAIL | **PASS** (287493) |
| C3 release->wake (T) | FAIL | FAIL (real break: T admitted at 287575 before release 287630) |
| C4 FULL durable restore (T) | FAIL | FAIL (T never issued) |
| wake fix exercised | "not reached" | not reached (F1 grant had both gens advance) |

Classification: **recipe/scheduling-race gap, NOT a durability defect and NOT a
new product failure**. No product change is licensed by R124.
