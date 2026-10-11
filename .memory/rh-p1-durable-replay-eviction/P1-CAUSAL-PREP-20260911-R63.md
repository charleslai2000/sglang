# P1 identity-consistent causal-chain coverage & A/B preparation — R63

- ENTRY: ACCEPT
- task_id: `P1-CAUSAL-PREP-20260911-R63`
- invocation: `ses-p1-causal-prep-r63-20260911`
- role: `scout`
- epoch: `2026-09-11`
- status: `done`
- scope: read-only local inspection of the existing tests, drivers/vehicles,
  telemetry emitters, and design contracts relevant to the P1 gate
  (`SPEC_BUDGET park -> reservation/release epoch transition -> RH wake ->
  L3->L2 stage -> Host-ready -> admission -> L2->L1 restore -> generation`) and
  its checks (`cached_tokens > 0`, full-prefix recompute = 0,
  `hybrid_discard = 0`, identity `RID/session/node/build/generation`).
  No remote access, no experiments, no product/test/gate/storage/Git change, no
  engine start. Only this report was written.
- gate position: **P0-B remains NOT_VERIFIED and P0-C remains NOT_VERIFIED; P1 is
  not executed by this invocation and this report is not P1 acceptance.** It
  prepares the P1 gate so it can run once P0-B/P0-C close. P1 itself is still
  gated by plan.md (P1 `depends_on: P0-A, P0-B, P0-C`).
- canonical plan: `3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/plan.md:14,53-61`
  (P1 causal oracle and acceptance). Product worktree inspected:
  `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt` @
  `4f41f5bab562b99562f30c67540eb05344d13637`, branch `3060-12g-qwen35-4b`.

## 1. Bottom line

Every stage of the P1 chain has a **source-level telemetry producer** and a
**synthetic unit/contract test** in the current revision. No stage has a live,
identity-complete proof. The chain is therefore **unit-covered but live-unproven**.

The three P1 checks (`cached_tokens > 0`, full-prefix recompute = 0,
`hybrid_discard = 0`) each have a producer and unit coverage, but **none is
asserted anywhere as a chain-level, RID-correlated outcome**. The identity
requirement is the sharpest gap: only `rh_match_prepare` emits
`session_generation`; `rh_stage`, `ready_host`, and `admission.v2` emit RID and
attempt only. The six-field lifecycle tuple (`run_id`, `session_id`,
`session_generation`, `build_rid`, `node_id`, `final_kv_hash`) exists only inside
the marker-gated `p0_durable.v3` trace context and is never repeated on the
scheduler completion records. Per-event `source_build` does not exist; it is a
manifest-level hash. A fail-closed reducer must bridge `p0_durable.v3`,
`host_alloc.v1`, `rh_*`, and `restore_*` by exact RID/attempt/cache-instance/
generation-edge joins and reject time-adjacency joins
(`work/P0-B-LIVE-PLAN-20260911-R54.md:76-121`).

No existing vehicle both creates the physical HOST_ALLOC condition and reduces
the chain. This is the already-reviewed P0-B/R54 boundary; P1 inherits it.

## 2. Target identity (what P1 must pin)

| Dimension | Frozen/observed value | Source |
|---|---|---|
| Local HEAD | `4f41f5bab562b99562f30c67540eb05344d13637` | `plan.md:81`; verified locally this invocation |
| Product worktree | `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt` | `plan.md:8` |
| Served model | `/hy-tmp/models/Qwen3.5-4B-AWQ` (`Qwen3_5ForConditionalGeneration`, AWQ/compressed-tensors) | `work/P0-C-PROFILE-RECON-20260911-R59.md:31` |
| KV dtype / page | `fp8_e4m3`, `page_size=1`, `c128_page_size=16` | R59:32,40 |
| Device KV pool | `--max-total-tokens 65536`, `--mem-fraction-static 0.82` | R59:33,34 |
| Host KV pool | `131073` tokens / `2.15 GB`, `--hicache-ratio 2.0` (size 0) | R59:38,40 |
| IO/layout/write/storage | `kernel` / `page_first` / `write_through` / `file`, prefetch `wait_complete` | R59:44 |
| Physical/spec budgets | `65536` / `39321` (0.6 fraction) | R59:46,47 |
| RH enable / N | `--enable-ready-horizon` (toggle), `--ready-horizon-frontier-n 8` | R59:49,50; `server_args.py:2866-2904` |
| RH watermarks | token mode low/high `55000` / `110000` | R59:51 |
| Max running / chunked prefill | `1` / `2048` (max 16384) | R59:53,54 |
| RH default (source) | `False` (`enable_ready_horizon`, `server_args.py:2866-2880`) | `server_args.py:2866-2880` |

