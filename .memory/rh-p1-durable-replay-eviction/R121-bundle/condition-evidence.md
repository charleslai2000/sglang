# R121 controlled-eviction P1 closure — condition evidence

- Task: `P1-SPEC-BUDGET-CONTROLLED-EVICTION-20260911-R121`
- Invocation: `ses-p1-controlled-eviction-r121-20260911`
- Contract: `P1-R121-CONTROLLED-EVICTION-CONTRACT.md`, sha256
  `2ac86b5a54264fad46d049e2c32e3cc37c125f8c778a38dfb14e840a37be3b3b` (VERIFIED match)
- Frozen bundle: `raw.log` (offset 2312756, wall 2026-09-12 00:28:40..00:34:09),
  `probe.log` (offset 25948), `requests.jsonl`, `state.jsonl` (hashes in `manifest.json`)
- Measurement window: raw line 103819 / server line 2416575 / wall 2026-09-12 00:32:50.
  Identity: `rid=r121-p3-R-T`, `session_id=r121-s-R-p3`, `session_generation=60`,
  durable producer `build_rid=r121-p3-build-T`, `build_session=r121-s-T-p3`.

## Verdict: NOT_VERIFIED

Top-level hard precondition unmet: **HOST_HEADROOM_SUFFICIENT = FAIL**.
Consequently C4 (full restore gate) and C5 (host headroom) FAIL and the
`l2_to_l1_restore_generation` leg of the chain is not produced. C1, C2, C3 PASS.

## Top-level hard precondition (fail-fast)

### FULL_DURABLE — PASS
- `probe.log:3264` (target `pc_storage_query`): `query_suffix_len=27339`,
  `kv_hit_pages=27328`, `storage_hit_count=27328`,
  `sidecar_hits={"kv":27328,"mamba":27328}`.
- Durable restore boundary `D_req = kv_hit_pages = 27328`; Mamba sidecar durable on
  the same boundary (27328). Build durability barriers: F1=21, F2=21, T=14.

### NOT_DEVICE_RESIDENT — PASS
- `raw.log:103819` (server 2416575), T `rh_match_prepare current_match` after
  controlled eviction + full drain: `device_hit_tokens=0`, `host_hit_tokens=0`,
  `fill_len=27340`. F1 also reports `device_hit_tokens=0`, `host_hit_tokens=0`.
- No `r121-p3-q1..q5` event occurs at or after the window start (last pressure
  admission server 2416514 / wall 00:28:40; window start 00:32:50; gap 4m10s).

### HOST_HEADROOM_SUFFICIENT — FAIL
- Host KV pool = 131073 tokens (R117 frozen profile).
- `host_allocable := free_units.kv + evictable_units.kv` (basis: `host_alloc.v1`
  events; `full_locked` is not published in the available telemetry — measurement
  limitation, Verdict is invariant to it because free+evictable alone is already
  far below the requirement).
- Window start (F1 host wait, raw 103892 / server 2416648):
  `free.kv=162`, `evictable.kv=8000` → allocable **8162** < F1_required **42944**.
- T stage (raw 125841 / server 2438597): `free.kv=98`, `evictable.kv=6080`
  → allocable **6178** < T_required **27328**.
- After full reclaim (raw 224763 / server 2537519): `reclaimed=22526`,
  `free_after=24670`, `evictable_after=0` → allocable **24670** < 27328.
- F1 required 42944 + T required 27328 = 70272, far above the observed allocable
  host capacity. The precondition was therefore not achieved.

## C1 — full durable coverage — PASS
- `pc_storage_query.kv_hit_pages == storage_hit_count == 27328 == D_req`.
- Mamba sidecar durable for the same boundary (27328).
- `D_req = 27328`; raw requested suffix = `query_suffix_len = 27339`
  (disposition requested 27339); external tail = **11 tokens** (durable-boundary
  external, chunk alignment/generated token) — explicitly justified per contract
  §Durable restore boundary.
- Caveat (identity join): park/query use replay identity `r121-p3-R-T`
  (session `r121-s-R-p3` gen 60) while the durable producer is build session
  `r121-s-T-p3` (`build_rid=r121-p3-build-T`). The `pc_storage_query` record
  itself carries `session_id=null`, `session_generation=null`, `build_rid=null`
  (only `rid=r121-p3-R-T`), and no T finalize exists to join (restore failed),
  so the full `build_rid` triple-consistency across park/storage-query/finalize
  cannot be shown; coverage + sidecar identity are fully shown.

## C2 — T park uniquely SPEC_BUDGET — PASS
- T park `raw.log:103830` (server 2416586): `decision=exclude`,
  `reason=negative_cache`, `speculative_budget_used_tokens=42958` >
  `speculative_budget_limit_tokens=39321`, `negative_cache_blocked=True`,
  `negative_cursor=42958`, `staging_eligible=True`, `restore_potential=True`,
  `headroom_tokens=162`.
