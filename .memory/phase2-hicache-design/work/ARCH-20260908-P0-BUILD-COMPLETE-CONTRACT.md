ENTRY: ACCEPT

# P0 durable V3 `build_complete` gate contract

- Task ID: `ARCH-20260908-P0-BUILD-COMPLETE-CONTRACT`
- Orchestration epoch: `2026-09-08`
- Role: `architect`
- Invocation status: `done`
- Decision owner: orchestrator. This memo is architectural evidence and a recommendation, not implementation authority or gate acceptance.
- Scope performed: read-only inspection of the accepted local product worktree, vehicle, scheduler/session path, accepted V4.3 session-retirement V2 gate, and designated frozen reports. The only write is this memo. No product, launcher, vehicle, ledger, or remote host was modified.

## Summary recommendation

Add one marker-gated, product-authored `p0_durable.v3` event at the successful radix build-finalization boundary in `UnifiedRadixCache.cache_finished_req`. The event establishes the immutable logical build identity before any accepted KV/Mamba durability evidence can be reduced. It does not claim durability, residency, HTTP completion, or all-rank completion.

The product event must use the existing V4.3 trace context and existing durable logger. It must not extend `trace_context.py`, change cache/session semantics, synthesize a generation, or create a V2 compatibility event. The launcher has a separate mandatory responsibility: enable the existing scheduler feature with `--enable-session-radix-cache`, provide the existing marker/run configuration, and otherwise leave identity production to product code.

Recommended minimal product write set for a fresh coder Task ID:

- `python/sglang/srt/mem_cache/unified_radix_cache.py`: one narrow helper or inline emission plus a call at the boundary specified below.
- `3090-dev/test_p0_trace_context_v4.py`: focused contract fixtures only, if the orchestrator authorizes test scope.

No change is recommended to the vehicle, `trace_context.py`, scheduler, session tracker, Hybrid controller, extent backend, Mamba component, tree core, allocator, or launcher in the product task. The launcher correction is a separate devops/config task.

## Observed facts

1. The accepted narrow V4.3 session-retirement gate is `review/gates/P0-TRACE-CONTEXT-V4.3-SESSION-RETIRE-V2.md`. It accepts the null-safe, attempt-isolated retirement patch while explicitly leaving live P0 runtime acceptance blocked.
2. `trace_context.py` defines `TRACE_SCHEMA = "p0_durable.v3"`. `make_trace_context` returns no context unless the marker exists and `session_id`, scheduler-owned `session_generation`, and `build_rid` are all available. `attach_trace_context` promotes a record to V3 only when context is present.
3. In `Scheduler.handle_generate_request`, a top-level `session_id` receives `req.session_generation` only in the radix-native branch guarded by `enable_session_radix_cache`. The R3 evidence confirms that the live launcher omitted this enablement, producing contextless V2 records.
4. For the vehicle's top-level `session_id` request shape, the request follows the radix-native/normal request path, not `StreamingSession.try_cache_finished_req`.
5. `UnifiedRadixCache.cache_finished_req` prepares all components, performs the radix insert, receives `result.last_device_node`, assigns `req.last_node`, and calls `_t38c_record_node_context(req, result.last_device_node)`. The tree insert commit has already attached component data, including Mamba data, to the target node before the result is returned.
6. The accepted V4.3 durability path stores attempt-keyed evidence and emits `storage_persisted` and `durability_barrier` only during scheduler-side backup ACK drain and frontier promotion. The combined barrier already requires complete V3 context plus KV and all-rank Mamba durability evidence.
7. The vehicle accepts only exact schema `p0_durable.v3`; it requires non-empty string fields `(session_id, build_rid, node_id, final_kv_hash)`, rejects a build RID that differs from the response ID, and requires one exact identity tuple in the final row. It does not accept V2 as evidence.
8. The vehicle obtains `build_rid` from the OpenAI-compatible response `id`. Product request state already carries the same request identifier as `req.rid`; the V4.3 context uses `req.rid` as the first build RID and preserves that value for later warm requests in the same session generation.
9. No live product `build_complete` emitter exists. `Reducer.record_build_complete` is a vehicle helper/fixture surface and has no live invocation; using it in live mode would make the consumer manufacture its own producer evidence.

## Proposed authoritative producer boundary

### Ownership

`UnifiedRadixCache` owns the smallest authoritative boundary because it is the first existing component that simultaneously has:

- the scheduler-issued request identity and generation;
- the finalized radix target node;
- the target node's final KV hash after tree/component commit; and
- the V4.3 node-context binding used by later storage and residency events.

