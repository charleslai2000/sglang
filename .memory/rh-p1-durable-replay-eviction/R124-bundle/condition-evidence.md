# R124 condition evidence (run 1, R121-faithful recipe on the rebuilt server)

Status: **NOT_VERIFIED** — the frozen chain could not be exhibited.
All references are to `/mnt/data/neuron/sglang-3090-r112-20260911/sglang-server-r124.log`
(`raw.log` is the verbatim slice `[769, 393328]`, offset = server line - 768) unless
noted as `probe` (`/tmp/t38c-probe.log`, run slice in `probe.log`).

## Verified server / build facts

- server PID `3082643`, scheduler child `3086752`, port `30000`, `/health` 200
  (`baseline-offsets.txt:1-15`).
- repo HEAD `4f41f5bab562b99562f30c67540eb05344d13637`.
- live `python/sglang/srt/managers/scheduler.py` sha256
  `892efc25e2a9ef7c5ebb4afa09cf6914182b1467981d14cd76c53eea5d8de9d7` (the fix).
- **All other R121-manifest producer files are byte-identical to the R121 bundle**
  (`unified_radix_cache.py 5d3db152…`, `telemetry_context.py d55b057c…`,
  `hicache_restore.py 1cc9d2b8…`, `hybrid_cache_controller.py a71acb88…`,
  `ready_horizon.py 954161ce…`). So the rebuild changed only `scheduler.py`.
- `source_build` marker is the known constant defect and is NOT used to bind the build.

## Top-level precondition

| condition | verdict | evidence |
|---|---|---|
| FULL_DURABLE | **FAIL** | see below |
| NOT_DEVICE_RESIDENT | PASS | `:288250` first T match `fill_len=27170 device_hit_tokens=0 host_hit_tokens=0` |
| HOST_HEADROOM_SUFFICIENT | NOT_REACHED | T never entered HOST_ALLOC |

### FULL_DURABLE FAIL — decisive

Every build and pressure request was dispositioned `RECOMPUTE … revoked:miss`
(no durable L3 coverage):
```text
:32728   restore_disposition rid=r124-p1-build-F1 disposition=RECOMPUTE requested=42775 granted=0 reason=revoked:miss
:70248   restore_disposition rid=r124-p1-build-F2 disposition=RECOMPUTE requested=42770 granted=0 reason=revoked:miss
:106108  restore_disposition rid=r124-p1-build-T disposition=RECOMPUTE requested=27169 granted=0 reason=revoked:miss
:138878  q1 … :288199 q5  (all RECOMPUTE revoked:miss)
```
`probe` `pc_storage_query` for the producer `r124-p1-build-T`:
`kv_hit_pages=0, storage_hit_count=0, query_suffix_len=27169, sidecar_hits={"kv":2}`.

The durable publish channel never succeeded from the rebuilt server:
```text
probe  storage_persisted from process 3086752: exactly 1 (startup warmup, line 40955, result=false, context_complete=false)
probe  storage_persisted after the run baseline (line >40960): 0
probe  durability_barrier  from the rebuilt server: 0
```
Yet the L3 file backend **is physically writing**: `330341` files under
`/mnt/data/neuron/sglang-3090-r112-20260911/l3` were modified in the 25-minute
window (newest 02:17). So bytes land on disk but the durable publish/ack never
fires and queries report a full miss.

An independent fresh probe (`r124-probe-dur-1`, 17647 unique tokens, 1 completion)
reproduced the same class: `:prefetch_revoke … storage_hit=0 miss_reason=miss`,
`:restore_disposition … RECOMPUTE reason=revoked:miss`, and 0
`storage_persisted` in the new probe bytes. This rules out the R121 recipe as the
cause.

## Frozen chain legs (target `r124-p1-R-T`)

