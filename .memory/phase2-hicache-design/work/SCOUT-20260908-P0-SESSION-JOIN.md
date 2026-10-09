# SCOUT-20260908-P0-SESSION-JOIN

- Task ID: `SCOUT-20260908-P0-SESSION-JOIN`
- Epoch: `E20260908-P0P1P2`
- Role: `scout`
- Invocation status: `done`
- Admission: `ACCEPT`
- Scope: read-only exploration; this report is the only file written.

## Result

The current active `sglang-3090-24g-opt` trace cannot safely produce the required
live join. It has operation/node/hash correlation, and the runtime already has
request `session_id` state, but there is no path from the vehicle's build request
identity into deferred storage/residency operations. There is also no current
`durability_barrier(combined_durable=true)` event. A timestamp or event-order
join would therefore be non-authoritative and violates the P0 contract.

The smallest safe solution is an additive, marker-gated trace context attached
to the request, retained on the cache node, copied onto storage operations and
pool transfers, and copied into every trace event. It must be observational only:
no cache key, allocator decision, LRU order, fold, acceptance, or scheduling
behavior may read this context.

## Search limits

Inspected the active diff and the requested P0 durability plan, live-vehicle
report, V2 trace report, both V2 remote-test reports, and the parked vehicle.
Searched the active `python/sglang/srt` cache/request paths and `3090-dev`
helpers for the named event families and identity fields. I did not inspect
unrelated model, kernel, frontend, or external/remote files. Remote deployment
state was not queried.

## Observed facts and evidence

### Existing request/session identity

- `Req.__init__` accepts `session_id` at
  `python/sglang/srt/managers/schedule_batch.py:834-880`; it stores
  `self.session_id` at `:901-904` and initializes
  `self.session_generation` at `:904`.
- OpenAI serving already passes `request.session_id` into `Req` at
  `python/sglang/srt/entrypoints/openai/serving_completions.py:120-137`.
- Session-ref tracking resolves `req.session_id` (or the session object's ID)
  at `python/sglang/srt/mem_cache/unified_cache/session_ref_tracker.py:48-52`,
  validates generation at `:63-70`, and registers the leaf with each component
  at `:72-79`.
- This is existing session-cache bookkeeping, not a durable-trace identity
  propagation path. The parked vehicle currently puts only model/messages/
  generation settings in its request payload at
  `3090-dev/gate3_parked.py:453-465` and `:590-607`; its build row obtains the
  generated request ID from the response (`sx.rid` or `meta.request_id`) at
  `:476-478`.

### Current operation and storage path

- The active hybrid `StorageOperation` contains host/token/hash/prefix and
  pool-transfer state at
  `python/sglang/srt/mem_cache/hybrid_cache/hybrid_cache_controller.py:152-165`.
  `PrefetchOperation` adds the request ID at `:167-187`. Neither declares
  `session_id`, `session_generation`, `build_rid`, or `warm_rid`.
- The generic operation class likewise has only storage data plus an integer
  operation ID at `python/sglang/srt/managers/cache_controller.py:258-287`.
- Write construction creates a storage operation, assigns only `node_id`, and
  queues it at `python/sglang/srt/mem_cache/hybrid_cache/hybrid_cache_controller.py:689-715`.
  The active radix caller is `write_backup_storage`/
  `_write_backup_storage_node` at
  `python/sglang/srt/mem_cache/unified_radix_cache.py:2483` and `:2553`; the
  existing call supplies `node_id` but no vehicle/session context.
- The current `backup_submit` record is emitted at
  `unified_radix_cache.py:2571-2630` and contains operation ID, attempt ID,
  node ID, final KV hash, and transfer counts. It does not contain
  `session_id`, `session_generation`, or `build_rid`.
- `backup_ack_enqueue` is emitted by the backup thread at
  `hybrid_cache_controller.py:1031-1069`; it carries operation/attempt,
  node/hash, transfer booleans, completed tokens, and result only.
- `backup_ack_drain` is emitted at
  `unified_radix_cache.py:4042-4076`. The subsequent durable frontier
  promotion calls `advance_storage_persisted` at `:4103-4113`, and
  `storage_persisted` records are emitted for each promoted node at
  `:4114-4135`. These records still carry operation/node/hash/frontier data,
  not session/build identity.
- The existing storage query path builds `HiCacheStorageExtraInfo.extra_info`
  with operation ID, attempt ID, node ID, and final hash at
  `hybrid_cache_controller.py:717-731`; the extent backend consumes this
  context for `storage_query` at
  `python/sglang/srt/mem_cache/storage/extent/extent_file_backend.py:738-767`.
  This is the cleanest existing hook for additive query metadata, but the
  current context has no session/build fields.
- Query-side pool transfers receive private operation/node/hash attributes at
  `hybrid_cache_controller.py:741-755`. The same pattern can carry a trace
  context without changing transfer semantics.

### Mamba detach/free and barriers

- Mamba detach records are emitted after the component value is cleared at
  `python/sglang/srt/mem_cache/unified_cache/components/mamba_component.py:417-455`
  and `:457-484`. They include node/hash, Mamba key, pool/tier, slot digest,
  and `session_ids` from component data, but no `build_rid`; the component
  session set can also contain multiple sessions and is not an exact vehicle
  join.
- Mamba host free completion is emitted after the actual allocator free returns
  at `mamba_component.py:1076-1097`, but that event contains only pool/tier,
  slot count/digest, and result. It has no node/session/build identity.
- Queued Mamba host release is recorded at `mamba_component.py:1116-1137`.
  The queue payload is unchanged and the event has no vehicle identity.
- The shared durable envelope normalizes operation/attempt/node/hash/storage
  fields but not session/build fields at
  `unified_radix_cache.py:201-255`, `hybrid_cache_controller.py:93-145`,
  `extent_file_backend.py:93-145`, and `mamba_component.py:98-149`.
- `residency_barrier` is node-scoped and emitted only after keyed detach/free
  completion, empty release queues, and no remaining KV/Mamba values at
  `unified_radix_cache.py:288-329`; callers invoke it after eviction/demotion
  frees at `:1080-1097`, `:1110-1119`, and `:1142-1147`.
- A search of the active product and vehicle paths found no
  `durability_barrier` or `combined_durable` emitter. The vehicle fixture
  synthesizes those fields only in `3090-dev/rh_durability_driver.py:82-98`,
  while live mode explicitly refuses because `gate3_parked.py` has no per-
  session pre-warm barrier callback at `:124-134`.

## Answers to the requested questions

### 1. Where the identifier can attach

The existing safe attachment points are:

1. Vehicle request: use the already supported request `session_id`; add a
   marker-gated trace-only field carrying the vehicle's `build_rid` (and
   optional `warm_rid`) alongside the request metadata. The parked driver must
   preserve the generated build RID from the response row and send the same
   session/build tuple on the trace-enabled request path.