The scheduler is too early: it does not yet own the final node/hash. The HTTP/launcher/vehicle layers are too far outside the cache commit and cannot prove which radix node was built. The storage ACK path is too late and would conflate build identity with durability.

### Exact emission point

For the vehicle's radix-native request path, emit immediately after all of the following have succeeded in `cache_finished_req`:

1. `insert(insert_params)` returned a non-null `InsertResult`;
2. `result.last_device_node` is non-null;
3. `req.last_node` was set to that returned node;
4. `_t38c_record_node_context(req, result.last_device_node)` completed; and
5. a readback of the node-bound context matches the request's full V3 build context.

Emit before component request cleanup, session-ref registration, return from `cache_finished_req`, and any later scheduler `check_hicache_events` ACK drain.

The readback condition is essential. `_t38c_record_node_context` can encounter an already-bound node; an event must not assert a new build identity unless the node sidecar actually resolves to exactly the same `(session_id, session_generation, build_rid)`. Ambiguous or conflicting binding produces no `build_complete` and therefore fails the vehicle closed.

The event is eligible only when all conditions below hold:

- diagnostic marker is on;
- `is_insert` is true;
- the request completed without `FINISH_ABORT`;
- `context = _t38c_trace_context_for_req(req)` is a complete dictionary;
- `str(req.rid) == context["build_rid"]`; this excludes warm requests whose request RID differs from the preserved build RID;
- the finalized target node exists and is not the root;
- `node.get_last_hash_value()` is a non-empty string; and
- node-context readback equals the request context for session, generation, and build RID.

No event is emitted from `cache_unfinished_req`, prefix match, storage submit/ACK, HTTP response handling, streaming-session early-return handling, abort handling, or warm lookup.

### Meaning

`build_complete` means only:

> This request's cacheable, page-aligned build state has successfully committed to this finalized radix node, and the existing immutable V3 trace context is bound to that node.

It does not mean:

- the HTTP response has been fully consumed by the client;
- GPU or Host residency has been released;
- KV or Mamba storage writes have completed;
- the storage frontier has advanced;
- every TP rank has completed the build; or
- the state is crash/power-loss durable.

Those claims remain owned by the existing response evidence, residency barrier, rank-aware Mamba ACK proof, and combined durability barrier respectively.

## Exact event contract

The logical event is:

```json
{
  "schema_version": "p0_durable.v3",
  "evt": "build_complete",
  "run_id": "<existing T38C_RUN_ID>",
  "event_id": "<existing logger-generated unique id>",
  "session_id": "<top-level request session_id>",
  "session_generation": 1,
  "build_rid": "<req.rid; equal to response.id>",
  "warm_rid": null,
  "node_id": "<str(result.last_device_node)>",
  "final_kv_hash": "<target node last hash>",
  "operation_id": null,
  "attempt_id": null,
  "result": true,
  "rank": "<existing logger rank>",
  "process_id": 123,
  "thread_id": 456,
  "local_seq": 7,
  "ts_wall_ns": 0,
  "ts_mono_ns": 0
}
```

Required semantic fields are:

| Field | Contract |
|---|---|
| `schema_version` | Exactly `p0_durable.v3`; never V2. |
| `evt` | Exactly `build_complete`. |
| `run_id` | Existing durable logger run ID; mandatory and non-empty. |
| `event_id` | Existing logger uniqueness contract; every physical record has a unique ID. |
| `session_id` | Non-empty string from the request's V4.3 context. |
| `session_generation` | Non-null scheduler-owned integer; never launcher/client synthesized. |
| `build_rid` | Non-empty string from `req.rid`; must equal the client-observed response `id`. |
| `warm_rid` | Null on this event. A differing request RID denotes a warm request and is ineligible. |
| `node_id` | String form of the finalized radix node ID, not a hostname, worker ID, or storage extent. |
| `final_kv_hash` | Non-empty final hash read from that exact finalized node after insert commit. |
| `operation_id`, `attempt_id` | Null. A build identity is not a storage-write attempt. |
| `result` | Boolean `true`. Failures/aborts produce absence, not a successful-looking event with `false`. |
| logger envelope | Existing `rank`, process/thread IDs, sequence, and timestamps are retained unchanged. |

The emitter should pass the existing V4.3 context through `trace_context` to `_t38c_durable_log` and let `attach_trace_context` author the top-level V3 fields. It must not manually fork a second V3 envelope implementation.

No raw tokens, token IDs, prompts, state bytes, slot lists, or new cache keys are allowed.

## Identity and causal invariants

For each accepted logical build key

```text
B = (run_id, session_id, session_generation, build_rid,
     node_id, final_kv_hash)
```

the required arrival/causal order is:

