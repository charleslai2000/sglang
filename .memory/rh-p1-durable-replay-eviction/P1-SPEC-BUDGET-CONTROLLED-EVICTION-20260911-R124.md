# P1 SPEC_BUDGET controlled-eviction — R124 acceptance replay (rebuilt server)

- Task: `P1-SPEC-BUDGET-CONTROLLED-EVICTION-20260911-R124`
- Role: independent tester; owns the experiment. No child agents.
- Bundle: `work/R124-bundle/` (raw.log, probe.log, chain.json,
  condition-evidence.md, manifest.json, sha256sums.txt, driver124.py,
  requests.jsonl, state.jsonl).

## STATUS

**BLOCKED → P1 NOT_VERIFIED.** Run 1 of the frozen R121-faithful recipe executed
against the rebuilt server, but the experiment could not exhibit the chain because
the top-level precondition **FULL_DURABLE is unattainable on this server**: its L3
durable publish/ack path does not function (bytes are written, `storage_persisted`
never succeeds, storage queries report a full miss). The `scheduler.py`
wake-eligibility fix was therefore **never exercised on the target T**. One further
diagnostic probe confirmed the publish failure is independent of the recipe. No
corrected run was spent (see §Budget).

## VERIFIED SERVER FACTS

| item | value |
|---|---|
| server PID | `3082643` (started 01:57:13) |
| scheduler child | `3086752` |
| port / health | `30000` / `200` (`baseline-offsets.txt:15`) |
| repo HEAD | `4f41f5bab562b99562f30c67540eb05344d13637` |
| scheduler.py sha256 | `892efc25e2a9ef7c5ebb4afa09cf6914182b1467981d14cd76c53eea5d8de9d7` |
| launch script sha256 | `2259d406f8f2239289d799bfd7bffd6401dedd101ed90225ddc05508cf8caaa3` |
| new server log | `/mnt/data/neuron/sglang-3090-r112-20260911/sglang-server-r124.log` |
| build binding | scheduler.py content sha (the `source_build` marker is the known constant defect, not used) |

Independent source binding: all other R121-manifest producer files
(`unified_radix_cache.py`, `telemetry_context.py`, `hicache_restore.py`,
`hybrid_cache_controller.py`, `ready_horizon.py`) are **byte-identical** to the
R121 bundle. Only `scheduler.py` changed → the rebuild is source-consistent with
the stated fix.

## GATE A / GATE B / t_feasible (target `r124-p1-R-T`)

**Not measurable.** The target never entered the HOST_ALLOC path. `host_alloc.v1`
census on the rebuilt server: `restore_host_alloc_wait=1`,
`restore_host_alloc_wake_decision=3`, `restore_host_alloc_retry_result=1`,
`host_allocability_change=69`, `restore_hybrid_finalize=1`; **every rid-bearing
event is `rid=r124-p1-R-F1` (the decoy)**.

| gate | reading | file:line |
|---|---|---|
| Gate A (before F1 stage) | n/a for T | — |
| Gate B (before T stage) | n/a for T (`restore_host_alloc_wait(rid=T)=0`) | — |
| `t_feasible` | n/a for T | — |
| `t_wake` | n/a for T | — |
| `t_deadline` | n/a for T | — |

The only available temporal record is the decoy F1, which is **not** the target:
```text
:288397  wait  fifo=0 blocked=[kv,mamba] free kv=518 evict kv=3966 deadline_mono_ns=19410611802296
:288398  wake  hold_no_generation  kv_gen 125->125  mamba_gen 176->177  cap 4484 < required 42752
:288407  wake  grant                kv_gen 125->139  mamba_gen 176->191
:288408  wake  release
:393312  disposition PARTIAL requested=42775 granted=42752 reason=shortfall
:393314  restore_hybrid_finalize
```
The `:288398` hold is **correct** under the new per-domain rule (kv generation
unchanged AND kv `free+evictable < required`), so no defect of the wake fix is
observed; the fix is simply untested on T.

## D_req DERIVATION

Not derivable for this run. The frozen definition is
`D_req = target L3 durable coverage (pc_storage_query.kv_hit_pages)` AND the Mamba
sidecar durable on the same boundary. For T's producer `r124-p1-build-T` the
durable coverage is **0** (`pc_storage_query.kv_hit_pages=0`,
`storage_hit_count=0`), so no positive durable boundary exists. Nominal request
size (for reference only) is T `fill_len=27170`; R121's target boundary was
`D_req=27328`.

## C1..C5 VERDICTS

| # | condition | verdict | key evidence |
|---|---|---|---|
| C1 | full durable coverage | **FAIL** | `sglang-server-r124.log:106108` `restore_disposition rid=r124-p1-build-T disposition=RECOMPUTE granted=0 reason=revoked:miss`; `pc_storage_query kv_hit_pages=0` |
| C2 | T park uniquely SPEC_BUDGET | **FAIL** | `:288261` reason=`negative_cache`, spec_used 42775 > limit 39321, `restore_state_before=NONE`, `wait_reason_before=null`, `staging_eligible=True`, `restore_potential=True`; no HOST_ALLOC park exists, so "host alloc not the limiter" is not exhibited |
| C3 | strict release→wake causality | **FAIL** | no T wake: `restore_host_alloc_wait(rid=T)=0`, `restore_host_alloc_wake_decision(rid=T)=0` |
| C4 | full restore gate (`kv_fetched==D_req`, Mamba complete, no recompute) | **FAIL / NOT_REACHED** | T served from in-memory cache (`:288250` `reason=current_match`); no `restore_disposition`, `restore_hybrid_finalize`, or `kv_fetched` for `r124-p1-R-T` |
| C5 | host headroom proven | **NOT_REACHED** | no T stage moment |