The profile is "observed, not ratified": R59/R60 record that no reviewed launch
script pins it and the run it came from (R32) never demonstrated a capacity
transition (`work/P0-C-PROFILE-RECON-20260911-R59.md:9-12`). P1 may not start on
an unfrozen profile (`plan.md:41`).

## 3. Coverage matrix — chain stage -> producer -> evidence

Legend: **U** = deterministic unit/contract test (synthetic); **L** = live/vehicle
evidence; **—** = none found. Line refs are to the inspected revision.

### 3.1 `SPEC_BUDGET park`

| Aspect | Evidence | Verdict |
|---|---|---|
| Producer | `_park_ready_decline` writes `self._ready_horizon_negatives[rid]` with `reason=DeclineReason.SPEC_BUDGET`, `epoch_cursor=epochs.spec_budget_release_epoch`, `release_epoch_cursor` (`scheduler.py:4936-4973`); enum (`scheduler_components/ready_horizon.py:110`) | present |
| Indirect telemetry | `ready_stage` `rh_stage.v2` `result=declined`/`reason` (`scheduler.py:4868-4896`); `rh_preadmission_decision` `negative_cache_blocked`/`negative_cursor` (`scheduler.py:4201-4217`) | present |
| Dedicated park event | none — park is in-memory state only | gap |
| Unit tests | `3090-dev/test_ready_horizon_unit.py:514` (cleared only by budget release), `:535` (unsampled ABA release clears), `:1078` (post-issue cursor + wake on release), `:1132` (wake after unsampled ABA release), `:1208` (physical-only limiter creates no spec park), `:1333` (off-mode noop), `:1339`/`:1359` (RH on/off enqueue) | U |
| Live | none | — |
| Gap | no telemetry line names the park; `ready_stage` line carries RID only (no session/node/build/generation) |  |

### 3.2 `reservation/release epoch transition`

| Aspect | Evidence | Verdict |
|---|---|---|
| Producer | `reserve_prefetch` (`mem_cache/unified_radix_cache.py:5106`); `release_prefetch` (`:5123`) increments `cc.speculative_release_epoch` (`:5144`) | present |
| Allocator epoch | `host_allocability_change` emitter (`unified_radix_cache.py:3741`, schema `host_alloc.v1` at `:161-190`); `cache_controller.py:376,675,856,1289` | present |
| Scheduler release counter | `_ready_host_release_epoch` init/advance (`scheduler.py:1502-1508,5028-5039`); `_ready_spec_budget_release_epoch` (`:1512,5031-5035`) | present |
| Unit tests | `test/registered/unit/managers/test_hicache_host_allocability.py:200` (schema/zero units/`ts_mono_ns`), `:218-235` (generation bumps only on completed/changed mutations); `test/registered/unit/mem_cache/test_mem_pool_host.py:282,299` (change callback); `3090-dev/test_prefetch_budget_split_unit.py:297` (roundtrip), `:307` (double-release idempotent), `:317` (release without reservation noop), `:323`, `:333` (revoke), `:343` (abort), `:351` (finalize), `:374` (hybrid discard), `:411` (detach); `test_ready_horizon_unit.py:761-853` (`CausalEpochEventTests`); `test_writeback_reserve_unit.py:87-279` | U |
| Live | R32 HAE rows had `rid=null, attempt_id=null, causal_rid=null, trace_context=null` (`work/P0-B-LIVE-PLAN-20260911-R54.md:56`); no epoch transition demonstrated | — |
| Gap | `host_allocability_change` may legitimately have null request identity (global release); join only by `cache_instance_id`+`pool`+contiguous generation edge (`R54:118`); mutation telemetry is bounded/sampled (`unified_radix_cache.py:149-158,3723-3735`) so an exact edge can be sampled away |  |