```text
radix/component insert commit
  -> node V3 context bind
  -> build_complete(B)
  -> accepted KV evidence(B, kv_durable=true)
  -> accepted Mamba evidence(B, mamba_durable=true)
  -> durability_barrier(B, combined_durable=true)
  -> residency_barrier(B, cold_residency=true)
  -> vehicle warm request / warm_lookup_start(B)
```

KV and Mamba evidence may occur in either order, but both must arrive after `build_complete` and before `durability_barrier`. Existing `backup_submit`, per-key writes, or ACK enqueue operations may begin before `build_complete`; they are attempt evidence and do not establish vehicle readiness. The accepted durable events and barrier are scheduler ACK-drain/frontier products and must follow the build event in the same engine execution.

Every scoped event used for this build must repeat exactly the same vehicle identity tuple `(session_id, build_rid, node_id, final_kv_hash)`. Ancestor-node events, a different final hash, or another build RID are not evidence for `B`; they must remain separate identities. This preserves the vehicle's final `identity_count == 1` gate and prevents an ancestor barrier from satisfying a final-leaf build.

`session_generation` is mandatory product evidence even though the current vehicle's four-field join does not include it. It prevents a reopened session from inheriting an older build tuple and preserves the accepted V4.3 lifecycle boundary. A future vehicle may strengthen its join to include the generation, but this task must not modify the vehicle.

## Build RID source and availability

- Product source of truth: `req.rid` already present when `cache_finished_req` runs.
- Independent client cross-check: OpenAI-compatible response `id`, already recorded by the vehicle as `build_rid_source=response.id`.
- Equality rule: the product event and response must carry the same non-empty string. A mismatch is `NOT_VERIFIED`/invalid join; neither side overrides the other.
- First-build rule: the event is emitted only when the request RID equals the context's preserved `build_rid`. Later requests in the same `(session_id, session_generation)` have a different RID and are warm requests; they do not emit another build event.
- Availability failure: missing RID, missing scheduler generation, missing target node/hash, or failed context binding results in no V3 `build_complete`. The producer must not guess, delay-join by timestamp, use an operation ID, or accept a response header substitute.

## Rank and node semantics

`build_complete` is one logical request/cache-node identity, not durability consensus. To avoid making replicated TP execution look like independent builds, the recommended publication rule is:

- exactly the canonical TP-group leader (`torch.distributed.get_rank(group=self.tp_group) == 0`) publishes the logical build event;
- in TP=1, that sole rank publishes it;
- in multi-node TP, group rank 0 remains the publisher even if its global rank is not zero;
- DP groups publish only for requests routed to that group; `run_id + session_id + session_generation + build_rid` separates routed builds;
- `node_id` remains the logical radix node ID. It must never be replaced with host/node topology identity.

This requires no new collective and does not claim all-rank completion. The existing V4.3 durability barrier remains responsible for checking the authoritative expected rank set and all-rank Mamba ACKs. If the implementation cannot determine TP-group leadership through the already initialized group, it must emit no logical build event in multi-rank mode and fail closed; it must not fall back to global rank 0 or `range(world_size)`.

If the orchestrator instead chooses all-rank replicated publication, it must first require evidence that every rank produces the identical node/hash tuple and update tests/evidence to deduplicate those replicas. Leader-only publication is smaller and avoids expanding the current vehicle contract.

## Duplicate, retry, and attempt behavior

- A physical log retry or accidental repeated call may produce multiple records only if all fields in `B` are identical and each record has a distinct `event_id`. Such duplicates are semantically idempotent and count as one logical build.
- A duplicate with a different build RID, generation, node ID, or final hash is a conflicting build identity and must invalidate the session; it is never last-write-wins.
- The producer does not need persistent deduplication state. The authoritative lifecycle call should normally execute once, and the consumer/evidence analyzer groups exact duplicates by `B`. Adding mutable dedup state would create new retirement/reset obligations for no gate benefit.
- Storage retries keep their existing `operation_id`/`attempt_id` behavior. They do not cause another `build_complete`, and no storage attempt may substitute for a missing build event.
- Engine restart/relaunch requires a fresh `run_id`; records from another run are rejected by the vehicle.
- Session reopen requires a new scheduler generation. An old-generation event cannot establish the new build even if session ID, node, or hash repeats.

## Marker-off and incomplete-context behavior

With `/tmp/t38c-durable-trace` absent:

- no `build_complete` record is emitted;
- no extra trace context, node sidecar, dedup set, or lifecycle state is created for this event;
- cache insertion, component cleanup, session references, allocator behavior, and return values are unchanged; and
- no V2 `build_complete` compatibility record is emitted.

