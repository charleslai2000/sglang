# P0-B frozen canonical oracle — exactly 11 predicates

- task_id: `P0-B-REDUCER-FREEZE-20260911-R107`
- role: coder
- epoch: 2026-09-11
- authoritative inputs: R54 mandatory legs, R79 execution packet, R98/R100
  independent reviews, R101 event contract, R106b lineage report.
- reducer: `p0b_reducer.py` (`ORACLE_NAMES`, `oracle_names()`).

This file freezes the oracle against the **real emitted event names and
fields** of the checked-out producer (branch `3060-12g-qwen35-4b`, HEAD
`4f41f5bab5`).  `raw_provenance` is an **input gate** verified before
reduction, not a predicate; `negative_safety` is predicate 11.  There are
exactly eleven predicate names and no others.

## Input families (real envelopes only)

1. `[HAE] {json}` with `schema == "host_alloc.v1"` and `evt` one of:
   - `restore_host_alloc_wait` — `scheduler.py:3844`
   - `restore_host_alloc_wake_decision` — grant `scheduler.py:3985`,
     release terminal `scheduler.py:3661`, hold `scheduler.py:4183`
   - `restore_host_alloc_retry_result` — `unified_radix_cache.py:5460`
     (`forfeited_alloc_failed`) and `unified_radix_cache.py:6576`
     (`revoked_alloc_failed`)
   - `restore_hybrid_finalize` — `unified_radix_cache.py:5683` (discarded) and
     `unified_radix_cache.py:5718` (accepted)
   - `host_allocability_change` — `unified_radix_cache.py:3798`
2. `[P3] ts_ns=... evt=ready_host schema=rh_ready_host.v1 ...` —
   `scheduler.py:4409`.
3. `p0_durable` JSONL (`"trace": "p0_durable"`) written by
   `_t38c_durable_log` (`unified_radix_cache.py:356`); the positive artifact
   is `evt=durability_barrier` (`unified_radix_cache.py:7104`).

Every consumed record keeps its absolute raw `file:line` reference.  Joins use
exact keys and ordinals only; timestamps (`ts_*`, `*_mono_ns`) are **never**
used for ordering or backfill.

## Producer identity (R106b)

`process_id`, `run_id`, `profile_id`, `source_build` come from
`telemetry_context.producer_context`.  For `[HAE]` and READY they are
top-level fields; for `p0_durable` they live under the nested `producer`
mapping (`attach_trace_context`, `trace_context.py:96`).  `lifecycle_key` is
``f"{rid}:{session_generation}"`` (`telemetry_context.py:98`).

## Input gate — `raw_provenance` (NOT a predicate)

Verified before reduction; any failure ⇒ overall `NOT_VERIFIED` with reason
`raw_provenance_gate_failed: ...` and all eleven predicates reported false:

- manifest is a JSON object with `format == "p0b.raw-bundle.v3"`;
- no caller-authored summary/verdict key anywhere in the manifest
  (`oracle`, `verdict`, `status`, `summary`, `positive_hit`, `accepted`, …);
- `runtime` carries positive-int `process_id` and non-empty `run_id`,
  `profile_id`, `source_build`;
- `target` carries non-empty `rid` and `lifecycle_key`;
- `raw_files` binds every consumed raw file by absolute path and SHA256, all
  listed files exist and hash-match;
- `source_files` is a non-empty absolute-path SHA256 map and hash-matches;
- no consumer record carries a caller-authored summary key;
- at least one product record is consumed.

## Field semantics and fail-closed rules per predicate

### 1. `provenance`
Manifest/source/PID binding present and consistent: format, complete `runtime`
identity, non-empty `raw_files`/`source_files`, `target.rid` and
`target.lifecycle_key`, and at least one consumed record.  Missing ⇒ fail.

### 2. `singular_identity`
Every target-scoped record (any `[HAE]`/READY with `rid == target.rid`, plus
target-scoped durability records whose `session_generation` equals the
generation parsed from `target.lifecycle_key`) must carry a non-empty
`lifecycle_key`, `run_id` and `process_id`, and there must be exactly **one**
distinct `(process_id, run_id, lifecycle_key)` tuple, equal to the manifest
target key.  A referenced predecessor release may belong to a different
request lifecycle; it is bound only through predicate 7 and is never merged
into the target tuple.  More than one target tuple, or a mismatch, ⇒ fail.

### 3. `pid_profile_source_binding`
For **every** consumed record, the producer-emitted `process_id`, `run_id`,
`profile_id`, `source_build` (top-level, or nested `producer` for
`p0_durable`) must be present and exactly equal the manifest `runtime`.  Any
missing field or inequality ⇒ fail.  No substitution, no partial match.

### 4. `positive_full_hit`
A target-scoped `p0_durable` `durability_barrier` record with
`kv_durable is true`, `mamba_durable is true`, positive
`kv_completed_tokens == kv_requested_tokens`, positive
`mamba_expected_pages == mamba_succeeded_pages`, and a complete trace context
(`session_id`, `build_rid`, `session_generation`, `node_id`, `final_kv_hash`);
**and** a target `restore_host_alloc_wait` with
`positive_hit_tokens >= requested_primary_tokens > 0`.  Absent either ⇒ fail.