### 3.3 `RH wake`

| Aspect | Evidence | Verdict |
|---|---|---|
| Producer | `restore_host_alloc_wake_decision`, two emit sites (`scheduler.py:3755`, `:3800`); selector `_select_host_alloc_waiter` (`:3600`); predicate `_host_alloc_wait_eligible` (`:3481`); `HostAllocWakeArbiter` in `scheduler_components/hicache_restore.py` | present |
| Fields | `rid`, `attempt_id`, `cache_instance_id`, `trace_context`, captured/current generations, `generation_vector_id`, `decision`, `global_grant_used`, `budget_available`, free/evictable, `fifo_sequence` (`scheduler.py:3739-3836`) | present |
| Unit tests | `test/registered/unit/managers/test_hicache_host_allocability.py:70` (unlock-to-evict + actual-free opportunities), `:87` (no-change no-spin + FIFO rotate), `:119` (aux-blocked needs aux generation), `:132` (aux self-wake rejected), `:161` (full-span, trailing sidecar not croppable), `:184` (no lower-frontier crop path), `:192` (waiter departure removes FIFO entry), `:200` (telemetry schema); `3090-dev/test_hicache_restore_scheduler_feed.py:94,110,125,141,234`; `test_ready_horizon_unit.py:1234` (NO_HEADROOM wake on release epoch not level) | U |
| Live | none; R32 had no wait/wake chain (`R54:56`) | — |
| Gap | synthetic only; `trace_context` is marker-gated so the six-field join depends on `/tmp/t38c-durable-trace` being present (`trace_context.py:10,28-29`) |  |

### 3.4 `L3->L2 stage`

| Aspect | Evidence | Verdict |
|---|---|---|
| Producer | `restore_host_alloc_wait` (`scheduler.py:3568`, schema `host_alloc.v1`); `prefetch_issued` (`unified_radix_cache.py:5475`); `prefetch_io_done` (`:6731`); `ready_stage` `rh_stage.v2` (`scheduler.py:4868`); `rh_preadmission_decision` `rh_preadmission.v1` (`:4201`); `rh_match_prepare` `rh_match_prepare.v1` (`:4452`) | present |
| Stage issues via real path | `_ready_horizon_pass` (`scheduler.py:4641`) calls `_prefetch_kvcache` (`scheduler.py:4777`) | present |
| Unit tests | `test_ready_horizon_unit.py:974` (issues candidates via prefetch), `:998` (no event no refill), `:1055` (causal epoch change triggers refill), `:1078` (park), `:1405` (stage log reports issue result), `:1420` (issue decision precedes stage with claimed attempt), `:1433` (failed issue is hold); `test_hicache_restore.py:63-420` (T1-T15 transitions); `test_hicache_restore_scheduler_feed.py:54,178,218,234`; `test_rh_contract_dependency_free.py:674,720` (join fields/order) | U |
| Live | none | — |
| Gap | only `rh_match_prepare` emits `session_generation` (`scheduler.py:4458`); `ready_stage`/`prefetch_issued` carry RID only |  |

### 3.5 `Host-ready`

