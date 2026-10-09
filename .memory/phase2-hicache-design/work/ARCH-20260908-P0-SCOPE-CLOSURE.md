# ARCH-20260908-P0-SCOPE-CLOSURE

- Task ID: `ARCH-20260908-P0-SCOPE-CLOSURE`
- Epoch: `E20260908-P0P1P2`
- Role: `architect`
- Invocation status: `done`
- Admission: `ACCEPT`
- Decision owner: orchestrator; this report is architectural evidence and a recommendation, not authorization.

## Summary judgment

The current three-file trace is **not sufficient** for the user's hard P0 gate.
It is sufficient to observe storage transfer construction, per-pool extent writes,
storage ACK drain, and radix `storage_persisted` publication. It cannot establish:

1. the exact storage key set removed by extent reuse/clear and the old-to-new
   allocator generation transition;
2. keyed Mamba device/host detachment at the component that sets
   `host_value = None`; or
3. completion of the GPU/Host allocator frees before warm lookup. The current
   `residency_release` event is emitted before `_free_values`, so it reports a
   planned release, not a completed release.

The smallest safe expansion is additive diagnostic instrumentation in **two new
product files** plus completion/correlation changes inside the already modified
trace files. No tree-core or scheduler change is required.

**Recommendation:** keep `RH-DUR-P0-02` and the P0 vehicle blocked for strict
proof until this expansion lands and its focused tests pass. A functional trace
run is permissible but cannot satisfy the P0 gate. The orchestrator must accept
or reject this scope decision before redispatch.

## Baseline evidence: observed facts

Line numbers below refer to the active opt worktree at
`/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt`, HEAD
`9c9e7b7c7cfdf2ef2b0100662513361c1e17a013`, with its current uncommitted diff.

### Current three-file trace

- `unified_radix_cache.py:159-202` defines the durable logger and current
  `residency_release`. The latter is called before `_free_values` at
  `:914-917`, `:922-925`, `:943-946`, and `:968-973`.
- Actual synchronous device/host freeing is centralized through
  `UnifiedRadixCache._free_values`, `_drain_device_frees`, and
  `_drain_host_frees` at `unified_radix_cache.py:879-889,1405-1419`.
- Queued Host staging release is only complete when `_drain_release` or
  `_drain_extra_release` calls the host allocator at
  `unified_radix_cache.py:3961-3988`; queue insertion is
  `HybridCacheController._append_host_mem_release_pages` /
  `append_host_mem_release` at
  `hybrid_cache_controller.py:297-331`.
- Storage submission and ACK/frontier hooks exist at
  `unified_radix_cache.py:2410-2440,3834-3934` and
  `hybrid_cache_controller.py:799-877,920-958`.
- `ExtentFileBackend._write_pages` preserves `plan -> pwrite -> commit` under
  the allocator lock at `extent_file_backend.py:1038-1074`. No index mutation
  occurs on a failed pwrite. `batch_set_v2` returns per-pool/per-key results at
  `:883-963`.
- Current GC and clear observations at
  `extent_file_backend.py:1078-1123` carry no affected storage key and no exact
  generation. The existing Mamba lookup record explicitly says
  `removal_recycle_hook: "not_added"` at `:692-813`.

### Missing ownership boundaries

- `ExtentAllocator.lookup` rejects stale generations at
  `extent_allocator.py:76-85`; `commit` invokes `_drop_slot` on reuse at
  `:153-170`; `_drop_slot` owns the exact affected keys and increments the
  generation at `:197-218`. `clear` owns the complete key removal at `:186-193`.
  The backend cannot reconstruct these facts after they have been discarded.
- `MambaComponent.evict_component` owns the keyed device/host detach and sets
  `cd.value = None` / `cd.host_value = None` at
  `mamba_component.py:321-357`. It has the node and final hash while the later
  allocator free generally has only slot indices.
- Mamba's direct Host allocator free is
  `MambaComponent.free_host_values` at `mamba_component.py:936-940`; its queued
  Host release path is `apply_component_action(FreeComponentHostSlot)` at
  `:959-967`.
- `UnifiedTreeCore.commit_backup` at
  `unified_tree_core.py:2491-2515` commits Host residency only. Radix L3
  publication is a separate ACK-driven state transition. Therefore neither
  Host commit nor radix `storage_persisted` alone proves combined KV+Mamba
  durability.

## Proposed smallest product-scope expansion

### New file 1: exact extent invalidation

`python/sglang/srt/mem_cache/storage/extent/extent_allocator.py`