- F1 issue `raw.log:103821` (server 2416577): `prefetch_issued 42958` (consumes the
  speculative budget). F1 exclude at server 2416585 `reason=no_restore_potential`,
  `spec_used=42958`.
- Park cause is SPEC_BUDGET (negative cache cursor), NOT `HOST_ALLOC`,
  NOT `DEVICE_QUOTA`: `restore_state_before=NONE`, `wait_reason_before=null`.

## C3 — strict release → wake causality — PASS
Ordered, same identity:
1. F1 issue/reservation: `raw.log:103821` (server 2416577), `prefetch_length=42958`.
2. T SPEC_BUDGET park: `raw.log:103830` (server 2416586), epoch snapshot 96.
3. F1 exactly-once release: `raw.log:103888` (server 2416644)
   `prefetch_revoke reason=alloc_failed`, `requested=42958`, `storage_hit=42944`,
   `storage_generation=1037`; `CausalEpochs.spec_budget_release_epoch` 96 → 97
   (last epoch-96 snapshot server 2416576; first epoch-97 snapshot server 2416653).
4. T wake/reissue at the advanced epoch: `raw.log:103899` (server 2416655)
   `prefetch_issued`, `raw.log:103901` (server 2416657) `rh_preadmission_decision
   decision=issue spec_budget_release_epoch=97 issue_origin=READY_HORIZON`.
No OTHER epoch-advancing event occurred between (3) and (4): the only intervening
events are F1 `restore_disposition reason=revoked:alloc_failed` (raw 103889) and
F1 `restore_state WAIT_CAPACITY reason=HOST_ALLOC` (raw 103891), which do not
advance `spec_budget_release_epoch`.
Post-wake note: a SECOND independent release advanced 97 → 98 at `raw.log:25845`
(server 2438601) from T's own `prefetch_revoke reason=alloc_failed`
(`raw.log:25837` / server 2438593); it lies after step (4) and belongs to the C4
host-revocation failure, not to the F1→T wake chain.

## C4 — corrected full restore gate — FAIL
- Restore never reached `FULL`. T was woken at epoch 97, then host allocation was
  revoked twice:
  - `raw.log:125839` (server 2438595) `restore_host_alloc_retry_result
    revoked_alloc_failed`, `required=27328`, `alloc1=false`, `alloc2=false`,
    `reclaimed=0`, `free_after=98`, `evictable_after=6080`;
    disposition `raw.log:125840` (server 2438596) `revoked:alloc_failed`.
  - `raw.log:224763` (server 2537519) `revoked_alloc_failed`, `required=27328`,
    `reclaimed=22526`, `free_after=24670`, `evictable_after=0` → allocable
    **24670 < 27328**; disposition `raw.log:224764` (server 2537520)
    `revoked:alloc_failed`.
- Terminal T outcome: `raw.log:270213` (server 2582969) `restore_recompute
  cause=timeout`, `final_storage_survivability=host` (durable prefix recomputed).
- No `restore_success` and no `restore_hybrid_finalize` exists for T
  (`t_restore_success_present=false`, `t_hybrid_finalize_present=false`).
- Failure class per contract §FAIL: an `alloc_failed`/host revocation truncated the
  restore below `D_req` — this is a HOST_HEADROOM precondition failure, not a
  durable-coverage shortfall.

## C5 — host headroom proven sufficient at window start — FAIL
- `F1_required=42944`; `T_required=27328`; `F1_required + T_required = 70272`.
- Window start allocable `8162` (raw 103892); T stage allocable `6178`
  (raw 125841); after reclaim allocable `24670` (raw 224763).
- Requirement `F1_required + T_required + margin < host_allocable` is not met for
  any non-negative margin; effective margin = 24670 − 27328 = **−2658** at T stage.
- Basis: `host_allocable := free_units.kv + evictable_units.kv` from `host_alloc.v1`.
  `full_locked` is not published by available telemetry; this does not change the
  verdict because free+evictable alone is already below the requirement.
- Pressure fully drained (last pressure admission wall 00:28:40; window 00:32:50;
  zero pressure events in window) — so the shortfall is not an undrained-pressure
  artifact in this window.

## Chain legs
- produced: `full_durable T`, `SPEC_BUDGET park`, `F1 exactly-once release
  (epoch 96→97)`, `T wake/reissue at 97`.
- missing: `full L3→L2→L1 restore (durable boundary)` for T, and the terminal
  generation.

## Procedure note
The contract requires the three-way precondition to be evidenced and fail-fast
*before* opening the window. The driver operated on its `wait_idle` drain signal
and opened the window without independently proving host headroom; the host pool
was in fact below requirement. This is a harness/test gap, recorded as follow-up;
the returned verdict is unchanged (`NOT_VERIFIED`), and C2/C3 evidence retained.