| Aspect | Evidence | Verdict |
|---|---|---|
| Producer | `ready_host` `rh_ready_host.v1` (`scheduler.py:3975-3993`); `restore_ready` (`:4047`); finalizer material fields `_host_alloc_hybrid_completion` (`unified_radix_cache.py:5810-5827`); `restore_hybrid_finalize` (`:5615,5649`) | present |
| Fields | `rid`, `attempt_id`, `issue_origin`, `completed_kv_tokens`, `required_aux_pools`, `completed_aux_units`, `restore_state_before/after`, `finalize_result`, `ready_monotonic_ns` | present |
| Ordering contract | finalization precedes READY; discarded finalization cannot emit `ready_host` | enforced |
| Unit tests | `test_rh_contract_dependency_free.py:674` (required fields), `:720` (attempt/event order), `:867` (aux fields from finalizer), `:930` (discarded finalization cannot be ready_host), `:992,1002`; `test_storage_regression.py:2538` (accepted→READY), `:2556` (hybrid discard marks nothing, result discarded); `test_ready_horizon_unit.py:284,295,301,307` (M6 resident marker) | U |
| Live | R32-style logs not shown to carry the six-field identity; `ready_host` does not repeat it (`R54:117`) | — |

### 3.6 `admission`

| Aspect | Evidence | Verdict |
|---|---|---|
| Producer | `admission.v2` `rh_admission.v2` (`scheduler.py:6313-6333`); legacy `evt=admission` gated by `/tmp/t38c-on` (`:6229`, gate at `:390-397`) | present |
| Fields | `rid`, `rh_decision_id`, `hicache_prefetch_attempt_id`, `hicache_prefetch_origin`, `ready_host_observed`, `admission_monotonic_ns`, `can_run` | present |
| Wait/hold before admission | `WAIT_CAPACITY` skip (`scheduler.py:6270-6276`); `restore_success` on `loaded_tokens>0` (`scheduler.py:6282`) | present |
| Unit tests | `test_rh_contract_dependency_free.py:674,720`; `test_hicache_restore.py:228` (T6 admission deny), `:237` (T7 loadback fail); `test_hicache_restore_scheduler_feed.py:178` (quota-deny semantics); `test_drain_reentry.py:1045,1052,1106,1113,1122,1128` | U |
| Live | none | — |
| Gap | no `session`/`node`/`build`/`generation` on `admission.v2`; only the `ready_host_observed` boolean links it to Host-ready |  |

### 3.7 `L2->L1 restore`

| Aspect | Evidence | Verdict |
|---|---|---|
| Producer | `restore_host_alloc_retry_result` (`unified_radix_cache.py:5398`, `:6500`); `restore_hybrid_finalize` (`:5615,5649`); `restore_success` (`scheduler.py:6282`); `restore_loadback_fail` (`:6395`); `restore_backup` (`unified_radix_cache.py:1488`); `restore_disposition` (`:1444`) | present |
| Per-pool result | first/second alloc, reclaimed, free/evictable before/after, required aux, failed domains, `crop_attempted=False`, `lower_checkpoint_queried=False`, `terminal`, `reservation_released` (`:6499-6521`) | present |
| Unit tests | `test_hicache_restore.py:228,237,250` (T6/T7/T8), `:431` (full retry cycle); `test_storage_regression.py:1888,1910,1923` (load_back denied/success); `test_hicache_host_allocability.py:161,184` (full-span/no crop); `test_prefetch_budget_split_unit.py:374` | U |
| Live | none | — |
| Gap | the aux-alloc-failure emit (`:5398`) passes `trace_context=None`; only the revoke emit (`:6500`) carries `operation.trace_context`, so one retry path cannot carry lifecycle identity |  |

### 3.8 `generation`