| leg | verdict | file:line |
|---|---|---|
| T FULL_DURABLE(D_req) | FAIL | `:106108` (producer miss); no storage_persisted |
| T NOT_DEVICE_RESIDENT | PASS | `:288250` device_hit=0 host_hit=0 |
| Gate A | NOT_REACHED | no T host-alloc event |
| F1 issue | observed (decoy) | `:288253` restore_state RESTORING |
| T SPEC_BUDGET park (unique cause) | FAIL | `:288261` reason=negative_cache, `restore_state_before=NONE`, `wait_reason_before=null`, spec_used 42775 > limit 39321 |
| F1 revoke/release epoch +1 | observed for F1 only | `:288394`/`:288397`/`:288407`/`:288408` (rid R-F1) |
| T wake | **absent** | `restore_host_alloc_wait(rid=T)=0`; `restore_host_alloc_wake_decision(rid=T)=0` |
| Gate B | NOT_REACHED | — |
| T stage L3->L2 | NOT_REACHED | — |
| Host-ready / admission | NOT_REACHED | — |
| `kv_fetched == D_req` | NOT_REACHED | — |
| Mamba restore complete | NOT_REACHED | — |
| generation | completed (in-memory serve) | `:288250` `reason=current_match`; no restore_disposition for R-T |

`host_alloc.v1` event census on the rebuilt server (all rid-bearing records are
the decoy): `restore_host_alloc_wait=1`, `restore_host_alloc_wake_decision=3`,
`restore_host_alloc_retry_result=1`, `host_allocability_change=69`,
`restore_hybrid_finalize=1` — **all six rid-bearing records are
`rid=r124-p1-R-F1`**.

## Decisive temporal record

| field | value |
|---|---|
| D_req | not measurable (no T host-alloc wait) |
| host free_before / reclaimed / free_after | n/a |
| t_feasible | n/a |
| blocked_domains | n/a |
| kv/mamba generation before/after | n/a |
| t_wake / t_deadline | n/a |

The only host-alloc temporal data belongs to the **decoy F1**, not the target:
```text
:288397  wait  fifo=0 blocked=[kv,mamba] free kv=518 evict kv=3966 deadline_mono_ns=19410611802296
:288394  retry revoked_alloc_failed required=42752 free_after=518 (kv)
:288398  wake  hold_no_generation  kv_gen 125->125, mamba_gen 176->177, cap 518+3966=4484 < 42752
:288407  wake  grant                kv_gen 125->139, mamba_gen 176->191
:288408  wake  release
:393312  disposition PARTIAL requested=42775 granted=42752 reason=shortfall
```

### Note on the fix itself (F1, decoy)

At `:288398` the new per-domain eligibility holds correctly: the kv generation did
**not** advance **and** `free+evictable (4484) < required (42752)`, so the hold is
justified. The fix is not observed as defective; it was simply never exercised on
the target, because T never became FULL_DURABLE and never entered HOST_ALLOC.

## C1–C5 verdicts

- **C1 full durable** — FAIL: T producer coverage 0 (`:106108`, `pc_storage_query`).
- **C2 park uniquely SPEC_BUDGET** — FAIL: `:288261` is a SPEC_BUDGET/`negative_cache`
  exclusion with no host-alloc park; the frozen condition requires a HOST_ALLOC
  park proved not host-limited.
- **C3 release → wake causality** — FAIL: no T wake at all.
- **C4 full restore gate** — FAIL/NOT_REACHED: no `kv_fetched`, no hybrid finalize,
  no Mamba restore for T.
- **C5 host headroom** — NOT_REACHED.

## Pressure / drain

All 5 pressure requests returned 200 but each was itself `RECOMPUTE revoked:miss`
(q1 `:138878` … q5 `:288199`), and `driver124` logged `drain drained=false`
(server never reported fully idle within the 240 s wait). Because the durable
store was not publishing, pressure could not re-derive L3-anchored state.

## Classification

Residual blocker is **server-side durable publication** on the rebuilt server
(physical L3 bytes written, `storage_persisted`/`durability_barrier` and query
hits absent). It is **not** the R121 recipe (fresh probe reproduces it) and **not**
an observed failure of the `scheduler.py` wake fix (never reached on T). Whether
this is a product regression or an L3-store/infrastructure state issue requires
the debugger/owner; the tester records the evidence and does not assert causality.

No second (corrected) run was spent: no harness/recipe correction can make
FULL_DURABLE achievable while the server-side publish path is non-functional, and
the budget authorizes a corrected run only to repair a concrete failure of the
measured mechanism.
