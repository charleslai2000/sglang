# P1-SPEC-BUDGET-CONTROLLED-EVICTION-20260911-R122

- Invocation: `ses-p1-controlled-eviction-r122-20260911`
- Contract (frozen, unmodified): `R121-bundle/P1-R121-CONTROLLED-EVICTION-CONTRACT.md`
  sha256 `2ac86b5a54264fad46d049e2c32e3cc37c125f8c778a38dfb14e840a37be3b3b`
  — VERIFIED match before starting.
- Server: PID 48746 / scheduler 48806, `http://127.0.0.1:30000`, health 200
  before and after. No server control, no repo edits, no product instrumentation.

## status: `not_verified`

## Binding addendum (applies; read after the run)

`R122-bundle/P1-R122-HEADROOM-GATE-ADDENDUM.md` sha256
`92ad1c29f4749be9fc4056a5e8d9dbb89d7800f652ccccdc2959651401faea25` is
user-ratified, additive to the R121 contract, and **governs the host-capacity
gates**. It defines `host_allocable := full_free + full_evictable`, forbids a
single pre-window `F1+T` gate, and requires a **sequential** chain with
**Gate A** (before F1 stage, `>= F1_D_req+margin`) and **Gate B** (before T
stage after the wake, `>= T_D_req+margin`, with F1's allocation proven
released). This run did not implement that design; that is the primary
harness/profile gap.

- Gate A (device basis): `raw.log:53635` `full_free=287 full_evictable=63201`
  → 63488 ≥ 41472+2048 → PASS.
- Gate B (device basis): `raw.log:178471` `full_free=415 full_evictable=65119`
  → 65534 → numerically PASS, but *after* T had already restored, so the
  ordering was never exhibited.
- **Basis discrepancy (source-verified; open issue):** the addendum's
  `full_free+full_evictable` is the *device/full* pool (65536)
  (`unified_radix_cache.py:4366-4368` → `:3018-3021`,
  `token_to_kv_pool_allocator`). The pool that actually blocked F1/R121 is the
  *L2 host* pool in `host_alloc.v1` (size 131073) = **2786** at the window
  (`raw.log:73694`; `host_allocability_snapshot` → `mem_pool_host`,
  `unified_radix_cache.py:3838-3876`, published by `scheduler.py:3856-3862`).
  The addendum's cited "post-drain host allocable ~65534 (R121
  raw.log:270084)" is actually a `[P2A] promotion_reserve` **device**-pool line.
  A literal device-basis Gate A/B therefore PASSES (63488 / 65534) while the
  host pool is 2786 → the window opens on a saturated host.
- **Observability blocker:** there is no read-only fresh HOST `evictable`
  source (`/metrics` = 404, `enable_metrics` false;
  `/get_server_info.kv_events` = null); `host_allocability_change` is heavily
  coalesced (~16 min stale). The gate as mandated cannot be correctly enforced
  read-only with the available interfaces.

## Hard precondition achieved? **N**

| item | value | ref |
|---|---|---|
| host allocable at window start | **2786** (free.kv 994 + evictable.kv 1792) | `raw.log:73694` / server 2656710 |
| F1 required | **41472** | `raw.log:73694` (`requested_primary_tokens`) |
| sum required (F1+T+margin 2048) | 67714 | `chain.json` |
| T device residency | **device_hit_tokens=2048**, host_hit_tokens=22080 (NOT evicted) | `raw.log:53628` / server 2636644 |
| F1/T durable coverage | build L3 writes present (T: 12 `storage_persisted`, 2048-chunk); **no `pc_storage_query`/`D_req`** because T restored from host | `probe.log`; `raw.log:53628` |
| pressure drained | yes: q1–q4 HTTP 200, `/v1/loads` running=0 waiting=0 | `requests.jsonl`, `gate_evidence.jsonl` |

## Enforced drain gate (the fix) — implemented but DEFECTIVE

- Implemented in `R122-bundle/driver122_gate.py`: poll `/health` host free
  (`host_headroom`) + published host evictable until
  `free+evictable >= peak_stage_required + 2048`.
- The gate **passed on attempt 1** using free=994 (`raw.log:53620`) and
  evictable=42942 from server line 2582830 — an R121
  `host_allocability_change` at wall 00:34:09, **~16 min stale** because that
  telemetry is heavily coalesced. Computed allocable 43936 ≥ 43540.
- The **fresh** `host_alloc.v1` snapshot taken moments later by F1's own
  attempt (`raw.log:73694`, wall 00:50:49) gives free=994 + evictable=1792 =
  **2786**. So the precondition was NOT met and the window should not have been
  opened. This is a **harness defect** (stale evictable source), reported as
  such; the correct fail-fast verdict is NOT_VERIFIED.
- Device (`full`) pool was ample and is not the constraint:
  T promotion `raw.log:53635` (`full_free=287 full_evictable=63201`),
  F1 promotion `raw.log:178471` (`full_free=415 full_evictable=65119`).

## Per-condition C1..C5

