# COD-20260908-P0-DURABILITY-TRACE-V2

Task ID: `COD-20260908-P0-DURABILITY-TRACE-V2`  
Epoch: `E20260908-P0P1P2`  
Role: `coder`  
Invocation status: **done**  
Admission: **ACCEPT**

## Summary

Implemented the approved additive five-file expansion in the active
`sglang-3090-24g-opt` worktree. The trace remains diagnostic-only and is
enabled only by `/tmp/t38c-durable-trace`; the existing `/tmp/t38c-on` trace
was preserved. No token IDs, state bytes, tensors, raw slot lists, fsync, or
crash-durability claim was added.

The requested report is stored in the control checkout because the active
product diff is in the adjacent `sglang-3090-24g-opt` worktree:
`/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/COD-20260908-P0-DURABILITY-TRACE-V2.md`.

## Event schema

Every new durable event is emitted as `schema_version=p0_durable.v2` and
contains `run_id`, `event_id`, `evt`, `ts_wall_ns`, `ts_mono_ns`, `process_id`,
`rank`, `thread_id`, `local_seq`, `operation`, `attempt`, `result`, and the
optional correlation fields `operation_id`, `attempt_id`, `node_id`,
`anchor_id`, `pool`, `tier`, `final_kv_hash`, `storage_key`, `mamba_key`,
`extent_id`, `extent_generation`, `old_generation`, `new_generation`,
`slot_digest`, `requested_pages`, `succeeded_pages`, `reason`,
`predecessor_event_id`, and `evidence_ref`. `run_id` uses vehicle-provided
`T38C_RUN_ID` when present, with a process-scoped fallback; product code does
not create or infer session IDs. Vehicle-side `session_id -> build_rid ->
final_kv_hash/node_id` joining remains required.

`slot_digest` is SHA-256 over pool name, tensor dtype/shape, and exact integer
slot indices. It is calculated only while the durable marker exists.

## Exact hooks

- `unified_radix_cache.py:165-365`: durable envelope, slot digest, keyed
  detach/completion tracking, and `residency_barrier`. The old pre-free
  `residency_release` interpretation is gone; detach events are emitted before
  allocator release, while completion events are emitted after return.
- `unified_radix_cache.py:1080-1147`: node-scoped post-drain barrier checks.
- `unified_radix_cache.py:1580-1628`: actual device and host component-free
  completion after `_apply_cache_action` / `free_host_values` returns.
- `unified_radix_cache.py:4170-4235`: queued primary and extra-pool host
  release completion after the pool free returns.
- `hybrid_cache_controller.py:64-151`: controller-side `p0_durable.v2`
  envelope and digest.
- `hybrid_cache_controller.py:372-429`: `residency_release_enqueued` after
  each page is put into the unchanged release queue payload; pool and digest
  are recorded for KV and extra pools.
- `hybrid_cache_controller.py:723-752`: operation/attempt/node/hash context
  is attached to storage queries.
- `extent_allocator.py:43-99`: allocator-side durable envelope.
- `extent_allocator.py:213-218,234-244,246-271,275-302`: exact keyed
  `storage_invalidate` records. `_drop_slot` records keys after removals and
  generation increment (`commit_reuse` / `lru_gc`). `clear` records exact keys
  before ownership is discarded and reports unchanged observed generation.
  Allocator selection, return values, LRU order, cursor behavior, and
  generation mutation remain unchanged.
- `extent_file_backend.py:93-150`: backend durable envelope.
- `extent_file_backend.py:738-768`: Mamba query records include operation,
  storage key, extent ID/generation, and exact present/miss result. The
  generation-less backend GC/clear summaries were removed; allocator records
  are authoritative.
- `mamba_component.py:63-151`: Mamba durable envelope and digest.
- `mamba_component.py:417-484`: keyed `residency_detach` after
  `value=None`/`host_value=None`, with final KV/Mamba key and attached session
  IDs when available.
- `mamba_component.py:1076-1097`: `residency_free_complete` after the actual
  Mamba host allocator free returns.
- `mamba_component.py:1116-1137`: `residency_release_enqueued` for the
  `FreeComponentHostSlot` path after queue insertion.

Event families are: `backup_host_commit`, `backup_submit`,
`batch_set_result`, `extent_commit`, `backup_ack_enqueue`,
`backup_ack_drain`, `storage_persisted`, `storage_query`,
`storage_invalidate`, `residency_detach`, `residency_release_enqueued`,
`residency_free_complete`, and derived `residency_barrier`.

## Files changed

Authorized product write set only:

1. `python/sglang/srt/mem_cache/unified_radix_cache.py`
2. `python/sglang/srt/mem_cache/hybrid_cache/hybrid_cache_controller.py`
3. `python/sglang/srt/mem_cache/storage/extent/extent_file_backend.py`
4. `python/sglang/srt/mem_cache/storage/extent/extent_allocator.py`
5. `python/sglang/srt/mem_cache/unified_cache/components/mamba_component.py`

No focused test was added or modified.

## Verification

- `python3 -m py_compile` on all five changed files: **PASS**.
- `git diff --check`: **PASS**.
- Focused test command:
  `python3 -m pytest test/registered/unit/mem_cache/test_extent_file_backend_unit.py -q`
  **BLOCKED** before collection: the environment has no `pytest` module.
- Import/runtime unit execution was not possible in this environment because
  both `pytest` and the repository runtime dependencies (`torch`, `msgspec`)
  are unavailable.

## Semantic-delta review

- Marker-off path: durable helpers return before file IO, allocator lookup
  correlation, digesting, state tracking, or diagnostic counting. Existing
  `/tmp/t38c-on` behavior is unchanged.
- Extent allocator: only optional diagnostic `reason` parameters were added to
  internal `_drop_slot` calls. Index removal, generation bump timing, return
  values, LRU order, cursor selection, and lock ownership are unchanged.
- Mamba: detach assignments, eviction eligibility, host-LRU changes,
  cache-action routing, and pool APIs are unchanged; logging occurs after the
  existing field assignment or allocator call.
- Queued host release: queue objects, page splitting, payload tensors, drain
  limits, concatenation, and free calls are unchanged; completion is emitted
  only after the existing free call returns.
- KV+Mamba fold: no acceptance, frontier, backup, ACK, or cache eligibility
  behavior was changed. `residency_barrier` is conservative: it requires
  keyed completion evidence, no remaining KV/Mamba values, and empty release
  queues. Deleted-node cases deliberately publish no false barrier.

## Remaining gaps and disposition

- Focused tests need a runtime with `pytest`, `torch`, and `msgspec`.
- No 3090 vehicle or remote deployment was run by this coder invocation.
- The vehicle must provide `T38C_RUN_ID`, perform the documented
  `session_id/build_rid` join, require both durability and residency barriers
  before warm lookup, and derive `combined_durable`/`cold_residency`; product
  code does not claim crash or power-loss durability.

The P0 vehicle is **strict-proof runnable at the product-trace boundary** once
this active worktree is deployed with its existing vehicle-side join and the
focused test/runtime dependencies are available. This report does not claim a
strict-proof run result.

## Final status

`done`

Artifacts: the five authorized product files and this report.  
Evidence: py_compile PASS, diff-check PASS, focused test dependency blocker.  
Open issue: runtime test dependencies and vehicle execution remain with the
test/execution owners; no hook or semantic NEEDS_REASONING condition remains.