- Instrument `ExtentAllocator._drop_slot` (`:197-218`) while it still owns
  `self._slot_keys[slot]`. Emit one marker-gated `storage_invalidate` record per
  affected storage key, or a lossless chunked record, with `storage_key`,
  `extent_id`, `old_generation`, `new_generation`, and reason supplied by the
  caller (`commit_reuse` or `lru_gc`). Emit only after the generation increment
  and removals complete.
- Instrument `ExtentAllocator.clear` (`:186-193`) before key ownership is
  discarded and emit the exact removed keys with reason `backend_clear`.
  `clear` does not currently increment generations; the record must state the
  observed generation and `index_removed=true`, not invent a bump.
- Preserve `plan`, `commit`, `lookup`, `verify`, cursor selection, generations,
  LRU order, and return values. Capturing/sorting keys must occur only when the
  diagnostic marker is enabled.

The optional reason parameter may be diagnostic-only and default-compatible, or
the caller may emit a separate cause event. It must not change allocator
selection or invalidation timing.

### New file 2: keyed Mamba detach and actual Mamba free

`python/sglang/srt/mem_cache/unified_cache/components/mamba_component.py`

- Instrument `MambaComponent.evict_component` (`:321-357`) at each actual
  device/host detach. Capture `node_id`, final KV hash/Mamba logical key,
  session IDs if still attached, component=`mamba`, tier, reason/target, slot
  count, and a stable digest of the exact slot indices. Emit
  `residency_detach` only after the component field is set to `None`.
- Instrument `MambaComponent.free_host_values` (`:936-940`) after
  `host_pool_group.free(..., pool=MAMBA)` returns, emitting
  `residency_free_complete` with the same pool and per-page slot digest.
- Instrument the `FreeComponentHostSlot` branch of `apply_component_action`
  (`:959-967`) as `residency_release_enqueued`; completion remains owned by the
  central queue drain described below. This is necessary for prefetch/rejected
  transfer buffers, which are not freed synchronously here.

Do not alter Mamba eviction eligibility, flush-before-evict behavior, LRU
membership, cache actions, or pool APIs.

### Completion hooks in files already in the coder's write set

`python/sglang/srt/mem_cache/unified_radix_cache.py`

- Replace the current pre-free interpretation of `_t38c_residency_log`
  (`:187-202`) with a two-phase contract: `residency_detach` (tree state no
  longer owns slots) and `residency_free_complete` (allocator call returned).
- At `_drain_device_frees` / `_drain_host_frees` (`:1405-1419`), retain
  per-component slot digests before consuming each list and emit completion
  only after the component action/free call returns. This covers KV and Mamba
  GPU/Host frees without adding `full_component.py` to scope.
- At `_drain_release` / `_drain_extra_release` (`:3961-3988`), emit Host
  completion after `free` returns for each drained page/pool. Join enqueue and
  completion using `pool + exact-slot-digest`; do not change queue payloads.
- Emit a derived `residency_barrier` for a target node/session only after every
  detached digest has a completion record, the node snapshot shows no KV or
  Mamba GPU/Host value, and the relevant Host release queues contain no
  outstanding digest for that target. If node deletion makes a post-snapshot
  impossible, require keyed detach records for all four expected arms plus all
  matching completion records; do not infer absence from deletion alone.

`python/sglang/srt/mem_cache/hybrid_cache/hybrid_cache_controller.py`

- Extend `_append_host_mem_release_pages` / `append_host_mem_release`
  (`:297-331`) with marker-gated `residency_release_enqueued` records carrying
  pool and per-page slot digest. Do not wrap or change queue objects.

`python/sglang/srt/mem_cache/storage/extent/extent_file_backend.py`

- Consume allocator invalidation records (or use the allocator logger directly)
  and replace generation-less GC/clear summaries at `:1078-1123` with keyed
  cause summaries. Keep the detailed event's authoritative ownership in the
  allocator.
- Add the same operation/key/generation fields to `batch_exists_v2` query
  records at `:692-813`, so a miss joins to an exact prior invalidation rather
  than merely observing `tested_present=false`.

### Explicitly excluded

- `unified_tree_core.py`, scheduler files, pool allocators, session tracker,
  launchers, and vehicle/parser files are not needed for this product trace
  boundary.
- No fsync, fdatasync, rename, journal, crash-recovery, write ordering, cache
  eligibility, all-state fold, key derivation, or eviction behavior change is
  authorized.
- The word `durable` in this P0 schema means the existing process-lifetime
  contract: successful pwrite/index commit plus ACK/frontier publication. It
  does **not** mean power-loss or process-crash durability.

## Trace schema and invariants

Use schema `p0_durable.v2`. Every event must include:

```text
schema_version, run_id, event_id, evt, ts_wall_ns, ts_mono_ns,
process_id, rank, thread_id, local_seq,
session_id?, session_generation?, build_rid?, warm_rid?,
operation_id?, attempt_id?, node_id?, anchor_id?,
pool?, tier?, final_kv_hash?, storage_key?, mamba_key?,
extent_id?, old_generation?, new_generation?,
slot_count?, slot_digest?, requested_pages?, succeeded_pages?,
result, reason?, predecessor_event_id?, evidence_ref?
```

Requirements:

- `event_id` is unique within `run_id`; `local_seq` is monotonic per emitting
  process/thread. Cross-thread order is established by operation IDs and explicit
  predecessor edges, not wall-clock timestamps alone.
- Keys are hashes/storage identities only; do not log token text, token IDs,
  tensors, state bytes, or raw slot lists. `slot_digest` is a canonical digest of
  pool name, dtype/shape, and exact index values; it is evidence correlation, not
  a cache key.
- If source code does not know `session_id`, the vehicle must join
  `session_id -> build_rid -> final_kv_hash/node_id` and record the join evidence.
  A timestamp-only join is invalid.
- `combined_durable=true` is a derived vehicle fact only when the same expected
  session/node/operation has successful KV and Mamba `batch_set_result`, their
  corresponding extent commits, a complete ACK drain, and a frontier covering
  the target. Radix `storage_persisted` alone must never set it.
- `cold_residency=true` is derived only from completed frees for every detached
  KV+Mamba GPU+Host slot digest. Planned frees, `host_value=None`, queue insertion,
  node deletion, or elapsed time alone are insufficient.
- All-or-nothing acceptance remains `final_pages = min(KV frontier, Mamba
  boundary, other required sidecars)`. No KV-only acceptance is allowed.

## Causal order and exclusive branch classification

The vehicle may issue warm lookup only after both barriers are observed:

```text
expected_state
  -> backup_host_commit
  -> backup_submit(KV + expected Mamba)
  -> batch_set_result/extent_commit(KV and Mamba)
  -> backup_ack_enqueue
  -> backup_ack_drain(complete)
  -> storage_persisted(frontier covers target)
  -> durability_barrier(combined_durable=true)

residency_detach(KV GPU, Mamba GPU, KV Host, Mamba Host as applicable)
  -> residency_release_enqueued (only for queued paths)
  -> residency_free_complete(each exact slot digest)
  -> residency_barrier(cold_residency=true)

durability_barrier + residency_barrier
  -> warm_lookup_start
  -> storage_query(raw_kv_frontier, queried Mamba key/generation)
  -> boundary_fold
  -> restore_outcome
```

`storage_invalidate` may occur after extent commit and before query; it must carry
the exact storage key and generation transition. A fixed settle interval is not
an edge in this graph.

Classify a failed full warm sample by this decision order, yielding exactly one
branch; otherwise use `F_unresolved`:

1. **E_late_write_or_barrier:** warm lookup started before either required
   barrier, or the correct expected KV/Mamba write/ACK/frontier became complete
   only after lookup. This takes precedence over A-D because the experiment did
   not establish the required happens-before relation.
2. **B_write_failure:** an expected Mamba transfer was submitted, and a terminal
   per-key write result was false/partial/exception (or its operation produced a
   terminal failed ACK) before lookup. Absence of an ACK without a terminal
   failure is not B; it is E if late, otherwise F.
3. **A_omitted_transfer:** the finalized backup operation expected Mamba for the
   session but constructed/submitted no Mamba transfer, with direct reason such
   as `host_value_unavailable`. There must be no later submission; otherwise E.
4. **D_recycle_or_remove:** the exact queried Mamba storage key committed and was
   acknowledged before lookup, then a keyed `storage_invalidate` for that key and
   committed generation occurred before lookup (extent reuse, LRU GC, or clear).
5. **C_key_mismatch:** a Mamba write committed/ACKed before lookup, no exact-key
   invalidation explains the miss, and canonical key derivation proves the write
   identity differs from the queried identity. Similar timestamps or suffixes
   are not proof.

This ordering keeps A-E mutually exclusive. Any missing expected-state record,
ambiguous session/hash join, generation-less recycle, unmatched release digest,
or clock-only ordering is `F_unresolved` and P0 FAIL/BLOCKED.

## Disjoint coder write set

Recommended fresh coder dispatch (single atomic product-trace task):

1. `python/sglang/srt/mem_cache/unified_radix_cache.py`
2. `python/sglang/srt/mem_cache/hybrid_cache/hybrid_cache_controller.py`
3. `python/sglang/srt/mem_cache/storage/extent/extent_file_backend.py`
4. `python/sglang/srt/mem_cache/storage/extent/extent_allocator.py` **(new scope)**
5. `python/sglang/srt/mem_cache/unified_cache/components/mamba_component.py` **(new scope)**

