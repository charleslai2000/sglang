ENTRY: ACCEPT

# COD-20260908-P0-TRACE-CONTEXT-V3

- Task ID: `COD-20260908-P0-TRACE-CONTEXT-V3`
- Epoch: `E20260908-P0P1P2`
- Role: `coder`
- Invocation status: `done`
- Admission: `ACCEPT`
- P0 vehicle/pass claim: **not claimed**

## Changed files

Product changes were limited to the existing V2 trace files plus one narrowly
scoped helper. Existing V2 edits, including `extent_allocator.py`, were
preserved and extended additively.

1. `python/sglang/srt/mem_cache/trace_context.py` (new): marker-gated v3
   context construction, event attachment, and slot-digest context registry.
2. `python/sglang/srt/mem_cache/unified_radix_cache.py`: retain the first
   session build tuple on node sidecars; associate later prefix-match/prefetch
   work with `warm_rid`; propagate context through backup, ACK drain,
   storage-persisted, query, free completion, and residency events; emit
   `durability_barrier` only after complete KV ACK/frontier plus successful
   Mamba sidecar pages; preserve the existing conservative residency barrier.
3. `python/sglang/srt/mem_cache/hybrid_cache/hybrid_cache_controller.py`:
   carry optional context on storage/prefetch operations and pool transfers;
   preserve it through query, backup, ACK enqueue, and queued release paths.
4. `python/sglang/srt/mem_cache/storage/extent/extent_file_backend.py`:
   forward operation context into extent commits and generation-keyed
   invalidations; include context on sidecar result and query events.
5. `python/sglang/srt/mem_cache/storage/extent/extent_allocator.py`:
   accept optional diagnostic context on commit/GC/clear and attach it to
   keyed `storage_invalidate` records without changing allocator behavior.
6. `python/sglang/srt/mem_cache/unified_cache/components/mamba_component.py`:
   attach node/session context to Mamba detach, queued release, and actual
   host-free completion events.

`io_struct.py` and `schedule_batch.py` were not changed: the existing
authoritative `Req.session_id`/session object and `Req.rid` are sufficient for
the marker-gated context derivation, so no new serialized request field or
scheduling behavior was introduced.

## Semantics

The context is top-level on v3 events when known:

```text
schema_version: p0_durable.v3
session_id: string
session_generation: int | null
build_rid: string
warm_rid: string | null
```

`build_rid` is the authoritative RID of the first cache insertion observed for
the session while the marker is active. A later request with the same session
identity is treated as the warm request only when an existing build context is
already retained; its RID becomes `warm_rid`. No second identity is generated.
Missing session/build identity returns no context and therefore cannot create a
guessed join.

Context remains observational. It is not used in cache keys, allocator
selection, LRU/eviction policy, fold/acceptance logic, scheduling, retries,
sleeping, fsync behavior, or storage I/O ordering. Old constructor/call sites
remain valid through optional parameters.

The combined durability barrier is emitted only for the same operation/node
when all of the following are true: KV completion covers the submitted span,
the node is promoted by the existing ACK-driven storage frontier, a Mamba
transfer exists, and the recorded successful Mamba sidecar pages cover that
transfer. No barrier is emitted for a missing or failed Mamba transfer.

Residency completion context is joined by the existing exact pool/tier/slot
digest registry. `residency_barrier(cold_residency=true)` remains gated by
actual free completion, no remaining KV/Mamba values, and empty release
queues. Invalidation remains exact storage-key plus allocator generation
keyed; no global invalidation is introduced.

## Diff summary

- Added one small trace-context helper module.
- Added optional context fields to asynchronous storage operations and private
  pool-transfer sidecars.
- Added context propagation to the existing V2 event families and derived
  `durability_barrier`/v3 context fields.
- Added context-aware generation/invalidation logging at the allocator owner,
  retaining old allocator state transitions and return behavior.
- No vehicle files, request wire schema, scheduler/cache semantics, plan,
  context, ledger, or primary documentation files were edited.

## Verification evidence

Commands run in `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt`:

- `python3 -m py_compile` on all six changed Python files: **PASS**.
- `python3` AST parse of all six changed Python files: **PASS**.
- `git diff --check`: **PASS**.
- Static surface assertion for v3 schema, context fields, both barriers, and
  keyed invalidation: **PASS**.
- Marker behavior check: v3 context is produced with the active marker, and
  the same helper returns `None` under a locally stubbed marker-off probe:
  **PASS**. The workspace marker itself was not changed.
- Focused test command:
  `python3 -m pytest test/registered/unit/mem_cache/test_extent_file_backend_unit.py -q`
  **BLOCKED before collection**: `/usr/bin/python3: No module named pytest`.
- Remote engine/vehicle execution: **not run**, as explicitly prohibited by
  this task.

## Exact residual join gap

The product patch does not add or accept a new vehicle request field. It
derives `build_rid` from the first observed cache insertion RID for a session
and `warm_rid` from a later request RID. Therefore the live vehicle must:

1. provide a stable `session_id` on both build and warm requests;
2. enable `/tmp/t38c-durable-trace` before the build request is cached; and
3. join/read the keyed v3 barriers before issuing or accepting the warm lookup.

If the session ID is absent, the marker starts after the build insertion, the
node is deleted before the context can be retained, or the causal operation
belongs to an object with no retained node/transfer sidecar, the product emits
the existing diagnostic event without fabricated context. Such records are
`NOT_VERIFIED` for the vehicle, not a pass. Multi-build reuse of one session
is intentionally not disambiguated beyond the retained first build tuple; a
vehicle needing explicit build/warm identities must add that as a fresh
vehicle/request-contract task.

## Followups and open issues

- Vehicle-side request/session wiring, keyed barrier collection, and warm-gate
  enforcement remain vehicle/test-owner work under a fresh Task ID.
- Focused runtime tests require an environment with `pytest`, `torch`, and
  `msgspec`; no dependency installation was requested or performed.
- This report supplies product-side prerequisite evidence only and does not
  establish P0 pass, live durability, crash durability, or remote correctness.

## Final status

`done`

Artifacts: the six product Python files listed above and this report.
Evidence: py_compile PASS, AST/static checks PASS, diff-check PASS, focused
pytest dependency blocker recorded. Extra work outside this invocation
requires a fresh Task ID.
