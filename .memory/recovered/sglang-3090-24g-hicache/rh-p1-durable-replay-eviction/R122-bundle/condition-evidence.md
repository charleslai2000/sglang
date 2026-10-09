# R122 controlled-eviction P1 closure (drain-gate enforcement) — condition evidence

- Task: `P1-SPEC-BUDGET-CONTROLLED-EVICTION-20260911-R122`
- Invocation: `ses-p1-controlled-eviction-r122-20260911`
- Contract: `P1-R121-CONTROLLED-EVICTION-CONTRACT.md`, sha256
  `2ac86b5a54264fad46d049e2c32e3cc37c125f8c778a38dfb14e840a37be3b3b` (VERIFIED match)
- Frozen bundle: `raw.log` (server offsets 2583017..2761501), `probe.log`
  (bytes 46280601..49583265), `requests.jsonl`, `state.jsonl`,
  `gate_evidence.jsonl` (hashes in `manifest.json`)
- Measurement window: raw line 53626 / server line 2636642 / wall 2026-09-12
  00:50:31. Identity: `rid=r122-r122-R-T`, `session_id=r122-s-R-r122`,
  `session_generation=63`, durable producer `build_rid=r122-r122-build-T`,
  `build_session=r122-s-T-r122`.
- `raw.log` line = server line − 2583017 + 1.

## Verdict: NOT_VERIFIED

The mandated drain gate was implemented and run, but it did **not** actually
enforce the precondition: it passed on a 16-minute-stale host `evictable`
reading (telemetry coalescing), opening the window on a saturated host. The
fresh in-window `host_alloc.v1` snapshot gives host allocable **2786** tokens
against `F1_required=41472`. T was also never evicted from device/host
(`device_hit_tokens=2048`, `host_hit_tokens=22080`), so it never parked on
SPEC_BUDGET and the R121 chain was not reproduced. C1 is not evaluable; C2–C5
FAIL.

## Binding addendum (read after the run — must govern the capacity gates)

`P1-R122-HEADROOM-GATE-ADDENDUM.md` (sha256
`92ad1c29f4749be9fc4056a5e8d9dbb89d7800f652ccccdc2959651401faea25`) is
user-ratified and additive to the R121 contract. It (a) defines
`host_allocable := full_free + full_evictable`, (b) forbids a single pre-window
`F1+T` gate, and (c) requires a **sequential** chain with **Gate A** (before F1
stage, `>= F1_D_req+margin`) and **Gate B** (before T stage after wake,
`>= T_D_req+margin`, with F1's allocation proven released). This run did not
implement that design.

### Gate A on the addendum basis (device `full` pool)
- `raw.log:53635` (server 2636651): `full_free=287 full_evictable=63201`
  → allocable 63488 ≥ F1_D_req 41472 → **PASS (device basis)**.

### Gate B on the addendum basis (device `full` pool)
- `raw.log:178471` (server 2761487): `full_free=415 full_evictable=65119`
  → allocable 65534 ≥ T_D_req 24174 → **numerically PASS**, but this reading is
  *after* T had already restored, so the Gate-B ordering was never exhibited.

### Basis discrepancy (source-verified; open issue)
- The addendum's `full_free+full_evictable` is the **device/full** pool
  (size 65536). Source: `unified_radix_cache.py:4366-4368`
  (`_promotion_pool_observation`) → `:3018-3021`
  (`_component_available_size(FULL)` → `token_to_kv_pool_allocator`).
- The pool that actually blocked F1/R121 is the **L2 host** pool reported by
  `host_alloc.v1` (`free_units.kv+evictable_units.kv`, size 131073), which was
  **2786** at the window (`raw.log:73694`). Source:
  `unified_radix_cache.py:3838-3876` (`host_allocability_snapshot` →
  `controller.mem_pool_host.available_size()`), published as
  `restore_host_alloc_wait` by `scheduler.py:3856-3862`.
- The addendum's cited "post-drain host allocable ~= 65534 (R121
  raw.log:270084)" is in fact a `[P2A] promotion_reserve` line — a **device**
  pool number, not the host pool. R121 `chain.json` independently states
  `host_kv_pool_tokens: 131073` with basis `free_units.kv+evictable_units.kv`.
- Consequence: a literal device-basis Gate A/B **PASSES** (63488 / 65534) while
  the host pool is 2786 → the window opens on a saturated host.
- Observability blocker: no read-only fresh HOST `evictable` source exists
  (`/metrics` = 404, `enable_metrics` false; `/get_server_info.kv_events` =
  null); `host_allocability_change` is heavily coalesced (~16 min stale).

## Top-level hard precondition (fail-fast)

### FULL_DURABLE — NOT_ESTABLISHED (in window)
- Build side: T wrote 24186 tokens to L3 in 2048-token chunks (12
  `storage_persisted` events for `r122-s-T-r122`), with a `durability_barrier`
  observed by the driver (`state.jsonl evt=build_durability`, T barrier≥1).