| Aspect | Evidence | Verdict |
|---|---|---|
| Product generation | `req.session_generation` set at `scheduler.py:2799,2843`; emitted only in `rh_match_prepare` (`:4458`); `_host_alloc_generation_vector_id` (`:3545-3549`); `_host_allocability_generations` (`unified_radix_cache.py:218-235`) | present |
| Lifecycle identity | `trace_context.make_trace_context`/`complete_trace_context` (`mem_cache/trace_context.py:44-91`) carries `session_id`, `session_generation`, `build_rid`, `warm_rid`; `_t38c_residency_identity` additionally requires `run_id`, `node_id`, `final_kv_hash`, schema `p0_durable.v3` (`unified_radix_cache.py:196-220`) | present |
| Unit tests | `test_p0_residency_barrier_emitter.py` (run-a != run-b; invalid-context cases; asserts at `:1296-1339`); `test_p0_trace_context_v4.py` (invalid join/identity; asserts at `:2037-2040`); `test_hicache_restore_scheduler_feed.py:288,317,339,365,391,410` (P1 sticky miss generation), `:461-487` (re-arm gate); `test_ready_horizon_unit.py:550` (generation change clears park); `test_rh_contract_dependency_free.py:370,429` (null generation handled); `test/registered/unit/mem_cache/test_session_unified_radix_cache.py` | U |
| Live | R32 showed `session_generation=null` on RH records (`R54:56`); no chain | — |
| Gap | per-event `source_build` does not exist as a field — the plan's `source_build` identity is satisfied only at manifest level (source/runtime/build hash), not on each chain event (`grep`: only `sglang.version.__version__` in `rust_server.py:815`) |  |

### 3.9 Check `cached_tokens > 0`

| Aspect | Evidence | Verdict |
|---|---|---|
| Client-visible producer | `meta_info["cached_tokens"]` (`entrypoints/openai/protocol.py:1849,1897,1904`; `entrypoints/openai/serving_chat.py:709,1595`); `entrypoints/context.py:97`) | present |
| Internal proxy | `restore_success n_tokens` (`scheduler.py:6282`); `storage_hit_length` / `pop_prefetch_loaded_tokens`; `host_hit_length` | present |
| Unit tests | `3090-dev/gate3_parked*.py` report cached/recompute fractions; many `test/registered/*` assert the client field | U (not chain-correlated) |
| Gap | no test asserts B's `cached_tokens > 0` correlated to the same `RID/attempt/session_generation` as the chain |  |

### 3.10 Check full-prefix recompute = 0

| Aspect | Evidence | Verdict |
|---|---|---|
| Producer | `restore_recompute` + `_final_storage_survivability` (`scheduler.py:4054-4074`); `restore_disposition` reason `RECOMPUTE`/`hybrid_discard` (`unified_radix_cache.py:1444,5648`); `restore_loadback_fail` (`scheduler.py:6395`) | present |
| Unit tests | `test_hicache_restore.py:444,453,461,477,486,505` (genuine-miss chain, sticky miss); `test_storage_regression.py:1829,1835` (drop to miss when not persisted); `test_drain_reentry.py:1113` (flag-off miss classification) | U |
| Live | none | — |
| Gap | no live/chain-level assertion that a positive-hit B performed **zero** full-prefix recompute |  |

### 3.11 Check `hybrid_discard = 0`

| Aspect | Evidence | Verdict |
|---|---|---|
| Producer | `release_prefetch(req_id, "hybrid_discard")` (`unified_radix_cache.py:5927`); `restore_disposition reason=hybrid_discard` (`:5648`); `restore_hybrid_finalize result=discarded` (`:5615-5642`) | present |
| Unit tests | `test_prefetch_budget_split_unit.py:374` (hybrid-discard path releases speculative reservation); `test_storage_regression.py:2556` (`test_hybrid_discard_marks_nothing`, result discarded/NONE) | U |
| Live | none | — |
| Gap | unit-only; no live chain assertion that zero all-or-nothing discards occurred on B |  |

## 4. Identity coverage (what each chain event actually carries)