No other product or test file belongs to that coder write set. The P0 vehicle and
parser remain a separate executor write set under `3090-dev/`; gate acceptance
remains reviewer-owned. This avoids concurrent writes to the active dirty product
files.

## Acceptance tests and evidence

The implementation is accepted only if all of the following pass:

1. **Static/no-semantic-delta:** `python3 -m py_compile` for all five files and
   `git diff --check`; review confirms marker-off paths preserve return values,
   queue payload types, lock boundaries, allocator generation changes, LRU
   ordering, and cache actions. No fsync-family call is added.
2. **Allocator keyed recycle:** extend or externally instrument the cases in
   `test/registered/unit/mem_cache/test_extent_file_backend_unit.py`, especially
   generation reuse (`:93-125`) and clear (`:179-193,452-460`). Assert exact old
   key, extent, old/new generation, reason, and event-before-subsequent-miss.
3. **Write failure:** force `_pwritev` failure and invalid Mamba host geometry.
   Assert no extent commit/index mutation, `batch_set_result=false`, no combined
   durability barrier, and branch B only when the operation reaches a terminal
   failure.
4. **Mamba detach/free:** use the existing Mamba path-state fixtures in
   `test/registered/unit/mem_cache/test_mamba_path_state_cap.py`. Assert keyed
   detach after `host_value=None`, completion only after the pool free returns,
   matching slot digests, and unchanged eviction outcome with tracing off/on.
5. **Queued Host release:** enqueue KV and Mamba pages, drain them, and assert
   enqueue precedes matching completion; a barrier with one undrained digest
   must fail.
6. **Classifier fixtures:** one deterministic trace fixture for each A-E plus
   ambiguous F. Assert exclusivity, E precedence for lookup-before-barrier, D
   requires exact key+generation, and timestamp-only evidence yields F.
7. **Focused runtime gate:** only after 1-6 pass, run one frozen S=25 RH-off
   vehicle. Every eligible session must show combined KV+Mamba durability and
   cold GPU/Host residency barriers before warm. `s00002` must be exactly A-E;
   no F, no fixed-sleep PASS, no KV-only full restore, and no health failure.

Tests 2-6 may be written by a separately authorized test/vehicle owner; adding
test files is not implicitly authorized by this architecture task or the proposed
five-file coder write set.

## Risks, trade-offs, and reversibility

- **Trace volume:** exact keyed clear/recycle can be large. Marker gating and
  lossless chunking bound normal-operation cost; dropping/sampling events is not
  acceptable for P0 proof.
- **Ordering:** independent file writes and wall clocks do not define causality.
  Operation IDs, local sequence, and slot/key digests are mandatory. This is
  reversible diagnostic metadata.
- **Identity lifetime:** node IDs can disappear before frees complete. Capture
  node/hash/session associations at detach and join later allocator completion by
  digest; do not broaden queue contracts.
- **False durability:** extent ACK remains successful pwrite plus in-memory index
  registration. The report and parser must call this process-lifetime durability,
  not crash durability. This preserves the existing no-fsync contract.
- **Dirty worktree:** the three existing files contain earlier semantic and
  diagnostic changes. The coder must layer only the approved trace delta and
  provide a scoped diff; no reset or cleanup of user changes is authorized.
- **Reversibility:** all proposed changes are marker-gated logging/correlation and
  can be removed without migration or stored-data format changes. Schema v2 is
  additive and the vehicle should reject v1 for strict P0 rather than silently
  degrading.

## Artifacts and followups

Artifact: this report only. No product, plan, ledger, context, test, vehicle,
remote, or repository state was changed.

Followups for the orchestrator:

1. Accept or reject the five-file product trace boundary.
2. If accepted, issue a fresh coder Task ID with the exact write set above and
   require a scoped change manifest.
3. Keep P0 strict vehicle/reviewer nodes blocked until implementation and focused
   tests pass; then redispatch the vehicle/parser under its disjoint write set.

## Open issues

- The source does not universally retain `session_id` through storage and free
  completion. The vehicle must provide an exact build-rid/hash/node join unless a
  future dispatch explicitly authorizes propagating session identity. This does
  not require widening the minimum product scope now.
- If Mamba Host indices can span multiple pool pages in the target configuration,
  detach and queue events must use identical per-page canonicalization; otherwise
  release completion remains `F_unresolved`.
- The active opt diff contains pre-existing semantic fixes in the same three
  files. Independent review must distinguish those changes from this proposed
  instrumentation before accepting the P0 trace vehicle.