With the marker present but any required identity unavailable, the result is the same fail-closed absence of `build_complete`. Existing contextless events may retain their current V2 fallback for diagnostics, but the vehicle must reject them and they cannot advance readiness.

Marker toggling does not retroactively emit a build event for an already completed request. A valid run must enable the marker before engine/request execution.

## Launcher configuration versus product code

| Responsibility | Launcher/devops config | Product code |
|---|---:|---:|
| Add `--enable-session-radix-cache` | Required | Must only consume resulting scheduler generation. |
| Create the existing trace marker before requests | Required | Check through existing `durable_trace_enabled()`. |
| Set a fresh non-empty `T38C_RUN_ID` and preserve the configured event file | Required | Use existing logger envelope/path behavior. |
| Keep frozen RH-off/S=25/other workload settings | Required | No semantic change. |
| Generate `session_generation` | Forbidden | Scheduler/session-ref owner only. |
| Generate or rewrite `build_rid` | Forbidden | Read `req.rid`; vehicle independently checks response `id`. |
| Emit/inject/synthesize `build_complete` | Forbidden | Required at the finalized radix boundary. |
| Convert V2 records to V3 or accept V2 | Forbidden | Forbidden; V3 only when complete context exists. |
| Change KV/Mamba fold, durability, residency, or barriers | Forbidden | Forbidden in this task; preserve accepted V4.3 behavior. |

The launcher flag is a necessary activation precondition, not evidence that the product event exists. Conversely, adding the product emitter cannot compensate for a launcher that leaves session radix caching disabled.

## Test and evidence schema

### Focused product fixtures

Under a fresh implementation Task ID, require deterministic tests for:

1. Valid TP=1 build: one logical V3 event with exact context, `req.rid`, finalized node ID/hash, null operation/attempt, and `result=true`.
2. Ordering: captured event occurs after insert/component commit and node-context bind, and before a simulated accepted `storage_persisted`, Mamba durable event, and `durability_barrier`.
3. Warm exclusion: a later request in the same generation whose RID differs from preserved `build_rid` emits no build event.
4. Fail-closed fields: independently remove session ID, generation, RID, insert result, target node, final hash, and matching node-context readback; each case emits no V3 build event.
5. Marker off: zero event and no new build-event state or cache behavior change.
6. Abort/non-insert/unfinished paths: zero event.
7. Rank publication: TP=1 leader emits; TP>1 group rank 0 emits; non-leader does not. No global-rank fallback.
8. Duplicate reduction: exact duplicate `B` is idempotent; any changed identity field fails the session.
9. Session reopen: same session ID with a new scheduler generation is a distinct build and cannot inherit the prior context.
10. Vehicle fixture: V2 `build_complete`, missing generation at product evidence, wrong response ID, barrier before build, ancestor-node barrier, and identity conflicts all remain non-PASS.

Use the existing dependency-free focused fixture style plus `py_compile`, AST parse, and `git diff --check`. Runtime pytest coverage is additional evidence when its dependencies are available; absence of pytest does not turn a failed focused fixture into acceptance.

### Live P0 evidence requirements

The corrected fresh S=25 RH-off run must preserve the existing evidence bundle and add/check these fields per session:

```text
session_id
session_generation
response_build_rid
response_build_rid_source
build_event_ids[]
build_logical_identity
build_publisher_rank
build_order
first_kv_durable_order
first_mamba_durable_order
durability_barrier_order
residency_barrier_order
warm_order
identity_count
exact_duplicate_count
conflicting_duplicate_count
```

Acceptance evidence for each of 25 sessions requires:

- exactly one logical build identity after exact-duplicate grouping;
- product `build_rid == response.id`;
- non-null scheduler generation;
- canonical TP leader publication;
- the exact same `(session_id, build_rid, node_id, final_kv_hash)` on every accepted build/KV/Mamba/barrier event;
- `build_order < kv_order < durability_barrier_order` and `build_order < mamba_order < durability_barrier_order`;
- `durability_barrier_order < residency_barrier_order < warm_order`;
- zero V2 records used as evidence, zero conflicting duplicates, and zero ancestor/final-node cross-join;
- the existing frozen restore, health, branch-classification, cleanup, and 25/25 requirements remain satisfied.

Raw trace evidence must retain `event_id`, rank, local sequence, monotonic/wall timestamps, and response/build rows. Arrival sequence remains the vehicle's causal order; timestamps alone cannot repair missing or reversed events.

## Structural trade-offs, risks, and reversibility

### Chosen trade-off

