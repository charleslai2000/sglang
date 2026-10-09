# Scout report: P0 durability / P1 Ready Horizon hooks

Task: `SCOUT-20260908-RH-HOOKS`, epoch `E20260908-P0P1P2`  
Repository inspected: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt`  
Status: **done**

## Scope and baseline

Read-only search was limited to `python/sglang/srt/mem_cache`, the scheduler and
scheduler components, the extent backend/allocator, existing `3090-dev` experiment
assets, and the phase2 design memory supplied by the workspace. No product files or
memory control files were changed. No SSH inspection was performed: the local tree
and existing handoff/evidence references were sufficient, and no remote endpoint was
needed to identify implementation hooks. Remote runtime availability remains
unverified.

The worktree is branch `3090-24g-opt` with pre-existing modifications in:
`hybrid_cache_controller.py`, `extent_file_backend.py`, and `unified_radix_cache.py`,
plus untracked `3090-dev` experiment scripts. Those changes were observed, not made
by this scout.

## 1. Mamba/KV backup submission and completion/ACK

Observed:

- `UnifiedRadixCache._execute_and_commit_kv_backup` builds the device-to-host backup,
  executes it, then commits tree host state only after the transfer result:
  `python/sglang/srt/mem_cache/unified_radix_cache.py:1595-1628`.
- The concrete backup spec is built by
  `UnifiedTreeCore.build_backup_spec` / `build_storage_backup_spec`; the latter
  carries KV `hash_value` and component transfers, including Mamba:
  `python/sglang/srt/mem_cache/unified_cache/unified_tree_core.py:2040-2087`.
- `HybridCacheController.write_storage` enqueues a `StorageOperation` on
  `backup_queue`: `hybrid_cache_controller.py:581-599`.
- `HybridCacheController._page_backup` submits sidecars with
  `storage_backend.batch_set_v2`, checks returned per-page booleans, and then calls
  the base KV backup unless `backup_skip` is active: `hybrid_cache_controller.py:777-814`.
  Mamba is explicitly retained on every TP rank by `should_backup` at
  `hybrid_cache_controller.py:816-835`.
- The backup worker executes `_page_backup` and puts the operation on
  `ack_backup_queue`: `hybrid_cache_controller.py:838-853`. This is the completion
  handoff; the consumer/reconciliation path should be paired with it for a true ACK
  timestamp.
- In the current branch, the extent backend's Mamba write trace is emitted from
  `batch_set_v2` after `_write_pages` returns: `extent_file_backend.py:835-883`.
  Invalid host-index geometry has a separate failure return at `:845-855`.
- The allocator documents and implements the durable index ACK point: `commit` is
  called only after pwrite succeeds, and updates the key index/generation at
  `extent_allocator.py:110-169`. `_write_pages` calls the allocator commit after the
  write at `extent_file_backend.py:958-990`.

Inference / smallest instrumentation surface:

- The minimum P0 proof is one correlation record spanning: backup submission
  (`node_id`, final KV hash, KV/Mamba transfer presence), host backup completion,
  `batch_set_v2` result per pool, extent allocator commit, and the tree durability
  promotion/ACK. The least invasive hooks are the existing queue submission
  (`hybrid_cache_controller.py:598`), worker completion (`:850-851`),
  `batch_set_v2` (`extent_file_backend.py:835`), and the existing tree promotion
  hook described below. Do not treat host-value creation alone as durable.
- Existing current-branch diagnostic code already attaches `_t38c_node_id` and
  `_t38c_final_kv_hash` to Mamba transfers before storage submission in
  `unified_radix_cache.py:2298-2328`; it is diagnostic-only and marker-gated.
- All-or-nothing semantics are visible at two levels: sidecar `batch_set_v2` returns
  all per-key results from one `_write_pages` operation, and extent `plan` is pure
  until `commit`. Instrumentation must observe results, not promote state or alter
  the commit ordering.

## 2. Extent persistence, durable frontier, and `batch_set_v2`

Observed:

- `UnifiedTreeCore` distinguishes `storage_written`, `storage_persisted`, and
  `storage_restored`; `mark_storage_written` is only a submission dedupe guard,
  while `mark_storage_restored` bumps L3 publication and the anchor version:
  `unified_tree_core.py:2089-2128`.
- Global diagnostic publication is `_bump_l3_publish` / `l3_publish_epoch` at
  `unified_tree_core.py:2130-2151`; eligibility uses per-anchor
  `_bump_anchor_storage_version` / `anchor_storage_version` at `:2153-2174`.
- `clear_storage_durable` explicitly invalidates stale durability beliefs and has a
  deferred-ACK guard: `unified_tree_core.py:2176-2195`.
- `commit_backup` commits host residency, not L3 durability:
  `unified_tree_core.py:2491-2515`. The L3 durable promotion must therefore be
  traced separately from D->H host commit.
- The current extent allocator uses generation invalidation on slot recycle:
  `extent_allocator.py:174-218`; `lookup` treats generation mismatch as a miss at
  `:76-85`. Backend `clear` delegates to allocator clear at
  `extent_file_backend.py:1019-1022`.
- Current `batch_exists_v2` computes KV prefix pages, folds sidecar boundaries into
  `final_pages`, and returns `PoolTransferResult`: `extent_file_backend.py:644-765`.
  The current branch first aligns the sidecar query to the actual KV frontier in
  `hybrid_cache_controller.py:610-624` and `:675-690`.

Inference / causal gap:

- A `batch_set_v2=True` result proves a backend write batch passed, but it does not
  alone prove that the radix node became `storage_persisted` or that the contiguous
  frontier crossed a request end. The smallest added evidence is a shared operation
  ID/node ID plus `write_submit`, `batch_set_result`, `allocator_commit`, `ack_drain`,
  `storage_persisted_promotion`, `anchor_version`, and `frontier_end` fields.
- Preserve the existing distinction: global `l3_publish_epoch` is diagnostic; P1
  re-eligibility must continue to use the anchor-local version. This is explicit in
  `unified_tree_core.py:2137-2143` and scheduler miss handling at
  `scheduler.py:3232-3281`.

## 3. Eviction/removal/recycle/clear invalidation paths

Observed:

- Unified tree removal is `UnifiedTreeCore.remove_node`: `unified_tree_core.py:259`
  (definition and callers should be paired with component cleanup).
- Device eviction has the main lifecycle hooks
  `evict_device_start`, `evict_device_next_node`, `evict_device_end`,
  `evict_device_leaf`, and `evict_device_leaf_storage_backed` at
  `unified_tree_core.py:1278-1450`; host eviction is surfaced through
  `UnifiedRadixCache.evict_host` at `unified_radix_cache.py:1371`.
- Component-level Mamba host invalidation is in
  `mamba_component.py:321-353` (host `host_value = None`, optional host-LRU
  insertion) and host-slot release is `:936-940`. Mamba restore/host attachment
  paths are `mamba_component.py:780-850`.
- Extent slot reuse and LRU GC invalidate all keys in the slot at
  `extent_allocator.py:174-218`; explicit backend clear is
  `extent_file_backend.py:1019-1022`.
- The current Mamba lookup trace explicitly reports
  `removal_recycle_hook: "not_added"` at `extent_file_backend.py:663-679` and
  `:734-760`. This is a concrete instrumentation gap.

Inference / smallest instrumentation surface:

- Add one invalidation event at each semantic boundary, not every tensor free:
  (a) component/tree host removal (`mamba_component.py:321-353` or common tree
  eviction callback), (b) extent `_drop_slot`/generation bump
  (`extent_allocator.py:197-218`), and (c) backend clear. Include key/pool where
  known, node/anchor ID where known, old generation, new generation, and reason.
- The causal proof needs the invalidation event joined to the next
  `batch_exists_v2` miss and to `clear_storage_durable`/anchor-version handling.
  Do not infer invalidation from a later lookup miss; recycle/clear can invalidate
  multiple keys without a request being present.

## 4. L3 lookup and Mamba boundary selection

Observed:

- Scheduler enters the storage path at `_prefetch_kvcache`, checks the anchor gate,
  and calls `tree_cache.prefetch_from_storage`: `scheduler.py:2962-3031`.
- `prefetch_from_storage` allocates component staging, builds Mamba/SWA sidecar
  transfers, and enqueues the controller prefetch at
  `unified_radix_cache.py:2647-2819`; the current branch logs the issue at
  `:2820-2829`.
- Controller `_storage_hit_query` first establishes KV hit pages, then passes only
  the KV-frontier hashes and aligned trailing transfers to `batch_exists_v2`:
  `hybrid_cache_controller.py:601-648`, `:675-690`.
- Extent `batch_exists_v2` checks KV presence, then for each transfer scans either
  all pages or a trailing window and clamps `final_pages` to the sidecar boundary:
  `extent_file_backend.py:644-765`. Mamba-specific diagnostic query fields are
  emitted at `:734-760`.
- Sidecar reads occur only after KV completes in `_page_transfer_sidecar`; it
  synchronizes trailing keys, calls `batch_get_v2`, counts pool hits, and emits the
  prefetch ACK: `hybrid_cache_controller.py:720-775`.

Inference:

- P0/P1 lookup proof must report both `raw_kv_frontier` and the post-Mamba
  `final_pages`/boundary. Existing fields are almost sufficient, but must include
  the selected candidate prefix length and invalidation generation/version used at
  lookup time. The current trace already exposes `tested_key`, `tested_present`,
  `matched_key`, `matched_present`, `boundary`, and `final_pages`.

## 5. Ready Horizon: eligibility, stage, L3 read, Host materialization, ready_host, admission

Observed:

- Ready Horizon policy defines strict resident READY membership as
  `state == READY`, `staged_tokens > 0`, and `full_prefix`; see
  `scheduler_components/ready_horizon.py:135-168` and `:262-278`.
- Scheduler constructs the policy/watermarks and causal state in
  `scheduler.py:1359-1425`.
- `_ready_horizon_pass` snapshots epochs, checks event-driven refill eligibility,
  builds a refill plan, calls `_prefetch_kvcache` for each stage, and emits existing
  `ready_stage` and `ready_pool` logs: `scheduler.py:3388-3493`.
- Candidate views include staged host tokens, host hit length, restore state,
  full-prefix status, and staging eligibility at `scheduler.py:3521-3556`.
- Epoch selection is explicit: L3 publication, host level, monotonic host release,
  speculative budget, and waiting frontier at `scheduler.py:3558-3587`.
- L3 read completion is drained into the restore state machine by
  `_feed_restore_terminal`; finalized/revoked outcomes and anchor-local miss state
  are handled at `scheduler.py:3218-3306`.
- Host materialization is represented by the tree's prefetch finalize marker;
  `peek_prefetch_loaded_tokens` documents that material is physically resident from
  finalize until admission consumes it, and `pop_prefetch_loaded_tokens` removes the
  marker at `unified_radix_cache.py:3152-3167`.
- Admission runs after restore reconciliation and Ready Horizon maintenance in the
  scheduler loop (`scheduler.py:4590-4593`), partitions READY requests first at
  `:4655-4659`, and consumes loaded tokens while building the prefill batch at
  `:4752-4800`. The actual `PrefillAdder` admission loop is
  `:4681-4891`.

Inference / smallest instrumentation surface:

- Existing `ready_stage` and `ready_pool` logs prove policy decisions but do not
  by themselves prove L3-read start/end or host materialization timing. Add paired
  `l3_read_start` / `l3_read_end` around the controller/backend read, and
  `host_materialized` at prefetch finalize where `prefetch_loaded_tokens_by_reqid`
  is set. Keep `ready_stage` as the issue decision, and add `ready_state_transition`
  or reuse existing restore-state logging at `_apply_restore_event`.
- Admission proof should join `ready_stage` -> `l3_read_end` -> host marker ->
  `pop_prefetch_loaded_tokens` -> `admission`, using `rid` and a per-prefetch
  operation/attempt ID. This is the smallest surface that distinguishes a staged
  host resident request from a merely READY state.

## 6. Existing trace/metrics fields suitable for extension

Observed:

- Current marker-gated `_t38c_log` traces already cover storage query, prefetch
  issue/outcome, sidecar get, Mamba query, Mamba write, and storage writes in the
  modified files. They are diagnostic-only and do not alter semantics.
- Existing scheduler logs include `[P2A]` restore events (`restore_state`,
  `restore_ready`, `restore_recompute`) and `[P3]` `ready_stage`/`ready_pool`.
- Existing request fields are suitable correlation anchors: `rid`, restore state and
  wait reason, `host_hit_length`, `cached_tokens_storage`, and staged-token marker;
  definitions are in `schedule_batch.py:1034-1058` and `:1165`.
- Existing tree fields provide `storage_written`, `storage_persisted`,
  `storage_restored`, `storage_version`, and global `l3_publish_epoch`; see
  `unified_tree_core.py:2089-2174`.
- The scheduler's capacity stats already expose KV host usable, Mamba host usable,
  READY resident, working, speculative inflight, and reserve tokens at
  `scheduler.py:3633-3702`.

Recommended trace schema (additive, semantics-neutral):

```text
ts_ms, evt, rid, attempt_id, node_id, anchor_id, pool,
kv_hash_tail, mamba_key, requested_pages, raw_kv_frontier,
selected_boundary, final_pages, host_tokens, staged_tokens,
restore_state, wait_reason, ready_count, ready_tokens,
storage_version, l3_publish_epoch, extent_id, extent_generation,
result, reason
```

Use event values such as `backup_submit`, `batch_set_result`,
`extent_commit`, `backup_ack`, `durable_promote`, `invalidate`,
`l3_read_start`, `l3_read_end`, `host_materialized`, `ready_stage`,
`ready_state`, `ready_pop`, and `admission`. Do not log token contents or state
bytes. `result` should be boolean/enum and `reason` should distinguish miss,
allocation failure, recycle, clear, eviction, and deferred ACK.

## Runnable status and causal gaps

The requested P0/P1 experiment is **conditionally runnable, but not fully
proof-runnable from this checkout alone**.

Observed readiness: the source contains the P0 backup/ACK path, extent all-or-nothing
write path, Mamba/KV boundary lookup, event-driven Ready Horizon stage path, host
residency marker, and scheduler admission path. Existing handoff memory identifies
3090 experiment assets and a remote production/test host, including a Ready Horizon
toggle and Gate C engine-join prerequisite (`phase2-hicache-design/work/
HANDOFF-2026-09-07.md:42-48,64-78`).

Blocking evidence gaps for a proof run:

1. The checkout does not establish that the remote 3090 runtime is live or matches
   this worktree; no SSH check was made.
2. The current Mamba trace says `removal_recycle_hook: not_added`, so an observed
   KV-hit -> Mamba-miss event cannot be attributed to eviction/recycle/clear without
   the additive invalidation hook.
3. Existing logs can show Ready Horizon issue and admission, but do not provide a
   complete L3 read start/end and host-materialization join key. The experiment can
   run functionally; a strict P0/P1 causal proof requires those fields or equivalent
   correlation from the runtime harness.
4. Existing worktree changes are dirty and include diagnostic code; exact deployed
   revision/hash and launch configuration must be verified by the execution owner.

Smallest followups for the implementation/test owners: add the operation/attempt
correlation and invalidation event at the hooks above, then run the existing 3090
launcher with RH OFF/ON and collect paired backup/ACK, recycle/miss, read/materialize,
and admission traces. Keep frozen capacity/Ready Horizon parameters unchanged and
preserve the existing all-or-nothing `batch_set_v2` and deferred-ACK semantics.

## Open issues

- Exact remote evidence location and live process/revision were not verified.
- The consumer that drains `ack_backup_queue` should be included in the final line
  reference set by the implementation owner if the ACK timestamp is required at
  scheduler granularity; this scout found the producer at
  `hybrid_cache_controller.py:850-851` and tree promotion state at
  `unified_tree_core.py:2111-2128`.
- Whether the experiment's acceptance permits existing marker-gated logs as
  sufficient, or requires the additive schema above, is a gate decision outside
  scout scope.