- **C1 full durable — NOT_ESTABLISHED.** No `pc_storage_query` for
  `r122-r122-R-T` (T matched a host-resident prefix), so `D_req` /
  `kv_hit_pages==storage_hit_count` cannot be read. Build-side L3 persistence
  exists (`probe.log`, session `r122-s-T-r122`).
- **C2 T park SPEC_BUDGET — FAIL.** Zero `SPEC_BUDGET` in `raw.log`. T
  scheduled first (cache hit) → `promotion_reserve n=22080` (`raw.log:53635`)
  → `admission.v2` (`raw.log:53637`); it never parked.
- **C3 release→wake — FAIL.** No T park, so no F1 release→T wake leg. F1 first
  `prefetch_issued` at `raw.log:53629` (41506). Batch ordering was T (host
  hit) before F1 (L3 miss), the reverse of R121.
- **C4 full restore gate — FAIL.** T restored only via L2→L1 promotion
  (`raw.log:53635`); no L3→L2 restore / storage query / durable-boundary
  finalize. F1 `restore_disposition PARTIAL requested=41506 granted=41472`
  (`raw.log:178460`).
- **C5 host headroom — FAIL.** Fresh allocable 2786 < F1_required 41472;
  effective margin −38686. Basis:
  `host_allocable := free_units.kv + evictable_units.kv` (`host_alloc.v1`).

## D_req vs raw requested

- `D_req`: **not derived** in this window (no L3 storage query for T).
- F1 raw requested 41506, granted 41472 (external tail 34,
  `raw.log:178460`).

## Exact unmet condition

- Top-level **HOST_HEADROOM_SUFFICIENT = FAIL** (fresh host allocable 2786 vs
  required 41472) **and** **NOT_DEVICE_RESIDENT = FAIL** (T device_hit=2048,
  host_hit=22080). Consequently C1–C5 cannot hold.
- The binding addendum's **sequential Gate A/Gate B ordering was not
  exhibited** (T restored before F1; no SPEC_BUDGET park).
- Classification: **harness/profile defect** (stale gate evictable reading;
  pressure without sessions failed to evict session-held T; `[F1,T]` batch let
  host-resident T schedule ahead of F1). The product's `HOST_ALLOC` park is
  consistent with R121; no new product defect is demonstrated.

## Why no corrected rerun was attempted

- R121's proven recipe built **F1+F2+T (~113k > device 65536)** with
  **sessioned** pressure q1–q5; R122 built only F1+T (~65.7k) with sessionless
  pressure, so T stayed resident. Restoring the recipe is possible, but neither
  gate interpretation can PASS: a device-basis gate re-opens on a saturated
  host, and a host-basis gate cannot be read fresh read-only. In R121 the host
  allocable peaked at ~24670 vs 27328 required, and only flush/close
  (forbidden) or new capacity would change that. A rerun would repeat known
  C1–C3 results without closing C4/C5, so budget was not spent.

## Decision required (orchestrator/user)

1. Which pool must Gate A/Gate B measure: the addendum's device
   `full_free+full_evictable`, or the L2 host pool that `HOST_ALLOC` actually
   blocks on (`host_allocability_snapshot`)?
2. What read-only fresh host-evictable interface is authorized, since none
   exists today (`/metrics` 404, `kv_events` null, coalesced events)?
3. Is a R121-faithful recipe (F1+F2+T + sessioned pressure) authorized for a
   corrected run, given the addendum mandates a sequential F1/T chain?

## Artifacts

`work/R122-bundle/`: `raw.log`, `probe.log`, `watch.log`, `requests.jsonl`,
`state.jsonl`, `gate_evidence.jsonl`, `chain.json`, `manifest.json`
(`p0b.raw-bundle.v3`), `baseline-offsets.txt`, `condition-evidence.md`,
`driver122.py`, `driver122_gate.py`.

sha256 (full list in `R122-bundle/sha256sums.txt`):
- `raw.log` `790cabec10968d9de3bf19125492b0c0f204c8e4fd650ac20c0abbd3b41bb8c2`
  (21,039,644 B)
- `probe.log` `67b5133a885c1e6b78a183998bff55cb7960b8a59095a61793035d1e2fc23614`
  (3,302,664 B)
- `chain.json` `a6e8a824e3a70f8ae8358d878c5480edb0b05ad85839a8d8ea9106b942bef015`
- `condition-evidence.md` `c64a2a16eebdd336b0b14408f574ee7bf67450483d2d2e016417d56824d9cb5f`
- `manifest.json` `e00f56e43c916546a37a36911b18396c5612fa9a4621a0d942285b5afb4e58f7`
- `P1-R122-HEADROOM-GATE-ADDENDUM.md` (binding, pre-existing)
  `92ad1c29f4749be9fc4056a5e8d9dbb89d7800f652ccccdc2959651401faea25`

## Budget

- Wall: ~16 min (limit 60). HTTP: ~50 requests (limit 200). Server left healthy
  (health 200); contract sha256 re-verified unchanged.