## FULL CHAIN LEGS

```text
T FULL_DURABLE(D_req)              FAIL   :106108 (producer revoked:miss; coverage 0)
T NOT_DEVICE_RESIDENT              PASS   :288250 device_hit=0 host_hit=0
Gate A                             n/a    no T host-alloc
F1 issue                           ok     :288253 (decoy)
T SPEC_BUDGET park (unique cause)  FAIL   :288261 negative_cache, no host-alloc
F1 revoke/release (epoch +1)       F1-only :288394/288397/288407/288408
T wake                             ABSENT restore_host_alloc_wait(rid=T)=0
Gate B                             n/a
T stage L3->L2                     n/a
Host-ready -> admission            n/a
kv_fetched == D_req                n/a
Mamba restore complete             n/a
generation                         completed from memory (no L3 restore)
```

## THE EXACT UNMET CONDITION

**Top-level precondition `FULL_DURABLE` is unattainable on the rebuilt server.**
Every build and pressure request was dispositioned `RECOMPUTE … revoked:miss`
(build-F1 `:32728`, build-F2 `:70248`, build-T `:106108`, q1..q5
`:138878 / :172749 / :209459 / :247929 / :288199`). The rebuilt server emitted
**zero** successful `storage_persisted` / `durability_barrier` (the only
`storage_persisted` from `process_id 3086752` is the startup warmup at probe line
40955 with `result=false, context_complete=false`; none after). Yet the L3 file
backend **is physically writing** (`330341` files under
`/mnt/data/neuron/sglang-3090-r112-20260911/l3` modified in the 25-minute window),
so the failure is in durable publication/ack + query visibility, not in raw I/O.

## SINGLE DECISIVE FILE:LINE

```
/mnt/data/neuron/sglang-3090-r112-20260911/sglang-server-r124.log:106108
restore_disposition rid=r124-p1-build-T disposition=RECOMPUTE requested=27169 granted=0 reason=revoked:miss
```
T's durable producer never reached FULL_DURABLE, so T could not enter the
SPEC_BUDGET→HOST_ALLOC→wake→restore chain. Corroborated by the absence of any
`restore_host_alloc_*` event for `rid=r124-p1-R-T` and by
`:288261` (T parked on `negative_cache`/SPEC_BUDGET with `restore_state_before=NONE`).

## CLASSIFICATION (product behaviour vs harness/profile)

- **Harness/recipe: ruled OUT.** A fresh independent probe
  (`r124-probe-dur-1`, 17647 unique tokens) reproduced the identical class:
  `prefetch_revoke storage_hit=0 miss_reason=miss` → `restore_disposition
  RECOMPUTE reason=revoked:miss`, 0 `storage_persisted`. The R121 driver recipe was
  verified to reproduce FULL_DURABLE on the pre-rebuild server (R121 bundle).
- **Measured `scheduler.py` wake fix: NOT implicated (not reached).** No failure of
  `_host_alloc_wait_eligible` was exercised on T; the only observed wake hold
  (decoy F1 `:288398`) is correct under the new per-domain rule.
- **Residual blocker: server-side durable publication.** The evidence supports
  "L3 bytes written but durable publish/ack and query hits never happen". Whether
  this is a product regression introduced by the rebuild, an L3 file-store state
  problem (2.74M pre-existing entries loaded at startup), or an infrastructure
  issue is **not** asserted here; it is a hard causal question for
  `debugger-deep`/the owner. The tester records the evidence only.

## BUDGET

- Live runs: **1 of 2** used. A second (corrected) run was intentionally not spent:
  the failure is not a harness/recipe defect, so no recipe correction can make
  `FULL_DURABLE` achievable. "Do not repeat an unchanged procedure."
- HTTP requests: 14 (run 1) + 4 (two diagnostic probes) = 18 ≪ 200.
- Wall: ~02:01 → ~02:18 (~17 min) ≪ 60 min.
- Constraints respected: no server restart/signal; no profile/param change; no
  `/flush_cache`; no `/close_session`; no edits under `python/sglang/`; no new
  instrumentation (existing endpoints/events only).

## DECISIONS REQUIRING USER AUTHORITY

None taken. The follow-on requires user authorization for **one** of:
1. dispatch `debugger-deep` to root-cause the durable-publish failure read-only; or
2. authorize a server restart / L3-store reset (explicitly out of scope here) to
   test the store-state hypothesis; or
3. authorize inspection of the L3 file backend internals.

## FOLLOW-ON (for orchestrator, not spawned here)

`debugger-deep`: root-cause why the rebuilt server writes L3 bytes yet never
publishes `storage_persisted`/`durability_barrier` and always reports
`revoked:miss`; discriminate product regression vs L3-store state vs infra.
Evidence: `work/R124-bundle/`, decisive line `sglang-server-r124.log:106108`,
warmup `storage_persisted` probe line 40955 (`result=false`), 330341 L3 files
written, fresh probe `r124-probe-dur-1`.
