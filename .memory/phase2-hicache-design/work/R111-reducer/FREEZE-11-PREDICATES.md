# P0-B frozen canonical oracle — exactly 11 predicates (R111 re-freeze)

- task_id: `P0-B-ORACLE-REFREEZE-20260911-R111`
- supersedes: `P0-B-REDUCER-FREEZE-20260911-R107` (kept frozen as history)
- role: coder
- epoch: 2026-09-11
- re-freeze authority: `../P0-B-GAP-CLASSIFY-20260911-R110.md` §1-2 (predicates
  6 and 8 contradicted real product emission), plus the original authoritative
  inputs R54, R79, R98/R100, R101, R106b.
- reducer: `p0b_reducer.py` (`ORACLE_NAMES`, `oracle_names()`).

This R111 re-freeze changes **only** predicate 6 (`generation_transition`) and
predicate 8 (`attempt_lineage`), plus the `negative_safety` `repeated_retry`
scoping that depends on 8.  The predicate count and names are unchanged; no
product source was modified.  Both changes replace an oracle predicate that was
provably unsatisfiable against real emission with one that measures the same
intended product semantics using the producer-owned, non-forgeable fields.

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
equals the accepted finalization's `wake_event_id`.  The producer-owned
generation counters are the **authoritative** signal: the park's
`captured_generations` and the grant's `current_generations` (both from
`host_allocability_snapshot`, `unified_radix_cache.py:3838-3882`).  The park
and grant must carry the same int `cache_instance_id`, and the park `ordinal`
must strictly precede the grant `ordinal`.  For every blocked-domain pool,
`current_generations[pool] > captured_generations[pool]` (strictly advanced),
with both counters present ints.

`host_allocability_change` records are **deliberately sampled** by the
producer (`unified_radix_cache.py:155-164`: first 16 mutations per telemetry
key, then every 128th, max 64 per key and 256 per cache instance; emission
gate at `unified_radix_cache.py:3784-3793`).  They are therefore
**corroborating, never required**.  For each blocked pool, the records with
that `pool` in `(park.ordinal, grant.ordinal]` are inspected:

* absence of such edges does **not** fail (the counters prove the advance);
  the predicate output records `sampled_edges_seen[pool]` and the `sampling`
  fact explicitly;
* a present edge must not contradict: same `cache_instance_id` as the cursor,
  `generation_after == generation_before + 1`, and
  `captured <= generation_before < generation_after <= current`.

Join by cache instance + pool + generation + ordinal, never timestamp.
Fail-closed: missing park/grant, non-int or missing `cache_instance_id`,
park/grant instance mismatch, park not strictly before grant, missing counter
fields, non-advancing counters, or any contradictory sampled edge.

Why the R107 text was unsatisfiable: it demanded an exact *contiguous* chain
of emitted edges from captured to current, but the sampler bounded emission
independently of the (complete) generation sequence.  In the real R109 chain
the deciding park captured mamba=89 and the grant carried mamba=105 with
**zero** in-window mamba edges (the last emitted mamba edge was 48->49 at
`raw.log:1012`, 53 lines before the park at `raw.log:1065`); 58 of 167
mutations were emitted, 109 suppressed (`../P0-B-GAP-CLASSIFY-20260911-R110.md`
§2.2).  The re-frozen text still fails any non-advance, instance mismatch, or
contradictory present edge, so the anti-forgery strength is preserved.

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
The non-forgeable lineage join is the producer-emitted `wake_event_id`: the
single accepted `restore_hybrid_finalize` and the single target `ready_host`
must both carry a `wake_event_id` naming the **same** captured target grant
(the *deciding grant*).  The finalize/READY `attempt_id`s must be present and
in their real producer namespaces — finalize/HOST_ALLOC retry build
`f"{rid}:{seq}"` (`unified_radix_cache.py:5717-5737`,
`scheduler.py:4251-4254`) while READY carries `f"{rid}:prefetch:{seq}"`
(`scheduler.py:3130-3139,4399-4457`) — so they are **not** required to be
equal (they are different namespaces).

`restore_host_alloc_retry_result` is emitted **only on allocation failure**
(`unified_radix_cache.py:5460` forfeited_alloc_failed,
`unified_radix_cache.py:6575-6598` revoked_alloc_failed).  Every park is
caused by exactly one **pre-wake** failure with `attempt_id=null`,
`retry_grant=false` and no `wake_event_id`, and it precedes the deciding
grant.  At most one **post-wake** retry (`retry_grant=true` or non-empty
`attempt_id`) is tolerated; when present it must carry a non-empty
host-alloc-namespace `attempt_id`, a recognized `retry_outcome`
(`revoked_alloc_failed` or `forfeited_alloc_failed`), and a `wake_event_id`
naming a captured grant that strictly precedes it.  If a later park exists
after the post-wake retry, that park must preserve the retry `attempt_id`.

Fail-closed: missing/duplicated pre-wake retry, a pre-wake retry carrying a
`wake_event_id` or a non-failure outcome, more than one post-wake retry, a
post-wake retry with a missing/mis-namespaced `attempt_id`, a post-wake retry
whose `wake_event_id` does not name a captured preceding grant, a later park
that loses the retry `attempt_id`, a finalize/READY `attempt_id` outside its
namespace, or a finalize/READY `wake_event_id` that does not name the deciding
grant.

Why the R107 text was unsatisfiable: it demanded exactly one retry_result with
a non-empty `attempt_id` and a grant `wake_event_id`.  Real emission pairs
every park with the mandatory pre-wake failure (`attempt_id=null`,
`wake_event_id=null`; real R109 `raw.log:1063`), so the count is never exactly
one post-wake retry on a success-first-try chain, and on a post-wake-failure
chain it becomes two (`../P0-B-GAP-CLASSIFY-20260911-R110.md` §2.4).  The
re-frozen text keeps the strong join: both finalize and READY must name the
same captured deciding grant, and a bogus/forward-naming post-wake retry
still fails.

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
- repeated retry: more than one **post-wake** `restore_host_alloc_retry_result`
  (`retry_grant=true` or non-empty `attempt_id`); the mandatory pre-wake
  failure with `attempt_id=null` is the park's cause, not a repeat;
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