| Event / record | rid | attempt_id | session/node/build/generation | cache_instance_id | trace_context |
|---|---|---|---|---|---|
| `restore_host_alloc_wait` (`scheduler.py:3568`) | yes | prior attempt | no | yes | yes (gated) |
| `host_allocability_change` (`unified_radix_cache.py:3741`) | optional (`causal_rid`) | no | no | yes | yes (gated) |
| `restore_host_alloc_wake_decision` (`scheduler.py:3755,3800`) | yes | yes | no | yes | yes (gated) |
| `restore_host_alloc_retry_result` (`:5398,6500`) | yes | yes | no | yes | only at `:6500` |
| `restore_hybrid_finalize` (`:5615,5649`) | yes | yes | no | yes | yes (from operation) |
| `ready_host` (`scheduler.py:3975`) | yes | yes | no | no | no |
| `restore_ready` (`scheduler.py:4047`) | yes | no | no | no | no |
| `admission.v2` (`scheduler.py:6313`) | yes | yes | no | no | no |
| `rh_stage.v2` (`scheduler.py:4868`) | yes | yes | no | no | no |
| `rh_preadmission.v1` (`scheduler.py:4201`) | yes | yes | no | no | no |
| `rh_match_prepare.v1` (`scheduler.py:4452`) | yes | yes | **session_generation only** (`:4458`) | no | no |
| `p0_durable.v3` trace context (`trace_context.py:59-81`) | warm/build rid | no | **yes** | no | n/a (is the context) |

Required six-field P1 identity (`R38:73-79`; `plan.md:61`):
`run_id`, `session_id`, `session_generation`, `build_rid`, `node_id`,
`final_kv_hash`. `warm_rid`, `attempt_id`, `cache_instance_id`, worker/rank are
additionally required for the HOST_ALLOC correlation (`R54:82-91`).

**Key observed fact:** no single chain record carries the full tuple. The join is
only constructible by bridging `p0_durable.v3` (lifecycle identity) with
`host_alloc.v1`/`rh_*`/`restore_*` (mechanics) through exact RID/attempt,
`cache_instance_id`, and generation-edge joins (`R54:114-121`).

## 5. Gaps requiring new tests or a temporary harness

1. **No live identity-complete chain (primary gap).** All chain stages are
   unit/synthetic only; R32 is the only live log and had null request identity
   and null `session_generation` (`R54:56`). Requires the R54-authorized
   two-part external harness (driver + reducer) under a fresh Task ID, not new
   product instrumentation (`R54:13-20,212-214`).
2. **No chain-level check oracle.** `cached_tokens>0`, `recompute==0`, and
   `hybrid_discard==0` are not asserted against the same identity as the chain.
   A reducer could add these as negative/positive predicates over existing logs
   without new product fields.
3. **`rh_stage`/`ready_host`/`admission.v2` omit lifecycle identity.** The
   reducer must inherit identity from the same-RID/attempt `p0_durable.v3` /
   HAE records, failing closed when absent (`R54:117`).
4. **`source_build` is manifest-level only.** Per the plan's identity wording,
   `source_build` must be pinned in the run manifest (source/runtime/build hash)
   and joined by `run_id`; it cannot be expected on each event.
5. **HAE mutation sampling.** Bounded/sampled mutation telemetry
   (`unified_radix_cache.py:149-158,3723-3735`) can drop the exact blocked-pool
   generation edge; the reducer must reject a jump whose intervening raw row is
   missing (`R54:65,118`). Changing sampling would be instrumentation.
6. **`restore_host_alloc_retry_result` identity seam.** The aux-alloc-failure
   emit passes `trace_context=None` (`unified_radix_cache.py:5398`); a run that
   exits via that path cannot carry lifecycle identity. The reducer must treat
   it as missing, not backfill.
7. **Existing vehicles cannot drive or reduce the chain.**
   `p0_session_barrier_vehicle.py` identity is
   `(session_id, build_rid, node_id, final_kv_hash)` + `run_id`, its scoped event
   set excludes `host_alloc.v1`, and it has no HOST_ALLOC cursor/FIFO/retry
   reducer (`R54:36`; `p0_session_barrier_vehicle.py:32-81,96-101,144-159,219-240,364-396`).
   `rh_durability_driver.py` is dry-run/synthetic and explicitly refuses live
   mode (`rh_durability_driver.py:131-134`). `cap_ratio_driver.py` (secondary
   worktree) supplies load mechanics only (`R34:104-106`).
