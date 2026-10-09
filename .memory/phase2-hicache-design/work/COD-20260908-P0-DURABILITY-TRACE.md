# COD-20260908-P0-DURABILITY-TRACE

Task: `COD-20260908-P0-DURABILITY-TRACE`  
Epoch: `E20260908-P0P1P2`  
Role: coder  
Invocation status: **blocked — NEEDS_REASONING**

## Scope and outcome

Implemented additive, marker-gated P0 durability tracing in the three authorized
T38C files only. The trace is disabled unless `/tmp/t38c-durable-trace` exists
and writes JSON lines to `/tmp/t38c-probe.log`. It records identifiers, hashes,
pool names, counters, generations, and lifecycle results; it does not record
token IDs, tensors, or state bytes. The pre-existing `/tmp/t38c-on` trace was
preserved.

The three-file scope captures the true storage ACK and radix durable-frontier
promotion path, but cannot capture every required invalidation source. Exact
per-key extent recycle generation is owned by `extent_allocator.py`, and
component-level Mamba host invalidation is owned by the Mamba component file;
both were explicitly out of scope. Therefore this invocation does not claim a
complete strict durability/residency proof for the next vehicle.

## Files changed

- `python/sglang/srt/mem_cache/unified_radix_cache.py`
- `python/sglang/srt/mem_cache/hybrid_cache/hybrid_cache_controller.py`
- `python/sglang/srt/mem_cache/storage/extent/extent_file_backend.py`

No allocator, tree-core, Mamba-component, memory-control, remote, or untracked
vehicle files were edited. The checkout already contained user changes in all
three product files and unrelated untracked `3090-dev` files; those were
preserved.

## Event schema

All new records include `trace: "p0_durable"` and `ts_ms`. Common correlation
fields are `operation_id`, `attempt_id`, `node_id`, `final_kv_hash`, `pool`, and
`result` where available. Events are:

| Event | Evidence carried |
|---|---|
| `backup_host_commit` | D→H host commit, node/hash, KV and Mamba presence, host slot count |
| `backup_submit` | storage operation/attempt ID, node/hash, KV/Mamba transfer presence, page counts, Mamba key |
| `batch_set_result` | pool, requested/succeeded pages, boolean result, operation correlation; geometry failures include a reason |
| `extent_commit` | operation correlation, extent ID, allocator generation(s), page count; emitted after allocator `commit` returns |
| `backup_ack_enqueue` | storage ACK queue enqueue, operation/node/hash, KV/Mamba presence, completion result |
| `backup_ack_drain` | ACK consumer drain, completion/requested counts, complete/partial result |
| `storage_persisted` | actual radix promotion, anchor/node/hash, frontier end, anchor storage version, global publish epoch |
| `residency_release` | node/hash, eviction reason, device/host slots released, observed L3-durable state |
| `invalidation` | backend clear or extent GC recycle observation, reason, result/count; generation is `None` where the allocator hook is unavailable |

## Exact hook references

Line numbers refer to the post-change checkout.

- `unified_radix_cache.py:159-174`: new `/tmp/t38c-durable-trace` logger.
- `unified_radix_cache.py:1675-1691`: D→H `backup_host_commit` after the existing host commit.
- `unified_radix_cache.py:2344-2440`: storage `backup_submit` after `write_storage` returns; existing T38C node/hash propagation remains.
- `unified_radix_cache.py:909-970`: device leaf, demote, storage-backed hollow, and forced-miss residency release observations.
- `unified_radix_cache.py:3833-3875`: storage ACK drain observation.
- `unified_radix_cache.py:3909-3934`: `storage_persisted` emitted after `advance_storage_persisted` returns, with anchor version/frontier/epoch.
- `unified_radix_cache.py:4096-4109`: backend-clear invalidation observation.
- `hybrid_cache_controller.py:61-75`: controller logger.
- `hybrid_cache_controller.py:595-619`: stable storage operation/attempt metadata attached to the queued operation and sidecar transfers.
- `hybrid_cache_controller.py:799-877`: sidecar and KV `batch_set_result`; the KV context is passed only to the backend trace hook and does not affect storage behavior.
- `hybrid_cache_controller.py:920-961`: ACK enqueue observation after `_page_backup` completes.
- `extent_file_backend.py:90-128`: backend logger and extent-commit record helper.
- `extent_file_backend.py:551-618`: v1 KV commit observation after allocator commit.
- `extent_file_backend.py:883-976`: v2 per-pool result observation, including invalid host-index geometry.
- `extent_file_backend.py:1038-1073`: all-or-nothing write path emits extent ID/generation after allocator commit.
- `extent_file_backend.py:1096-1123`: extent-GC and backend-clear invalidation observations.

## Verification evidence

- `python3 -m py_compile python/sglang/srt/mem_cache/unified_radix_cache.py python/sglang/srt/mem_cache/hybrid_cache/hybrid_cache_controller.py python/sglang/srt/mem_cache/storage/extent/extent_file_backend.py`: **PASS**.
- `git diff --check`: **PASS**.
- The requested `python -m py_compile ...` spelling was unavailable because
  this checkout has no `python` executable; the equivalent `python3` command
  passed.
- The focused remote extent unit test was not run. Sync/remote test execution
  belongs to the separate devops/test task, and no SSH changes were performed.

## Unresolved gaps

1. `extent_allocator.py` owns `_drop_slot`/generation bump and per-key
   invalidation. The authorized backend can observe that GC recycled slots, but
   cannot safely emit the exact affected key set or new generation. GC records
   therefore contain `recycled_slots` and `generation: None`.
2. The Mamba component's host-value removal/recycle hooks are outside the
   authorized three files. `pc_mamba_query` retains the existing
   `removal_recycle_hook: "not_added"` marker; no lookup miss is misrepresented
   as an invalidation event.
3. `residency_release` observes frees at the radix eviction/demotion hooks, but
   host-pool release queues without a node identity are not relabeled as a
   per-session clear. A driver can use node/hash-correlated records where
   available, but cannot claim complete per-session GPU+Host clearance for all
   release paths from this scope alone.
4. Extent ACK semantics remain the existing contract: successful pwrite plus
   in-memory index registration. No fsync or metadata persistence was added;
   crash durability remains intentionally unchanged.

## Next vehicle disposition

The vehicle may be run for functional collection of the additive trace and for
the storage ACK/frontier chain. It is **not strict-proof runnable** for the full
requested criterion “KV+Mamba durable completion plus all GPU/Host residency
cleared before warm” until the out-of-scope allocator/Mamba lifecycle decision
is made. This is the reason for `NEEDS_REASONING`; no product scope was widened.
