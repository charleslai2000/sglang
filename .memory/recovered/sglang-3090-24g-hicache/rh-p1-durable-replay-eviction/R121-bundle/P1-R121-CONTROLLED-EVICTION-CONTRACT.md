# R121 controlled-eviction P1 closure — FROZEN experiment contract (user-ratified)

- Task: `P1-SPEC-BUDGET-CONTROLLED-EVICTION-20260911-R121`
- Frozen by: orchestrator, on user ruling (2026-09-11). Option 1 only.
- Purpose: close P1 by proving, for ONE target identity T, the chain
  `full-durable T -> SPEC_BUDGET park -> F1 exactly-once release (epoch +1) ->
  T wake/reissue -> full L3->L2->L1 restore (durable boundary) -> generation`,
  WITHOUT the HOST_ALLOC/headroom contamination that defeated R119/R120.

## Top-level invariant (hard precondition; fail-fast)

Before the measurement window may start, ALL THREE must hold and be evidenced:
```text
FULL_DURABLE && NOT_DEVICE_RESIDENT && HOST_HEADROOM_SUFFICIENT
```
If any is not achieved after the controlled-eviction preprocessing, STOP
immediately and return NOT_VERIFIED with the exact unmet precondition and its
measurements. Do NOT burn the measurement window.

## Design (user ruling): controlled eviction is PREPROCESSING, not part of the chain
1. Build F1 (~43000 tokens, > speculative limit) and T (~27000 tokens) with
   distinct sessions and unique first tokens; confirm storage-backed FULL durable
   coverage for both (C1 semantics below).
2. Apply **controlled pressure** whose ONLY purpose is to evict F1/T from GPU L1
   (device). Pressure is a precondition-manufacturer, NOT a measured participant.
3. Drain ALL pressure requests, then wait for the system to stabilise. Re-verify:
   - F1/T device residency = 0 / insufficient (not fully device-resident);
   - L3 durable coverage for F1/T still FULL (eviction did not lose durability);
   - host pool has recovered sufficient headroom;
   - no pressure request still holds a reservation / HOST_ALLOC / running slot
     (waiting_queue empty, running batch empty, no inflight reservation).
4. ONLY THEN open the measurement window:
   - F1 issue (consumes the speculative budget),
   - T parks with SPEC_BUDGET as the UNIQUE cause,
   - F1 stages from L3 and releases exactly once,
   - `spec_budget_release_epoch` advances by exactly +1,
   - T wakes/reissues attributable to THAT epoch,
   - T performs a full L3->L2 -> host-ready -> admission -> L2->L1 restore,
   - generation completes.

## Durable restore boundary (replaces raw `granted == requested`)

Define, per target T, the **durable restore boundary** `D_req`:
- `D_req` = the number of prefix tokens for which the target's L3 storage query
  reports durable coverage at restore time (`pc_storage_query.kv_hit_pages`),
  AND for which the target L3 objects exist and the Mamba sidecar for the same
  boundary is durable.
- The request's raw park `requested_primary_tokens` may exceed `D_req` by a
  **durable-boundary-external tail** (e.g. the single generated token, chunk
  alignment, or a non-checkpointed suffix). Such a tail must be explicitly
  identified and justified by evidence; it is NOT a failure.

Corrected C4 gate (all required):
```text
restore_disposition.disposition == FULL
restore_disposition.granted   == D_req
pc_storage_query.storage_hit  == D_req
restore_hybrid_finalize.kv_fetched == D_req
Mamba sidecar durable on the SAME restore boundary (fetched == expected)
restore_success.n_tokens == D_req
```
FAIL (any one):
- `disposition == PARTIAL` caused by a **genuine durable-prefix shortfall**
  (i.e. durable coverage < D_req, or granted < D_req for a non-external reason);
- any recompute of the **durable prefix** (tokens within `D_req`);
- `hybrid_discard`;
- an `alloc_failed`/host revocation that truncates the restore below `D_req`
  (that is a headroom failure, i.e. the HOST_HEADROOM precondition was not met).
NOT sufficient by itself: absence of a `restore_recompute` event.
Explicitly allowed: ordinary prefill/recompute strictly BEYOND `D_req`
(the durable-boundary-external tail), with evidence.

## C1 — full durable coverage (storage-backed; NOT durability_barrier)
`pc_storage_query.kv_hit_pages == D_req` (full durable prefix) with
`storage_hit_count == D_req`; the target L3 objects exist (non-empty,
hash-consistent with the frozen evidence); Mamba sidecar durable for the same
identity; `session_id` + `session_generation` + `build_rid` consistent across
park / storage query / finalize.

## C2 — T park uniquely SPEC_BUDGET
At the T park instant: `spec_budget_used_tokens > speculative_budget_limit_tokens`
on the `spec_budget` epoch; publish host `free_units`/`evictable_units`/
`full_locked` and show host allocation was NOT the limiter; park reason is NOT
`HOST_ALLOC`; NOT `DEVICE_QUOTA`; NOT any other admission limiter; the parked
candidate was `staging_eligible=True` and `restore_potential=True`.

## C3 — strict release -> wake causality
In order, same identities: (1) F1 issue/reservation; (2) T SPEC_BUDGET park;
(3) F1 exactly-once release advancing `spec_budget_release_epoch` by exactly +1;
(4) T wake/reissue at that advanced epoch — and show no OTHER epoch-advancing
event occurred between (3) and (4).

## C5 — host headroom proven sufficient at window start
Freeze: F1 required tokens; T required tokens; host `free_units` + `evictable_units`
+ `full_locked` at window start and at T stage; peak stage reservation;
require `F1_required + T_required + margin < host_allocable` (state the margin
and the basis for `host_allocable`), with the pressure fully drained.

## Closure
If the top-level invariant AND C1–C5 all hold on one frozen bundle:
> **P1 CLOSED** (controlled-eviction P1 closure).
Otherwise P1 stays NOT_VERIFIED with the exact unmet precondition/condition.
Pressure is never counted as part of the causal chain.
