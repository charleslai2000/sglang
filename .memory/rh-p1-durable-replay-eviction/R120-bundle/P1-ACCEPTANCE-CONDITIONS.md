# P1 SPEC_BUDGET full-chain acceptance conditions (FROZEN, user-ratified)

- Task: `P1-SPEC-BUDGET-FULLCHAIN-20260911-R120`
- Frozen by: orchestrator, on user ruling (2026-09-11) — approved with these 5
  mandatory conditions. R120 may be closed PASS only if ALL hold for the single
  target identity T.
- Rule: no decoys; no product-code change; no instrumentation; do not enlarge the
  workload. If any condition cannot be met, R120 = honest NOT_VERIFIED naming the
  exact unmet condition. A PARTIAL restore is a FAIL; absence of a
  `restore_recompute` event is NOT an acceptable proxy for completeness.

## C1 — T full durable coverage (storage-backed; NOT via durability_barrier)
For target T (session/gen/build_rid identity consistent everywhere):
- `pc_storage_query.kv_hit_pages == requested_prefix` (and `storage_hit_count ==
  requested_prefix`, `query_suffix_len >= requested_prefix`);
- the target L3 page-set / object hashes exist (R116 storage-backed semantics:
  enumerated objects exist, non-empty, hash-matching);
- Mamba sidecar durable for the same identity (`backup_ack_drain`/durable ACK
  `mamba_durable is True`; finalize `sidecars.mamba.expected==fetched==1`);
- `session_id` + `session_generation` + `build_rid` identical across park,
  storage query, and finalize.
If a small structural delta exists (e.g. the final generated token is not a
cached page), report it explicitly with its cause; it does NOT auto-pass.

## C2 — T park uniquely attributed to SPEC_BUDGET
At the T park moment, all must hold:
- `spec_budget` requested exceeds the available speculative budget
  (`spec_budget_used_tokens > speculative_budget_limit_tokens`), on the
  `spec_budget` subscribed epoch;
- host pool was sufficient at that instant (record `free_units`/`evictable_units`
  /`full_locked` and show host alloc was NOT the limiter);
- the park reason is NOT `HOST_ALLOC`;
- the park reason is NOT `DEVICE_QUOTA` and not any other admission limiter;
- `negative_cache` reason attributable to SPEC_BUDGET (parked candidate was
  `staging_eligible=True` and `restore_potential=True`).

## C3 — strict release -> wake causality
All in order, for the same identities:
1. F1 issue/reservation (`prefetch_issued` for F1; reservation recorded);
2. T SPEC_BUDGET park (C2);
3. F1 **exactly-once** release advancing the budget epoch by exactly +1
   (`spec_budget_release_epoch` before/after differing by 1; one F1
   release/revoke event);
4. T wake/reissue (`rh_preadmission_decision` decision=issue at the advanced
   epoch, or documented demand-restore) — and the wake must be attributable to
   THIS release epoch, not an unrelated event (show no other epoch-advancing
   event between 3 and 4).

## C4 — full restore gate (all required)
For T, ALL of:
```text
restore_disposition.disposition == FULL
restore_disposition.granted   == requested
pc_storage_query.storage_hit  == requested
restore_hybrid_finalize.kv_fetched == requested
Mamba restore complete (sidecars.mamba fetched == expected == 1)
restore_success.n_tokens == requested
```
FAIL conditions (any one): `disposition == PARTIAL`; `reason == shortfall`; any
full-prefix/prefix recompute for T; `hybrid_discard`.
`restore_recompute` absent is necessary but NOT sufficient.

## C5 — host headroom proven sufficient BEFORE the run
Freeze, measured on the live server:
- F1 required tokens (`prefetch_length`);
- T required tokens (`requested_primary_tokens`);
- host `free_units` / `evictable_units` / `full_locked` at park and at stage;
- peak stage reservation (F1 + T);
- require `F1_required + T_required + margin < host_allocable` (state the margin
  and the basis for `host_allocable`).

## Closure
If C1–C5 all hold on one frozen bundle:
> **P1 CLOSED.** It then proves:
> `full-durable T -> SPEC_BUDGET park -> predecessor release -> release-epoch wake
> -> full L3->L2 stage -> admission -> full L2->L1 restore -> generation`.
Otherwise P1 stays NOT_VERIFIED with the exact unmet condition.