8. **Marker-gated trace context.** `p0_durable.v3` context is emitted only while
   `/tmp/t38c-durable-trace` exists (`trace_context.py:10,28-29`); P1 must run
   with the marker present and verify non-null context on the B chain.

No new *product/test/gate* changes are required by the evidence above; the
remaining work is the reviewed temporary harness plus a fresh live run.

## 6. Minimal fresh-blocker A/B experiment design (OFF vs ON)

This mirrors `plan.md:53-61` and the R54 authorization packet
(`R54:123-153`). Design only; not authorized or executed here.

### 6.1 Independent variable and paired controls

- **One toggle only:** `--enable-ready-horizon` OFF vs ON
  (`server_args.py:2866-2880`). Two runs use the **same** product revision
  (`4f41f5b`), launch argv from Section 2, model, storage namespace family,
  seed, request order, blocker shape, and timeout.
- Every other RH arg (`frontier-n 8`, watermarks `55000/110000`, spec fraction
  `0.6`, physical/spec budgets `65536/39321`) is fixed by the frozen profile.
- OFF run: RH is a noop and must be treated as the baseline, not a failure.
  ON run: RH stages/park/wakes.

### 6.2 Fixture (two durable sessions + one blocker)

1. Build two independent 55K-class session histories A (holder) and B (target)
   with complete `p0_durable.v3` identity and a positive full KV+Mamba durable
   artifact (KV `kv_durable`/`storage_persisted`, Mamba `mamba_durable`/
   `mamba_persisted`; `p0_session_barrier_vehicle.py:56-62`).
2. Use bounded, predeclared ordinary requests/holder A to consume host capacity
   until B's restore is not allocable and parks (`WAIT_CAPACITY/HOST_ALLOC`).
   This is the "fresh blocker".
3. Release exactly one predeclared holder through a documented
   client/lifecycle action; the driver never selects/wakes/retries/declares READY.
4. Observe the product-owned chain B:
   `SPEC_BUDGET park -> reservation/release epoch transition -> RH wake ->
   L3->L2 stage -> Host-ready -> admission -> L2->L1 restore -> generation`.
5. Repeat the identical sequence in the OFF run for the paired baseline.

### 6.3 Two-file temporary harness (subject to fresh authorization)

- **Driver** (public HTTP only): submits bounded build/warm/pressure/release
  requests; controls only the named experimental server lifecycle; no product
  imports/monkeypatches/internal scheduler or allocator calls/synthetic events.
- **Reducer** (offline, fail-closed): consumes immutable raw
  `p0_durable.v3`, `host_alloc.v1`, `rh_*`, `restore_*`, `ready_host` logs;
  performs exact RID/attempt + `cache_instance_id` + generation-edge joins with
  raw line references; emits only `VERIFIED`/`NOT_VERIFIED`.
- Review + SHA256 pin before transfer; delete remote copies after capture.

### 6.4 Required identity fields per B chain

Lifecycle: `run_id`, `session_id`, `session_generation`, `build_rid`,
`node_id`, `final_kv_hash`, `warm_rid` (where distinct), request `rid`.
Mechanics: `attempt_id` (single, preserved through retry result/finalization/
READY), `cache_instance_id`, worker/rank; waiter captured per-pool generations,
free/evictable units, `fifo_sequence`; mutation pool + generation before/after +
cause + returned units + monotonic seq; wake current generation/vector id +
FIFO grant; per-pool alloc/reclaim/alloc result with `crop_attempted=false`,
`lower_checkpoint_queried=false`, `genuine_miss=false`; `all_or_nothing=true`
and accepted finalization; `ready_host` strictly before `admission.v2`.
Manifest: frozen server args + source/runtime/build hash (the plan's
`source_build`) joined by `run_id`.

### 6.5 Stop conditions (fail closed)

- Any identity conflict or missing field on the target RID/attempt.
- Missing exact blocked-domain generation edge (sampled-away mutation).
- `cached_tokens = 0` for B; any full-prefix/full-history recompute; any
  `hybrid_discard` / discarded all-or-nothing finalization.