- But T matched a host-resident prefix (`host_hit_tokens=22080`), so **no
  `pc_storage_query` was issued for `r122-r122-R-T`**. The C1 storage-query
  gate (`kv_hit_pages == storage_hit_count == D_req`) and `D_req` itself are
  therefore not obtainable in this window.

### NOT_DEVICE_RESIDENT — FAIL
- `raw.log:53628` (server 2636644, wall 00:50:31) T `rh_match_prepare`:
  `fill_len=24186`, `device_hit_tokens=2048`, `host_hit_tokens=22080`.
- T was device- **and** host-resident at window start. The controlled pressure
  did not evict the session-held T.

### HOST_HEADROOM_SUFFICIENT — FAIL
- Fresh snapshot from F1's own host-alloc attempt, `raw.log:73694`
  (server 2656710, wall 00:50:49): `free_units.kv=994`,
  `evictable_units.kv=1792` → `host_allocable = 2786` for
  `requested_primary_tokens=41472`.
- The enforced gate passed on `raw.log:53620` host free 994 + server 2582830
  evictable 42942 = 43936 ≥ 43540. That evictable event is R121's
  `host_allocability_change` at wall 00:34:09 (~16 min stale); the computed
  43936 was **not** a valid current measurement.
- Device (`full`) pool was ample and is not the binding constraint: T promotion
  `raw.log:53635` `full_free=287 full_evictable=63201 full_locked=2048`;
  F1 promotion `raw.log:178471` `full_free=415 full_evictable=65119`.

## C1 — full durable coverage — NOT_ESTABLISHED
- No `pc_storage_query` for T (host-resident restore); `D_req` undefined.
- Build durability exists (12 `storage_persisted`, 1 barrier), but the C1
  storage-query/sidecar join cannot be shown in this window.

## C2 — T park uniquely SPEC_BUDGET — FAIL
- Zero `SPEC_BUDGET` occurrences in `raw.log`.
- T was scheduled first (cache hit): `rh_match_prepare` raw 53628 →
  `promotion_reserve n=22080` raw 53635 → `admission.v2` raw 53637. T was
  restored from host L2; it never parked.

## C3 — strict release → wake causality — FAIL
- F1 first `prefetch_issued` raw 53629 (`prefetch_length=41506`), but T never
  parked, so there is no park/release/wake leg.
- Batch ordering was T (host hit) before F1 (L3 miss), the reverse of R121.

## C4 — corrected full restore gate — FAIL
- T restored via L2→L1 promotion only (raw 53635, n=22080); no L3→L2 restore,
  no storage query, no durable-boundary full restore.
- F1 `restore_disposition` raw 178460 `PARTIAL requested=41506 granted=41472
  reason=shortfall`; `restore_success n_tokens=41470` raw 178470.

## C5 — host headroom proven sufficient — FAIL
- `F1_required=41472`; `T_required` (L3 restore) would be ~24174;
  `sum+margin(2048)=67714`. Window-start fresh allocable = **2786**.
- Basis: `host_allocable := free_units.kv + evictable_units.kv` from
  `host_alloc.v1`. Effective margin = 2786 − 41472 = **−38686**.

## Mandatory drain-gate enforcement (the intended fix)
- Implemented in `driver122_gate.py`: poll `/health` host free
  (`host_headroom`) plus published host evictable until
  `free+evictable >= peak_stage_required+margin`.
- Result: passed on attempt 1 (`gate_evidence.jsonl`) with free=994,
  evictable=42942 (stale), allocable=43936 ≥ 43540. **Harness defect**:
  `host_allocability_change` is heavily coalesced, so the freshest kv event was
  16 minutes old; the gate did not measure the current host pool.
- Corrected evaluation against the same window: 2786 < 43540 → the gate must
  FAIL (fail-fast), and the window must not have been opened.

## Pressure drain evidence
- Pressure `r122-r122-q1..q4` (42861/42826/42769/42697 tokens,
  `session_id=null`) all HTTP 200; `/v1/loads` at the gate showed
  `num_running_reqs=0`, `num_waiting_reqs=0`, queues waiting=0.
- Drain was clean, but the pressure did not achieve its eviction goal: T
  remained `device_hit=2048`/`host_hit=22080` at the window.

## Failure classification
- Harness/profile defects (primary):
  1. gate evictable reading stale → window opened on a saturated host;
  2. pressure without session ids did not evict session-held T;
  3. `[F1,T]`-only batch let host-resident T schedule ahead of F1, so T never
     parked on SPEC_BUDGET.
- Product: F1's genuine `HOST_ALLOC` park at allocable 2786 is consistent with
  R121; no new product defect is demonstrated.

## Chain legs
- produced: `full-durable build of T` (L3 chunks), F1 L3 prefetch + PARTIAL
  restore, T host→device promotion, batch generation.
- missing: `SPEC_BUDGET park`, `F1 exactly-once release (epoch+1)`, `T wake`,
  `full L3→L2→L1 restore at the durable boundary`, `D_req`, terminal
  SPEC_BUDGET-chain generation.
