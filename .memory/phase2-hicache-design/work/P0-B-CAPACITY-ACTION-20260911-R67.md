# P0-B capacity-action scout — R67

- ENTRY: `ACCEPT`
- Task ID: `P0-B-CAPACITY-ACTION-20260911-R67`
- Invocation identity: `ses-p0b-capacity-action-r67-20260911`
- Role: `scout`
- Epoch: `2026-09-11`
- Status: **done**
- Claim boundary: read-only determination only. This report does not design, implement, diagnose,
  or modify anything, does not execute a test or an experiment, and does not touch any remote host.
  It does not accept P0-B and does not bypass the P0-B hard gate.

## Dispatch validation and scope

The dispatch is valid: role `scout`, read-only, no remote access, no experiments, no edits, and an
explicit artifact path. `ENTRY: ACCEPT`.

- Report path resolved to `/home/dev-codex/workspaces/.memory/phase2-hicache-design/work/P0-B-CAPACITY-ACTION-20260911-R67.md`
  (cwd `/home/dev-codex/workspaces`; the R54/R59/R60/R64 lineage is materialized in this live
  `.memory` root. A byte-identical mirror is placed in the product worktree's canonical
  `.memory/phase2-hicache-design/work/` per the R59/R64 two-root convention).
- No subagents were spawned and no IDs were created.

### Search limits

Read-only inspection of:

- Live coordination memory `/home/dev-codex/workspaces/.memory/phase2-hicache-design/` (R34, R38,
  R45, R53, R54, R59, R60, R64, R65) and the coordination/product `.memory` mirrors.
- Product worktree `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt`
  (branch `3060-12g-qwen35-4b`, HEAD `4f41f5bab562b99562f30c67540eb05344d13637`).
- Targeted source under `python/sglang/srt/` only: `managers/scheduler.py`,
  `managers/scheduler_components/ready_horizon.py`,
  `managers/scheduler_components/session_ref_tracker.py` equivalents,
  `mem_cache/unified_radix_cache.py`, `mem_cache/unified_cache/unified_tree_core.py`,
  `mem_cache/unified_cache/components/full_component.py`, `entrypoints/http_server.py`,
  `server_args.py`.
- Existing vehicles/tests named by the dispatch: `3090-dev/p0_session_barrier_vehicle.py`,
  `3090-dev/gate3_capacity.py`, `3090-dev/p2io_e28_hybrid_live.py`,
  `3090-dev/test_drain_reentry.py`, `3090-dev/test_hicache_restore_scheduler_feed.py`,
  `test/registered/unit/managers/test_hicache_host_allocability.py`.

Not inspected: the remote 3060 host, the 3090 fleet, production, unrelated repositories, private
memory outside `.memory/phase2-hicache-design`. No file was modified except this report (and its
mirror). No test, import, compile, remote command, or experiment was run.

## 1. Bottom line

