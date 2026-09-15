# R123 gate contract (FROZEN) — host feasibility timing vs HOST_ALLOC wake-liveness

- Applies to `P1-SPEC-BUDGET-CONTROLLED-EVICTION-20260911-R123`.
- Binding ADDITIVE superset of `R121-bundle/P1-R121-CONTROLLED-EVICTION-CONTRACT.md`
  (sha256 `2ac86b5a54264fad46d049e2c32e3cc37c125f8c778a38dfb14e840a37be3b3b`).
- Gate basis is v2 (`host_allocable := free_after_reclaim`, L2 host pool via
  `host_alloc.v1`). The v1 device-pool gate is **INVALIDATED**
  (`R122-bundle/P1-R122-GATE-V1-INVALIDATION.md`).
- User ruling (2026-09-12): R121 exposed TWO potentially independent problems.
  R123 must DISCRIMINATE them; it must not merge "headroom timing" with
  "multi-domain wake eligibility".

## The two problems to discriminate

1. **Host headroom timing.** T needs `D_req` (R121: 27328); after reclaim only
   24670 was available at retry (shortfall **-2658**); F1's 42942 host pages
   became reclaimable only near T's deadline.
2. **HOST_ALLOC wake eligibility.** R121: KV generation advanced (1229->1230)
   but Mamba stayed (1853->1853); `_host_alloc_wait_eligible`
   (`scheduler.py`) holds unless ALL blocked domains' generations advance. If KV
   release already made enough resource available, requiring a Mamba generation
   change too may be a genuine **liveness bug**, not a capacity limit.

## Frozen chain R123 must exhibit (same identities)

```text
T FULL_DURABLE(D_req)
-> T NOT_DEVICE_RESIDENT
-> Gate A: host (L2) allocable >= F1_D_req + margin
-> F1 issue
-> T SPEC_BUDGET park            (unique cause)
-> F1 revoke/release             (spec_budget_release_epoch exactly +1)
-> HOST_ALLOC retry              (restore_host_alloc_retry_result)
-> first feasible host timestamp (t_feasible)
-> wake eligibility              (restore_host_alloc_wake_decision)
-> FULL stage/restore (L3->L2)   (kv_fetched == D_req)
-> Host-ready -> admission -> Mamba restore complete -> generation
```

## Decisive temporal criterion (REQUIRED)

Record the **exact first moment** at which T's host-feasibility holds:

```text
t_feasible := first timestamp t where, on the L2 host pool for the blocked
              domains, the reclaimable capacity is sufficient:
                 kv:    free_kv(t)    + evictable_kv(t)    >= D_req
                 mamba: free_mamba(t) + evictable_mamba(t) >= required_aux_units
              (t_feasible is a property of the SERVER STATE, independent of
               whether T was woken.)
```

Compare with `t_wake` (first `restore_host_alloc_wake_decision` granting T, or
the hold) and `t_deadline` (T's `deadline_mono_ns` from
`restore_host_alloc_wait`).

### Verdict rules (frozen)

| condition | verdict |
|---|---|
| `t_feasible < t_deadline` but T did NOT wake / was held because Mamba generation did not change | **PRODUCT LIVENESS FAIL** — must fix `_host_alloc_wait_eligible` blocked-domain semantics; a workaround recipe is NOT acceptable |
| `t_feasible >= t_deadline` | capacity/timing shortfall at this profile/workload — NOT a wake bug |
| `t_feasible < t_wake < t_deadline` and final FULL restore | **P1 PASS** |

Plus the standing chain/C1–C4 conditions: `durable-prefix recompute == 0`;
`hybrid_discard == 0`; PARTIAL/shortfall within `D_req` = FAIL (tail strictly
outside `D_req` allowed and must be evidenced); HTTP completed; identity
continuous.

## Required output record (per run)

```text
D_req
host free_before        (kv, per blocked domain)
reclaimed               (kv, per blocked domain)
free_after              (kv, per blocked domain; = free_after_reclaim)
t_feasible
blocked_domains
kv_generation_before / kv_generation_after
mamba_generation_before / mamba_generation_after
t_wake
t_deadline
```

## Diagnostic run (conditional; NOT a default fallback)

A **shrink-T** run (`T < observed reclaimable ceiling`, e.g. < 24670) is
authorized ONLY as a discriminator, never as a substitute for the frozen-gate
run:
- If the small-T run STILL holds on `mamba generation unchanged`, that is
  **direct evidence of the product liveness bug**.
- A PASS on small-T alone does NOT close P1 for the `D_req = 27328` case.

## Budget / constraints (unchanged)
<= 2 live runs; <= 60 min; <= 200 HTTP. No server restart; no profile/param
change; no `/flush_cache`; no `/close_session`; no `python/sglang/` edits; no new
instrumentation. GPU ops under `/mnt/data/gpu/3090.lock`.