2. Request/cache boundary: retain a trace context on the request/node at the
   point where the request commits its leaf. The existing component session
   tagging proves that node/component metadata survives beyond the request,
   but it is not sufficient for exact build-RID correlation.
3. Storage operation: copy the context to `StorageOperation`/
   `PrefetchOperation` and to each `PoolTransfer` private trace context. This
   reaches backup submit, ACK enqueue/drain, storage persistence, and query.
4. Mamba/residency: copy the same immutable context into detach, release,
   free-complete, and both barriers. Barriers must repeat the explicit tuple;
   they must not be reconstructed from timestamps.

### 2. Exact functions/fields that can carry it

The concrete existing chain is:

`Req.session_id/session_generation` -> radix node trace context at the backup
construction boundary (`unified_radix_cache.py:2483,2553,2571-2630`) ->
`StorageOperation` creation (`hybrid_cache_controller.py:689-715`) ->
`backup_ack_enqueue` (`:1031-1069`) -> `backup_ack_drain`
(`unified_radix_cache.py:4042-4076`) -> `storage_persisted`
(`:4111-4135`) and `HiCacheStorageExtraInfo.extra_info`
(`hybrid_cache_controller.py:717-755`) -> `storage_query`
(`extent_file_backend.py:738-767`) -> Mamba detach/free
(`mamba_component.py:417-484,1076-1137`) -> node-scoped residency checks
(`unified_radix_cache.py:288-329,1080-1147`).

The current fields that are usable as stable non-session keys are
`operation_id`/`attempt_id`, `node_id`, `final_kv_hash`, `storage_key`,
`mamba_key`, `extent_generation`, and `slot_digest`. The missing additive
fields are `session_id`, `session_generation`, `build_rid`, and optional
`warm_rid`; `operation_id`/`attempt_id` remain operation identity, not vehicle
identity.

### 3. Smallest additive marker-gated interface and write set

No safe route exists with the current active files alone. The smallest
interface is a trace-only context, enabled only by the existing
`/tmp/t38c-durable-trace` marker:

```text
trace_context = {
  schema_version: "p0_durable.v3",
  session_id: string,
  session_generation: int | null,
  build_rid: string,
  warm_rid: string | null,
}
```