### 5. `host_alloc_park`
At least one target `restore_host_alloc_wait` with `state == "WAIT_CAPACITY"`,
`reason == "HOST_ALLOC"`, non-empty `wait_id`, non-empty int-valued
`captured_generations`, non-empty `blocked_domains`, int `fifo_sequence >= 0`,
and positive `requested_primary_tokens`.  No valid park ⇒ fail.

### 6. `generation_transition`
The *deciding park* is the valid park whose `fifo_sequence` equals the
deciding grant's.  The *deciding grant* is the unique grant whose `event_id`
equals the accepted finalization's `wake_event_id`.  For every blocked-domain
pool, `current_generations[pool] > captured_generations[pool]`, and the
`host_allocability_change` records with the same `cache_instance_id` + `pool`
inside `(park.ordinal, grant.ordinal]` form an exact contiguous chain from
`captured` to `current` (`generation_after == generation_before + 1`, next
`generation_before == previous generation_after`).  Join by cache instance +
pool + generation + ordinal, never timestamp.  Any gap, wrong instance/pool,
or non-advance ⇒ fail.

### 7. `fifo_predecessor`
The deciding grant must carry `predecessor_lineage_reason is null` and
non-empty `predecessor_wait_id`, `predecessor_terminal_event_id`,
`predecessor_terminal_state`; the terminal state must be one of the producer
released states `RELEASED, TIMEOUT, RESTORED, MISS, ABORTED, RECOMPUTE,
ABANDONED`; and a consumed `restore_host_alloc_wake_decision` with
`decision == "release"`, `event_id == predecessor_terminal_event_id`,
`wait_id == predecessor_wait_id`, `terminal_event_id == event_id`,
`terminal_state == predecessor_terminal_state` must exist **strictly before**
(lower ordinal than) the grant.

Fail-closed reasons that fail the predicate with their exact spelling:
`no_wait_cursor`, `no_released_predecessor`, `predecessor_terminal_incomplete`,
`predecessor_terminal_state_unrecognized`.  Any other (unrecognized) reason
string also fails closed as `unrecognized predecessor lineage reason: ...`.
No predecessor fact is ever inferred from the payload or timestamps.

### 8. `attempt_lineage`
Exactly one target `restore_host_alloc_retry_result`, with non-empty
`attempt_id`, a recognized `retry_outcome` (`revoked_alloc_failed` or
`forfeited_alloc_failed`), and a `wake_event_id` that names a captured target
grant; that same retry `attempt_id` is preserved into a later target park; the
accepted finalization carries a non-empty `attempt_id` and
`wake_event_id == deciding grant.event_id`; and the single READY carries the
deciding `wake_event_id`.  Missing/duplicated retry, broken wake propagation,
or a lost attempt id ⇒ fail.

### 9. `accepted_finalization`
Exactly one target `restore_hybrid_finalize` with `result == "accepted"`,
`all_or_nothing is true`, `restore_state_after == "READY"`, positive
`kv_expected == kv_fetched`, non-empty `attempt_id` and `wake_event_id`, and
every entry of `sidecars` a mapping with `expected == fetched` (at least one
positive).  Incomplete KV, any partial sidecar, a discarded/rejected result,
or `all_or_nothing != true` ⇒ fail.

### 10. `ready_after_finalize`
Exactly one target `ready_host` record, strictly after the accepted
finalization, with the target `lifecycle_key`, `finalize_result == "accepted"`,
positive `completed_kv_tokens == finalize.kv_fetched`, the same
`wake_event_id` as the finalization, a non-empty `attempt_id`, and
`required_aux_pools`/`completed_aux_units` matching the finalization sidecars.
READY at or before the finalization, a different lifecycle, or an aux
mismatch ⇒ fail.

### 11. `negative_safety`
Fails if any of the following is observed anywhere in the consumed target
contract:

- `genuine_miss=true` on any record, or a retry_result whose `genuine_miss` is
  not exactly `false`;
- `crop_attempted=true`, or a retry_result whose `crop_attempted` is not
  `false` (no crop);
- `lower_checkpoint_queried=true`, or a retry_result whose
  `lower_checkpoint_queried` is not `false` (no lower-frontier substitution);
- same-generation self-wake: any grant whose `current_generations[pool]` is
  not strictly greater than its `captured_generations[pool]` for a blocked
  pool;
- repeated retry: more than one `restore_host_alloc_retry_result`;
- skipped eligible predecessor: a grant carrying a fail-closed
  `predecessor_lineage_reason` while a released waiter with a strictly lower
  `fifo_sequence` and lower ordinal (and compatible blocked domains) exists;
- partial sidecar: a finalization whose `sidecars` are not all
  `expected == fetched`;
- discarded hybrid: a finalization with `result == "discarded"` or
  `restore_state_after == "NONE"`;
- recompute fallback: a retry with `terminal`/`retry_outcome` naming
  recompute (or a `miss` outcome), or a finalization without an accepted READY
  landing;
- READY before finalization (or READY without an accepted finalization).

## Overall verdict

`VERIFIED` **iff** all eleven predicates pass and the `raw_provenance` input
gate passes.  Otherwise `NOT_VERIFIED` with the per-predicate reasons.  A
bundle's own `oracle`/`verdict`/`status`/summary fields are rejected and never
consulted.