- **Create-side:** no *existing* public-interface action deterministically produces the first
  positive-full-KV-hit host-allocation failure (`revoked_alloc_failed`) under genuine
  non-allocability on the **frozen RH-ON 3060 profile**. The straightforward route (a normal warm
  request's Ready-Horizon speculative L3→host prefetch) is structurally guarded by the RH headroom
  gate (`ready_horizon.py:481-489,530-549`; `scheduler.py:5049-5062`), which charges the candidate's
  prefix length against host free before issuing. When it passes, the alloc succeeds; when it fails,
  the request parks as an RH `NO_HEADROOM` decline, **not** `HOST_ALLOC`. The only code-consistent
  route to a first `HOST_ALLOC` park on this profile is a **DEMAND** re-issue (T11/T12 wake) after a
  prior wait reason, which is not demonstrated by any existing vehicle and is not a single public
  action.
- **Release-side:** a discrete, deterministic public action does exist: `POST /abort_request` on a
  predeclared holder RID that owns in-flight host staging. It reaches
  `release_aborted_request` (`unified_radix_cache.py:6167`), which queues a host release
  (`append_host_mem_release`, `:6208`); the drain frees pages and emits a `host_alloc.v1`
  `host_allocability_change` with cause `queued_release_drain` (or `direct_free`) and
  `returned_units > 0` (`:7166-7204`), advancing the blocked pool generation so the parked waiter
  becomes eligible (`scheduler.py:3481-3492,3600-3629`). The retry is then re-issued as a DEMAND
  restore (`scheduler.py:3867-3871`, `unified_radix_cache.py:5520`) and is allowed to run the
  authoritative `alloc -> evict_host -> alloc` path (`:6607-6633`).
- Therefore the R54 open item is **partially** resolved: the release action is identifiable from
  code; the deterministic *create* action is **not** established by read-only analysis and remains
  the binding unknown.

## 2. Observed mechanism map (all paths in `sglang-3090-24g-opt` at HEAD `4f41f5ba`)

### 2.1 Where the positive hit is formed

- A request that is not resident but whose prefix is durable in L3 gets a storage prefetch via
  `Scheduler._prefetch_kvcache` (`scheduler.py:3121`) → `prefetch_from_storage`
  (`unified_radix_cache.py:5240`). The storage query returns `operation.storage_hit_count`.
- `prefetch_threshold = 256` (`unified_radix_cache.py:1643`); a hit below it is revoked as
  `insufficient`/`miss`, not a positive full hit (`:6348-6349`).
- On the frozen profile (`--enable-ready-horizon`, R59 §4), eager enqueue prefetch is **disabled**
  (`scheduler.py:5570-5574`), so prefetches are issued by the RH refill planner
  (`scheduler.py:4692-4697`, issue at `:4777`) with `demand_restore=False` →
  `PrefetchKind.SPECULATIVE` (`unified_radix_cache.py:5520`).

### 2.2 Where an allocation failure becomes `WAIT_CAPACITY/HOST_ALLOC`

- Two distinct failure sites:
  1. **Issue-time auxiliary staging failure** (`prepare_prefetch` for Mamba/SWA):
     `forfeited_alloc_failed` (`unified_radix_cache.py:5338-5457`). It records
     `positive_hit_tokens=0` (`:5441`) and `sidecar_hit_pages={}`, so it does **not** satisfy the
     positive-full-hit requirement. Rejected candidate.
  2. **Hit-alloc KV staging failure**: `_try_alloc_storage_hit` (`:6579`) calls
     `cc.mem_pool_host.alloc(alloc_len)` = `alloc1` (`:6607`); if `None`, it calls
     `self.evict_host(alloc_len)` and retries `alloc2` only for DEMAND reservations (`:6617-6621`);
     if still `None`, it revokes with `alloc_failed=True` (`:6629-6633`). `revoke_pending_prefetch`
     classifies `alloc_failed` (`:6350-6351`) and emits `restore_host_alloc_retry_result` with
     `positive_hit_tokens=operation.storage_hit_count` (`:6499-6532`), then
     `record_host_alloc_failure` (`:6522`).
- The scheduler consumes that terminal in `_feed_restore_terminal` → `RestoreEvent.DENIED_ALLOC` →
  `_capture_host_alloc_wait` (`scheduler.py:3946-3963,3517-3593`), logging
  `restore_host_alloc_wait` (`state=WAIT_CAPACITY`, `reason=HOST_ALLOC`) with the captured per-pool
  generation cursor, free/evictable units, blocked domains, and FIFO sequence.

### 2.3 Wake eligibility is generation-based, not free/evictable-based

- `_host_alloc_wait_eligible` (`scheduler.py:3481-3492`) requires cache-instance equality and a
  **strictly greater generation for every blocked domain**. `free_units`/`evictable_units` are not
  independent predicates.
- `_select_host_alloc_waiter` (`scheduler.py:3600-3629`) additionally requires a non-rate-limited
  controller and an unexpired waiter (`hicache_restore_wait_timeout_s`, frozen `60.0`).
- `_restore_wait_capacity_fits` for HOST_ALLOC always returns True once the controller exists and
  `full_untruncated_fill_ids` is set (`scheduler.py:5206-5215`), by design, so the retry may run
  `alloc -> evict_host -> alloc`.

### 2.4 What bumps a host-pool generation (release observability)

`host_alloc.v1` `host_allocability_change` is emitted by `_bump_host_allocability`
(`unified_radix_cache.py:3663-3758`). Verified call sites and causes:

| cause | trigger | site |
|---|---|---|
| `direct_free` | host pages freed (drain, failed-transfer cleanup, restore finalize, retraction discard) | `:3860,3879,4049,4129,5737` |
| `queued_release_drain` | queued host-mem releases drained (KV / aux) | `:7181-7185,7230-7234` |
| `lock_release_evictable` | `dec_host_lock_ref` / `dec_swa_lock_only` changed the evictable signature | `:3273,3287` |

Generation bumps only when `returned_units > 0` or the evictable signature actually changed
(`:3686-3688,3765-3773`).

### 2.5 What makes host occupancy non-evictable

- `_is_host_leaf` requires `node.evicted`, `node.backuped`, no children, and all
  `host_lock_ref == 0` (`unified_tree_core.py:1950-1964`). `drive_host_eviction` only frees
  `evictable_host_leaves` (`full_component.py:230-257`).
- Non-evictable host occupancy therefore comes from (a) device-resident "duplicate" nodes (not
  `evicted`), (b) `host_lock_ref > 0` nodes (in-flight prefetch anchors, L3 write-through ACK
  backlog; see the F1 drain-then-retry at `unified_radix_cache.py:4195-4211`), and (c) staged
  prefetch buffers that are not yet tree host values.
- `host_allocability_snapshot` reports `free_units` from `host_group.available_size(pool)` and
  `evictable_units` from `_host_evictable_signature` (`unified_radix_cache.py:3775-3819`).

### 2.6 The RH headroom gate (decisive for create-side determinism)

- `_ready_host_headroom` = host free + READY-resident tokens (`scheduler.py:5049-5062`).
- `refill_plan` issues only if
  `headroom_fits(ready_tokens, inflight_speculative_tokens, host_headroom - reserve_floor)`
  (`ready_horizon.py:481-489,530-534`), where the per-candidate charge is
  `max(prefix_len, staged_tokens)` (`:227-234`). Failed candidates are attributed `NO_HEADROOM`
  (`:549`), a Ready-Horizon park — **not** `HOST_ALLOC`.
- Because the charge covers the full requested prefix and the alloc is the un-matched suffix
  (`<= prefix_len`), an RH-issued speculative prefetch should not oversubscribe host free.

### 2.7 Public control surface relevant to this task

| action | entrypoint | effect relevant here |
|---|---|---|
| `/generate` | `http_server.py:899` | ordinary request; can build/persist and trigger restores |
| `/v1/chat/completions` | `http_server.py:1726` | same, chat payload; supports `session_id` field |
| `POST /abort_request` (`rid`, `abort_all`) | `http_server.py:1610` | explicit request cancellation; releases prefetch/staging and queues host frees |
| `/flush_cache` | `http_server.py:971` → `scheduler.py:7383` | requires `is_fully_idle()`; `is_fully_idle` requires `waiting_queue == 0` (`scheduler.py:7210-7227`) |
| `/clear_hicache_storage_backend`, `POST /hicache/storage-backend/clear` | `http_server.py:1047,1063` | clears L3 storage only; does not free host; would destroy the retry's L3 hit |
| `/release_memory_occupation` | `http_server.py:1485` | elastic weight/memory occupation release; not a per-pool host release |
| `/open_session`, `/close_session` | `http_server.py:1576,1590` | session ref pin/release only when `enable_session_radix_cache` is on; default False (`server_args.py:1471-1474`), absent from the frozen argv (R59 §4) → no-op for tree refs on this profile |

## 3. Candidate create actions (ranked)

| rank | action | entrypoint | preconditions | determinism | side effects | host_alloc.v1 observability | public-driver usable |
|---|---|---|---|---|---|---|---|
| **C1** | **DEMAND re-issue after a prior wait reason**: park the target in a prior wait (`FRONTIER`/`BACKUP_PENDING`/`PREFETCH_BUDGET`), arrange host free+evictable < full span, then let the T11/T12 wake re-issue the prefetch as DEMAND; `alloc1` fails, `evict_host` cannot cover, `alloc2` fails → `revoked_alloc_failed` with positive hit | normal request + natural wait-state; wake code `scheduler.py:3867-3871`; alloc `unified_radix_cache.py:6579-6633` | full L3-durable span; host saturated with non-evictable occupancy; prior park actually reachable; storage query returns full hit on re-issue | **unproven**; no existing vehicle/test demonstrates it; requires a reachable prior wait and precise host saturation | normal request lifecycle only | `restore_host_alloc_retry_result`(positive hit) → `restore_host_alloc_wait`(`WAIT_CAPACITY/HOST_ALLOC`) | yes in principle; not demonstrated |
| **C2** | RH speculative prefetch on a resumed (post-restart) long L3-durable prefix | `/generate`/`/v1/chat/completions`; issue `scheduler.py:4777` | L3 durable prefix; device+host residency cleared (e.g. bounded server restart, as in OPS3060-HICACHE-RESTORE-R3); RH on | **no failure**: headroom gate (`ready_horizon.py:481-489,530-534`) charges `prefix_len` against free; alloc succeeds | normal request | `prefetch_issued`; **no** `host_allocability_change` / park | yes, but produces the positive hit **without** non-allocability |
| **C3** | Saturate host so RH declines | normal requests + post-restart target | host free < requested prefix | **wrong park**: `rh_preadmission_decision decision=decline reason=NO_HEADROOM` / Ready-Horizon park, not `HOST_ALLOC` | normal requests | `rh_preadmission_decision`; no HOST_ALLOC | yes, but wrong event |
| **C4** | Auxiliary (Mamba/SWA) staging failure at issue | normal request | host Mamba/SWA pool exhausted | deterministic failure, but | normal request | `restore_host_alloc_retry_result` with `positive_hit_tokens=0`, `forfeited_alloc_failed` | yes but **fails the positive-hit requirement** (`unified_radix_cache.py:5441`) |
| **C5** | Pure host-bytes saturation by request count | normal requests | fill device-duplicate + staging occupancy | **not established**: a single span is `<= max_req_input_len=65530` (R64 §3) while `free + evictable >= host_capacity(131073) - device_pool(65536) = 65537` absent staging/locks; steady-state failure is not implied | normal requests | only releases/unlocks, no guaranteed park | not usable as sole mechanism |

**Rejected create alternatives:** direct allocator/scheduler calls, product imports/monkeypatch,
synthetic `host_alloc.v1` rows, timestamp-only joins, and profile changes (e.g. turning RH off or
enabling session radix cache) — all violate R38/R31 boundaries or exceed the frozen profile.

## 4. Candidate release/wake actions (ranked)

| rank | action | entrypoint | precondition | determinism | side effects | emitted event(s) | public-driver usable |
|---|---|---|---|---|---|---|---|
| **R1 (recommended)** | `POST /abort_request` with the predeclared holder's `rid` while that holder owns in-flight staged prefetch host slots | `http_server.py:1610` → `scheduler.py:7631-7651` → `unified_radix_cache.py:6167-6215` | holder's prefetch is in `ongoing_prefetch` with `host_indices`; target rid must not start with the holder prefix (matching is `rid.startswith`, `:7632`) | discrete and deterministic once the holder state exists; releases `host_indices[:completed_tokens]` into `host_mem_release_queue` then drains | cancels the holder only; target keeps its parked state | `host_allocability_change` cause `queued_release_drain` (KV via `:7181`; aux via `:7230`) or `direct_free` (`:3860`), then `restore_host_alloc_wake_decision decision=grant`, `restore_retry cause=capacity` | yes — existing generic HTTP client + log tail |
| **R2** | Let one predeclared holder finish naturally | normal request completion | holder has bounded `max_tokens`; its ACK/writeback drains | real but timing-driven (async ACK drain), not a discrete command | holder completes; frees/unlocks its host footprint | `lock_release_evictable` (`:3287`), `direct_free`/`queued_release_drain` | yes |
| **R3** | ACK-backlog drain via `_execute_kv_backup` F1 | internal only (`:4195-4211`) | in-flight finished L3 writes hold host locks | internal, time-driven | none externally visible | `lock_release_evictable` | **no** public trigger |
| **R4** | `/flush_cache` | `http_server.py:971` → `scheduler.py:7383` | `is_fully_idle()` requires `waiting_queue == 0` (`:7210-7227`) | **fails while target parked** | none if rejected | none | not usable during park |
| **R5** | `/clear_hicache_storage_backend` | `http_server.py:1047,1063` | L3 backend present | frees L3, not host | destroys the retry's L3 hit | none host-side | not usable |
| **R6** | `/release_memory_occupation` | `http_server.py:1485` | engine memory-occupation contract | whole-engine release, not per-pool | disrupts the engine | none target-relevant | not usable |
| **R7** | `/open_session` + `/close_session` | `http_server.py:1576,1590` → `scheduler.py:8041-8054` | `enable_session_radix_cache=True` | **no-op on frozen profile** (default False, `server_args.py:1471-1474`; absent from R59 §4 argv) | none | none | not usable |

## 5. Recommended bounded scenario (single target lifecycle)

Because the create-side is not established, the recommendation is a **two-gate bounded attempt**: first
*prove the positive hit and the park*, then *prove the release wake and retry*. If gate 1 does not
produce a real `HOST_ALLOC` park within the bound, stop `NOT_VERIFIED`; do not push the release leg.
This is a scenario recommendation only and is not authorized by this read-only report.

**Profile inputs (frozen, R60/R64):** `max_req_input_len=65530`, device KV `65536` fp8_e4m3,
host KV `131073` tokens, host Mamba `5.51 GB`, `prefetch_threshold=256`, RH on, watermarks
`55000/110000`, `hicache_restore_wait_timeout_s=60.0`, `max_running_requests=1`, write_through/cache.

**Parameter proposal (bounded):**

1. Build one durable artifact: 1 request, prompt ≈ **54,976 tokens** (the R38-anchored span; below the
   `55000` RH low watermark), unique marker prefix, `max_tokens` 1-4, streamed to completion;
   wait for L3 write-through ACK drain (no `ongoing_write_through`/`ongoing_backup` residue in the
   log). Pool target: KV (+ Mamba sidecar present).
2. Clear residency deterministically: one bounded server restart of the same frozen profile (L3
   storage dir preserved), or a bounded number of auxiliary builds that evict the artifact from
   device and host. Record which was used and why.
3. Target T: 1 request, same prefix + short unique suffix, `max_tokens` 1-4. Expect a positive full
   L3 hit. Under C1, T must first be parked in a prior wait reason and then re-issued as DEMAND;
   the exact way to reach the prior park must be predeclared and observed, not guessed.
4. Release leg (R1): predeclare exactly one holder with in-flight staging (a second long-prefix
   request), then `POST /abort_request {"rid": "<holder_rid>"}` exactly once. The holder rid must be
   chosen so its `startswith` prefix does not match the target rid.
5. Bounds: total requests `<= 6`; total prompt tokens `<= 4 x 65530`; wall-clock `<= 600 s`;
   single release; single target retry; pool target KV (+ Mamba).

**Acceptance oracle (observe, never control):** `restore_host_alloc_retry_result` with
`positive_hit_tokens > 0` and `retry_outcome=revoked_alloc_failed`; then `restore_host_alloc_wait`
`state=WAIT_CAPACITY reason=HOST_ALLOC` with a captured cursor; then exactly one
`host_allocability_change` with `returned_units > 0` (or a genuine evictable-signature change) on the
blocked pool and generation strictly greater; then one `restore_host_alloc_wake_decision
decision=grant` with `retry_grant=true`; then one `restore_retry cause=capacity`; then full
all-or-nothing finalize and `ready_host` on the same RID/attempt. Any missing leg is
`NOT_VERIFIED`.

## 6. Fail-closed conditions

1. No positive full L3 hit (`storage_hit_count < 256` or `<` requested full span) → stop; do not park.
2. Park reason is not `HOST_ALLOC` (e.g. RH `NO_HEADROOM`, `PREFETCH_BUDGET`, `FRONTIER`,
   `REVALIDATE`) → stop; wrong event.
3. `positive_hit_tokens == 0` (aux-issue `forfeited_alloc_failed`) → stop; not the required positive path.
4. More than one target retry, same-generation self-wake, or a skipped eligible FIFO predecessor → stop.
5. Release produces no `host_allocability_change` with a strictly advanced blocked-pool generation
   before the timeout → stop.
6. Any partial sidecar, crop/lower-frontier substitution, discarded hybrid, or recompute fallback → stop.
7. Any need for product imports/monkeypatch, allocator/scheduler internal calls, `/flush_cache` while
   a waiter exists, or profile/RH/session-flag changes → stop (out of scope / R38 boundary).
8. Any provenance mismatch (server args, source hashes, GPU) → stop.

## 7. Artifacts

- Created: `.memory/phase2-hicache-design/work/P0-B-CAPACITY-ACTION-20260911-R67.md` (this report).
- Mirror (coordination convention): `3rdparty/sglang-3090-24g-opt/.memory/phase2-hicache-design/work/P0-B-CAPACITY-ACTION-20260911-R67.md`.
- No product/test/gate/storage/Git file and no remote resource was changed or accessed.

## 8. Evidence

- Product source (HEAD `4f41f5ba`): `managers/scheduler.py:3121,3517-3593,3600-3629,3724-3876,3946-3963,4692-4697,4777,5049-5062,5180-5215,5570-5574,7210-7227,7383-7412,7631-7651,8041-8054`;
  `managers/scheduler_components/ready_horizon.py:227-234,481-489,491-556`;
  `mem_cache/unified_radix_cache.py:1643,3273-3288,3663-3773,3775-3819,4195-4211,5106-5144,5240-5457,5520,5579-6646,6304-6532,6579-6646,7166-7249,6167-6215`;
  `mem_cache/unified_cache/unified_tree_core.py:1226-1236,1665-1690,1932-1964`;
  `mem_cache/unified_cache/components/full_component.py:230-257`;
  `entrypoints/http_server.py:899,971,1047,1063,1485,1576,1590,1610,1726`;
  `server_args.py:1471-1474`.
- Prior local evidence: R34 (no existing HOST_ALLOC liveness vehicle), R38 (minimum evidence legs;
  the ~54,976-token positive span), R45/R53 (focused fixtures only), R54 (existing vehicles cannot
  close the chain; telemetry schemas), R59 §4-5 (frozen profile and capacity semantics), R60/R64
  (frozen capacity: host KV `131073`, device `65536`, `max_req_input_len=65530`, RH watermarks,
  `hicache_restore_wait_timeout_s=60.0`), R65 (vehicle inventory and single-3060 serialization).
- Independent local checks: `git -C sglang-3090-24g-opt rev-parse HEAD` = `4f41f5bab562b99562f30c67540eb05344d13637`;
  targeted symbol/line reads listed above.

## 9. Summary

Read-only determination complete. The release/wake action is identifiable and bounded: a discrete
`POST /abort_request` on a predeclared staged holder queues a host release whose drain emits a
`host_allocability_change` (`queued_release_drain`/`direct_free`, `returned_units > 0`) that advances
the blocked-pool generation and wakes the parked waiter for one DEMAND retry. The create action is
**not** deterministically available through existing public interfaces on the frozen RH-ON profile:
the RH headroom gate prevents a speculative prefetch from failing host allocation, and the only
code-consistent first-park route (a DEMAND re-issue after a prior wait reason) is not demonstrated by
any existing vehicle. The recommended bounded scenario therefore proves the park before attempting
the release, and fails closed if the park is not `HOST_ALLOC` with a positive full hit.

## 10. Followups

1. Orchestrator: treat create-side determinism as the open blocker. A fresh `debugger-deep` or
   `architect` invocation **with reasoning** should resolve whether a DEMAND re-issue can be driven
   from existing public interfaces and a reachable prior wait, before any harness authorization.
   **NEEDS_REASONING**.
2. If a harness is later authorized, the exact bounded scenario in §5 plus the §6 fail-closed list
   should be the dispatch input; this report does not authorize implementation or execution.
3. Verify (read-only) the reachable prior wait reasons and their park/resume transitions against
   `hicache_restore.py` states before relying on C1.
4. Confirm the frozen profile still matches R60/R64 at execution time (RH flags, watermarks,
   `hicache_restore_wait_timeout_s`, host pool sizes) before using the §5 numbers.

## 11. Open issues

1. **Create-side determinism unresolved:** no public-interface action is shown to deterministically
   produce the first positive-hit `HOST_ALLOC` park on the frozen RH-ON profile; the RH headroom gate
   is a structural obstacle (`ready_horizon.py:481-489,530-549`).
2. **Steady-state host-bytes bound:** a single request's span `<= 65530` while
   `free + evictable >= 131073 - 65536 = 65537` absent non-evictable locks/staging; pure request-count
   saturation is not shown to be sufficient.
3. **DEMAND re-issue route (C1) unproven:** its reachability from public requests, and whether the
   storage query still returns a full positive hit on the re-issue, are unverified.
4. **`/abort_request` prefix matching:** abort matches by `req.rid.startswith(recv_req.rid)`
   (`scheduler.py:7632`), so holder/target RID naming must be chosen to avoid aborting the target.
5. **FIFO evidence:** a single waiter proves one retry but weak predecessor-ordering evidence
   (R54 open item 5 persists); a controlled predecessor would be required for a stronger claim.
6. **Telemetry join remains subject to R32's null-identity limitation** (`rid=null`,
   `attempt_id=null`, `causal_rid=null`); even a successful physical park may fail the identity join.
7. **Mirror ambiguity:** two phase2 `.memory` roots coexist; this report is written to the live
   workspace root and mirrored to the product worktree.