Publishing after final insert/context binding gives an authoritative node/hash and keeps build identity separate from storage durability. Publishing earlier in the scheduler would lack node identity; publishing in ACK drain would allow durability to manufacture build evidence. Leader-only publication avoids a new collective and replicated logical events.

### Risks

1. Existing-node/context conflict: a reused node may already be bound to another session/build. The readback equality requirement deliberately suppresses the event rather than asserting an unsafe join. This can make a run `NOT_VERIFIED`, which is safer than false P0 acceptance.
2. Ancestor promotion: V4.3 may emit persistence/barrier records for promoted ancestors. The P0 reducer/evidence must use only the finalized build node/hash identity; otherwise `identity_count` exceeds one and the run cannot pass.
3. Immediate backup actions: submit/enqueue diagnostics can precede the build event during insert. They are not accepted durable evidence. If an accepted KV/Mamba durable event or combined barrier can be demonstrated to precede this producer boundary, implementation must stop and return for architectural re-evaluation rather than reorder the vehicle.
4. Multi-rank publication: group-leader detection must use actual TP-group membership. The accepted gate's separate topology-fallback concern remains open; this memo does not resolve or weaken it.
5. Logging is best-effort: `_t38c_durable_log` currently swallows exceptions. A missing event therefore fails P0 closed; it must not be inferred from successful HTTP or later barriers.

### Reversibility and migration

The change is additive, marker-gated, and localized to one product lifecycle boundary using the existing V3 context/logger interface. Reverting the helper/call removes the event without changing cache behavior or persisted data. No storage format, network API, cache key, allocator generation, session API, or vehicle schema migration is required.

Operational migration is:

```text
accept this design (orchestrator)
  -> fresh coder implements product emitter + focused fixture
  -> independent reviewer accepts exact diff/gate
  -> fresh devops task adds launcher flag and verifies resolved config
  -> fresh S=25 RH-off tester run
  -> independent P0 gate review
```

Do not reuse R3 as acceptance evidence, mutate its records, synthesize the missing event, or admit V2.

## Artifacts

- This memo: `.memory/phase2-hicache-design/work/ARCH-20260908-P0-BUILD-COMPLETE-CONTRACT.md`
- No product, launcher, vehicle, gate, ledger, or remote artifact changed.

## Evidence

- `DEBUG-20260908-P0-R3-V3-GAP.md`: confirms launcher activation gap and absent live product emitter.
- `SCOUT-20260908-P0-R3-EVENT-GAP.md`: confirms strict V3/full-identity/ordered vehicle behavior.
- `review/gates/P0-TRACE-CONTEXT-V4.3-SESSION-RETIRE-V2.md`: accepted narrow lifecycle boundary and still-blocked runtime gate.
- `trace_context.py`: existing marker, generation, build RID, and V3 attachment invariants.
- `unified_radix_cache.py`: finalized insert/node-context boundary and later attempt-keyed ACK/frontier/barrier path.
- `scheduler.py` and session-ref handling: scheduler-owned generation gated by session radix enablement.
- `p0_session_barrier_vehicle.py`: response-ID source, exact identity count, V3-only reducer, and ordered warm gate.
- Frozen `plan-rh-durability.md` and associated reports: no fixed-sleep proof, no KV-only acceptance, frozen S=25/RH-off gate, and no scale advance before independent PASS.
- Inspected local identities: `trace_context.py` SHA-256 `aa8656e1e6e572dd139d4c18e4f6840083800df5b2692bdcad3bf2dab82e439e`; `unified_radix_cache.py` `10e0d53b3efa2d8a3a3202c546d7f36a2ef4655979d18d7f6c3722f72706ec6c`; vehicle `c557300fe8f287a4ef10c5105a89bd48e3c8f2c01d0621700da362031d1db5bc`.

## Followups

- Orchestrator: accept, amend, or reject this recommendation; it is not self-authorizing.
- If accepted, dispatch a fresh coder Task ID with the minimal product/test write set and an independent reviewer gate.
- After product acceptance, dispatch a separate devops task for launcher correction and resolved-config evidence, then a fresh tester task for the frozen S=25 RH-off run.

## Open issues

- The accepted V4.3 review retains a separate authoritative-rank-topology fallback concern. This contract avoids expanding it but does not close it.
- Existing-node conflicting context and ancestor-promotion behavior are intentionally fail-closed and require focused evidence; no semantic tree/session repair is authorized here.
- Whether any accepted durable event can race ahead of this boundary must be proven by the coder/reviewer fixture and fresh runtime evidence. If observed, the design requires re-evaluation rather than a vehicle relaxation.
- P0 runtime remains blocked until a fresh corrected run and independent gate pass. This memo does not accept implementation or runtime evidence.
