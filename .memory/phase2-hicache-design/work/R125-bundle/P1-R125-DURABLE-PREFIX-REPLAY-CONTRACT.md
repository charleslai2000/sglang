# R125 contract (FROZEN) — R121 durable-prefix restore replay (Option A)

- Applies to `P1-DURABLE-PREFIX-REPLAY-20260912-R125`.
- Binding additive superset of `R121-bundle/P1-R121-CONTROLLED-EVICTION-CONTRACT.md`
  (`2ac86b5a…b3b`) and `R123-bundle/P1-R123-TEMPORAL-WAKE-GATE-CONTRACT.md`
  (`bf7b09ee…1e1f8`). Gate basis is v2 (L2 host pool via `host_alloc.v1`).
- User ruling (2026-09-12): execute **Option A** — restore-path replay of R121's
  KNOWN durable prefix on the rebuilt server (which loads the HOST_ALLOC
  wake-liveness fix). NO product patch, NO profile change, NO workload redesign.

## Why A (R124 corrected conclusion)
R124 (same recipe as R121, fresh server) reached `NON_RESIDENT` + `SPEC_BUDGET
park`, but T was consumed by ordinary admission/recompute BEFORE the spec-budget
release, so the RH never issued T and the fixed wake predicate was never
exercised. Root difference from R121: R121's T was a **durable L3 restore
candidate** and stayed parked for the RH, whereas R124's T was **negative-cached**
(probe `pc_storage_query(build-T) kv_hit_pages=0`) and served by recompute.
A removes that difference by restoring the ALREADY-DURABLE R121 prefix.

## Identity gate (hard precondition 0)
R121's durable T prefix is still physically present in the L3 file backend:
`/mnt/data/neuron/sglang-3090-r112-20260911/l3`.

```text
R121 window-T key set (from R121-bundle/probe.log:3264, kv_hit_pages=27328):
195f0625351762a3a6d9a010b7f858b5990e260023ffeb0f9f16d64eeb75ca73
3f676d20b0be2678d9fd0288bf87b35369829da630ce243cbabd03076d76346b
e711270eff4efc26153823b2fd9cba8a66aec5f877d1ac62236553203ecc1257
cf38ec4b8b2668fbc8e8fb332adb53de2a528cd02534ea08661d1f3f27377806
dc50c5021520e84299afd7b2a4cbc15c5a8c34b27eb4f74f54296e2cbde59100
26827c2720166d4ba17ea34d73b798a4266b472490ebda37c7a3a994eada446b
5a996e2add555dffd4449e034c7faa24a7747a49371022716732d0a062274dae
adab1b6dcd6269838e76684555e7965656a12bafcaf806f7dd803020157d13df
key_set_sha256 = 73e15a5fa454204f8ac3b0d1181235999bacaeb59d71f9f5eb208444cf92dcb8
target_tokens  = 27328   (R121 D_req)
```
All 8 objects were re-verified present on disk (glob `<key>*.bin`).

**Gate 0 (mandatory):** the replay's T must query THIS key set (or an
identical-prefix superset with the same key_set_sha256 on the first 8) and the
storage query must report `kv_hit_pages == 27328`. A rebuild that produces a
DIFFERENT prefix is a FAIL (no silent "similar prefix").

Prompt determinism (reproduces R121's prefixes exactly): `driver121.py` with
`R121_NONCE=p1`; seeds `SEEDBASE=_NH%100000` from `sha256("p1")`;
`T_K=240+KOFF`, `T_WORDS=7000`, `F1_K=160+KOFF`, `F1_WORDS=11000`.

## Frozen chain (P1 final gate)
```text
R121 durable T present          (Gate 0: key_set_sha256, kv_hit_pages==27328)
-> T NON_RESIDENT               (device_hit_tokens==0 AND host_hit_tokens==0)
-> T SPEC_BUDGET park           (wait_reason='SPEC_BUDGET' / negative_cursor>39321)
-> F1 release epoch +1          (spec_budget_release_epoch advances by exactly 1)
-> RH issue of T                (ready_stage result=issued / prefetch_issued(rid=T)>0)
-> T HOST_ALLOC wait            (restore_host_alloc_wait rid=T)
-> FIXED predicate grants T     (see new-condition gate below)
-> T FULL restore (L3->L2)      (kv_fetched == D_req; Mamba restore complete)
-> generation
```

## Four hard gates (user-mandated)
1. **Identity:** Gate 0 above; T must hit R121's original L3 identity, not a
   rebuilt similar prefix.
2. **No premature consumption:** T must NOT be admitted/recomputed before the
   spec-budget release. Evidence: no `admission`/`Prefill batch` for T before the
   release epoch event; `prefetch_issued(rid=T)` must occur and its issue epoch
   must be >= the release epoch.
3. **New predicate condition observed:** the deciding condition must be the fix's
   new clause — at the grant, some blocked domain's generation did NOT advance
   while its current allocability satisfies the requirement
   (`free+evictable >= required`). Record per-domain `gen_before/after`,
   `free/evictable`, `required`. (If instead BOTH generations advanced, the old
   rule would also grant and the fix is NOT exercised — that is a NON-EVIDENCE
   outcome even if the restore succeeds.)
4. **FULL restore by durable boundary:** `disposition==FULL`, `granted==D_req`,
   `kv_fetched==D_req`, Mamba sidecar durable on the same boundary,
   `restore_success.n_tokens==D_req`; PARTIAL/shortfall/durable-prefix recompute =
   FAIL. A tail strictly outside `D_req` is allowed if evidenced.

Plus: `durable-prefix recompute == 0`, `hybrid_discard == 0`, HTTP completed,
session/build/generation identity continuous, `t_feasible < t_deadline`.

## Required record
`D_req`, T L3 key_set_sha256, T `device_hit/host_hit`, park `wait_reason`+cursor,
F1 release epoch before/after, T `prefetch_issued` epoch, T `host_alloc.v1`
wait/wake `free_before/reclaimed/free_after`, per-domain `kv/mamba`
`gen_before/after`, `t_feasible`, `t_wake`, `t_deadline`, `restore_disposition`,
`restore_success.n_tokens`, `restore_hybrid_finalize`.

## Constraints
No server restart; no profile/param change; FORBIDDEN `/flush_cache`,
`/close_session`; read-only w.r.t. product code; no new instrumentation; do not
modify R121–R124 artifacts. <= 2 live runs; <= 60 min; <= 200 HTTP.