- Self-wake (same generation), duplicate/multiple retries, skipped eligible
  FIFO predecessor, READY before finalization, partial KV or Mamba restore.
- Parameter/hash drift, unstable intended-A/B→RID label, missing durability
  ACK, actor conflict, timeout, memory/disk bound, unexpected process state.
- OFF/ON runs differing in any control, or the profile not frozen.
Any of these yields `NOT_VERIFIED`, never PASS.

## 7. Evidence / artifacts

- Product source (inspected; unmodified): `python/sglang/srt/managers/scheduler.py`,
  `.../scheduler_components/ready_horizon.py`, `.../scheduler_components/hicache_restore.py`,
  `.../mem_cache/unified_radix_cache.py`, `.../mem_cache/trace_context.py`,
  `.../managers/cache_controller.py`, `.../server_args.py`.
- Product tests (existing): `3090-dev/test_ready_horizon_unit.py`,
  `3090-dev/test_prefetch_budget_split_unit.py`, `3090-dev/test_hicache_restore.py`,
  `3090-dev/test_hicache_restore_scheduler_feed.py`, `3090-dev/test_rh_contract_dependency_free.py`,
  `3090-dev/test_storage_regression.py`, `3090-dev/test_drain_reentry.py`,
  `3090-dev/test_writeback_reserve_unit.py`, `3090-dev/test_p0_trace_context_v4.py`,
  `3090-dev/test_p0_residency_barrier_emitter.py`,
  `test/registered/unit/managers/test_hicache_host_allocability.py`,
  `test/registered/unit/mem_cache/test_mem_pool_host.py`.
- Memory contracts: `work/P0-B-HARNESS-BOUNDARY-20260911-R38.md:73-79,159-169`,
  `work/P0-B-HARNESS-SCOUT-20260911-R34.md:42-106,116-129`,
  `work/P0-B-LIVE-PLAN-20260911-R54.md:13-20,34-121,123-169`,
  `work/P0-C-PROFILE-RECON-20260911-R59.md`, `work/P0-C-PROFILE-FREEZE-20260911-R60.md`,
  canonical `plan.md:13-14,53-61`.

## 8. Followups

1. After P0-B/P0-C close and fresh authorization: dispatch the two-file harness
   implementation, then independent review, then one fresh 3060 execution.
2. Build the coverage matrix into the reducer as explicit predicates so each
   stage/check emits `present|absent` with raw line refs.
3. Before execution, confirm the `p0_durable.v3` marker
   (`/tmp/t38c-durable-trace`) and verify non-null trace context on the B RID.
4. Capture and freeze the OFF/ON manifest (args + source/runtime/build hash)
   into the P1 durability manifest.

## 9. Open issues

- Memory-root ambiguity: the canonical `plan.md`/`ledger.md`/`context.md` live in
  `3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/`, while the
  latest P0-C reports (R59/R60) and this report are under
  `workspaces/.memory/phase2-hicache-design/work/`. R60's open issue already
  recorded a missing-input symptom. The orchestrator should reconcile the active
  memory root; this report was written to the dispatch-specified relative path.
- `source_build` per-event identity does not exist; interpretation as a
  manifest-level hash joined by `run_id` is inferred from plan language, not an
  explicit design statement.
- Mutation telemetry sampling and marker-gated trace context are unresolved
  live-run risks (R54 uncertainties).
- This report does not verify P0-B/P0-C closure and does not authorize any
  harness, instrumentation, or remote run.

## 10. Search limits

- Read-only local inspection of the two SGLang worktrees and phase2 memory only;
  no execution of any test, driver, engine, or remote host.
- Test coverage statements are derived from source inspection of test files, not
  from running them; pass counts are not asserted here.
- Some test files (`test_p0_trace_context_v4.py`,
  `test_p0_residency_barrier_emitter.py`) are assert-script style without
  `unittest` `def test` names; cited by file and assert lines.
- Upstream/3rdparty files outside the inspected worktrees and the two repository
  trees were not searched.