Every relevant event additionally carries this context plus the existing
node/hash/operation fields. The two required derived records are:

```text
durability_barrier: combined_durable=true
residency_barrier: cold_residency=true
```

Both barriers must repeat `session_id`, `session_generation`, `build_rid`,
`node_id`, and `final_kv_hash`. The vehicle may issue a warm request only after
both records for the exact tuple are observed. `storage_persisted` alone is
not the combined barrier because it proves only the KV storage frontier.

Recommended exact product write set for a fresh implementation dispatch:

- `python/sglang/srt/managers/io_struct.py` or the authoritative request-input
  schema: accept an optional marker-gated trace context; do not change normal
  cache-key construction.
- `python/sglang/srt/managers/schedule_batch.py`: copy the optional context onto
  `Req` without using it in scheduling or cache semantics.
- `python/sglang/srt/mem_cache/unified_radix_cache.py`: retain/copy the context
  on the node trace sidecar; add it to backup submit/ACK drain, storage
  persisted, Mamba completion callbacks, and emit keyed durability/residency
  barriers after existing checks.
- `python/sglang/srt/mem_cache/hybrid_cache/hybrid_cache_controller.py`: add
  the optional context to storage operation creation, backup ACK enqueue, and
  `HiCacheStorageExtraInfo.extra_info`; copy it to pool transfers.
- `python/sglang/srt/mem_cache/storage/extent/extent_file_backend.py`: emit
  the received context on storage query/persist events; do not use it for
  allocator lookup.
- `python/sglang/srt/mem_cache/unified_cache/components/mamba_component.py`:
  carry the node's context through detach, queued release, and free completion.
- Vehicle-side fresh write set: `3090-dev/gate3_parked.py` plus the parser/
  barrier driver assigned in that dispatch. It must send the tuple, wait on
  both keyed barriers before warm lookup, and reject missing fields; no
  timestamp-only fallback.

This is additive metadata only. The active five-file trace already uses the
marker and can retain `p0_durable.v2` compatibility for marker-off behavior;
the v3 schema should be emitted only when the new context is present, with
missing context treated as `NOT_VERIFIED`, not as an inferred join.

### 4. Test and rollback plan

Test in this order:

1. Marker-off regression: assert no trace sidecar allocation, no added request
   behavior, and unchanged cache hit/miss/eviction paths.
2. Schema fixture: one request with a known tuple must show the exact tuple on
   backup submit, ACK enqueue/drain, storage persisted/query, Mamba detach/free,
   durability barrier, residency barrier, and warm lookup. A fixture missing
   any required field must be `NOT_VERIFIED`.
3. Ordering test: warm lookup is rejected/held by the vehicle until both keyed
   barriers precede it; equal timestamps are resolved by trace sequence/event
   identity, never timestamp-only matching.
4. Recycle test: force a keyed invalidate/reuse between write and query and
   verify the join distinguishes it without changing allocator generation or
   cache eligibility behavior.
5. Focused runtime checks: `py_compile`, `git diff --check`, and the existing
   extent backend unit test in the runtime that has `pytest`, `torch`, and
   `msgspec`; then the authorized S=25 RH-off vehicle only.

Rollback is deleting/disable-gating only the additive trace-context hooks and
new event fields. The marker-off path must remain byte-for-byte behaviorally
equivalent; no cache data, allocator state, request scheduling, or existing
trace semantics should require the new context.

## Followups

- Fresh `coder` dispatch is required for the product interface above; this
  scout invocation does not authorize implementation.
- Fresh `executor`/vehicle dispatch must update `gate3_parked.py` and the live
  barrier collector only after the product schema is stable.
- Fresh focused runtime/test dispatch should verify the marker-off and schema
  fixture cases before any remote run.

## Open issues

- The exact authoritative request-input type/file for a new trace-only field
  was not selected beyond the `Req` and OpenAI serving evidence; adding a new
  public request field requires the implementation owner to inspect the request
  schema before editing.
- Deferred eviction can outlive the originating request, so request-local
  metadata alone is insufficient; node-side retention is required.
- Component `session_ids` is a set and cannot substitute for the exact
  `session_id -> build_rid` join.
- Existing remote-test evidence validates the five-file V2 deployment and
  extent unit test, but does not validate live vehicle session/build
  propagation.

## Final status

`done`

Artifacts: this report only.
Evidence: file/line inventory above, active diff inspection, and requested P0
trace/plan/vehicle reports.
Summary: no safe current join; additive marker-gated request-to-node-to-
operation context is the smallest path that preserves cache semantics.
