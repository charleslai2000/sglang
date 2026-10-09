# R122 additive binding addendum — two-moment host-headroom gates (FROZEN, user-ratified)

- Applies to `P1-SPEC-BUDGET-CONTROLLED-EVICTION-20260911-R122`, binding ADDITIVE
  to `work/R121-bundle/P1-R121-CONTROLLED-EVICTION-CONTRACT.md`
  (sha256 `2ac86b5a54264fad46d049e2c32e3cc37c125f8c778a38dfb14e840a37be3b3b`,
  unmodified). Where they differ, THIS addendum governs the host-capacity gates.
- User ruling (2026-09-11): the R121 core causal chain is proven; the only
  remaining P1 gate is whether host staging capacity is available AT THE CORRECT
  TIME. A single pre-window `F1+T+margin` gate is WRONG because F1's stage may
  still hold host slots, and because `F1+T > host_allocable` is structurally
  impossible here.

## Capacity arithmetic (binding)
```text
F1_D_req ~= 42944   (R121: F1 revoke requested 42958, storage_hit 42944)
T_D_req  =  27328   (R121 probe.log:3264; durable boundary; raw prefix 27339)
F1+T     ~= 70272
post-drain host allocable ~= 65534  (R121 raw.log:270084: free 2077 + evictable 63457)
=> F1 and T CANNOT be simultaneously host-resident. R122 MUST use a SEQUENTIAL
   chain. Do NOT wait for / require an `F1+T` gate.
```

## Gate A — before F1 issue/stage
Require and EVIDENCE (read-only, frozen refs + numbers):
```text
host_allocable >= F1_D_req + margin      (margin stated, >= 0)
```
with `host_allocable := full_free + full_evictable` (publish `full_locked` when
available), pressure fully drained, T not resident, F1/T FULL durable (C1).

## Gate B — the critical one: before T stage (after T wake)
Re-read capacity AT THAT MOMENT and EVIDENCE:
```text
host_allocable >= T_D_req + margin       (margin stated, >= 0)
```
AND prove F1's host allocation is actually released/evictable/admission-
transitioned so T is genuinely allocatable — not merely that pre-window total
capacity was sufficient. If F1 still holds host slots preventing T allocation,
wait (bounded) for F1's release/eviction/admission transition and re-measure; if
it never occurs, fail-fast and report.

## Frozen full-chain order R122 must exhibit (all real, same identities)
```text
T FULL_DURABLE(D_req)
-> T NOT_DEVICE_RESIDENT
-> Gate A: host_allocable >= F1_D_req + margin
-> F1 issue
-> T SPEC_BUDGET park          (unique cause; reason != HOST_ALLOC/DEVICE_QUOTA)
-> F1 revoke/release           (spec_budget_release_epoch exactly +1)
-> T wake/reissue at that epoch
-> Gate B: host_allocable >= T_D_req + margin
-> T stage (L3->L2)
-> Host-ready
-> admission
-> kv_fetched == D_req
-> Mamba restore complete
-> generation
```
Additional requirements: `durable-prefix recompute == 0`; `hybrid_discard == 0`;
`PARTIAL`/`shortfall` occurring WITHIN `D_req` = FAIL (a tail strictly outside
`D_req` is allowed and must be evidenced); HTTP completed; session/build/
generation identity continuous across all legs.

## C4 restated (durable boundary; unchanged from R121)
`disposition == FULL`, `granted == D_req`, `storage_hit == D_req`,
`kv_fetched == D_req`, Mamba sidecar durable on the same boundary,
`restore_success.n_tokens == D_req`. NOT `granted == raw requested`.

## Closure
If the full-chain order holds with Gate A AND Gate B evidenced on one frozen
bundle, plus C1–C4 and safety -> **P1 CLOSED. No further experiment needed.**
Otherwise P1 remains NOT_VERIFIED with the exact unmet gate/leg.

## Status wording (user-approved)
> P1 **NOT_VERIFIED**, but the scheduler/RH liveness core is proven PASS.
> Sole remaining gate: whether T completes a full durable restore under
> sufficient host headroom at the CORRECT TIME (Gate B).
