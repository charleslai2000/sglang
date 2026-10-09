ENTRY: ACCEPT

# P0.1 readiness-to-residency timing contract after r17

- Task ID: `ARCH-20260908-P0-RESIDENCY-R17-TIMING-CONTRACT`
- Orchestration epoch: `phase2-hicache-design/2026-09-08`
- Role: `architect`
- Invocation status: `done`
- Decision owner: orchestrator. This report is architectural evidence and a recommendation; it does not authorize implementation or accept a gate.
- Scope performed: read-only inspection of the authoritative build-complete contract, accepted node-sidecar and typed-lookup gates, accepted FIX5/FIX6 gate records, r17 debugger reduction, current r17-aligned product source, focused fixture, and vehicle. The only write is this report. No product/test/vehicle source, remote host, live process, or evidence bundle was modified.

## Decision summary

Recommend the following narrow P0.1 contract for orchestrator acceptance:

1. The only radix node eligible to enter strict residency pending state is the exact non-root final node whose six-field identity was successfully registered by the accepted `build_complete` boundary. Ancestors may retain diagnostic sidecars, but they never acquire pending tokens and never participate in a residency fold. Legacy/non-build pending identities are retired fail-closed.
2. Residency is a one-shot release lifecycle over one exact build identity. Its ordered readiness projection is `BUILD_CREATED -> DETACH_SEALED -> DURABILITY_READY -> FREES_COMPLETE -> QUEUES_EMPTY -> RESIDENCY_PUBLISHED -> WARM_VISIBLE`. Async facts may arrive early, but the projection cannot skip an earlier predicate and publication is allowed only from `QUEUES_EMPTY`.
3. Reconciliation is event-driven. Every transition that can make an identity newly ready must synchronously enqueue or invoke one idempotent reconcile after committing that transition. Scheduler checkpoint polling is not a correctness or liveness dependency. A bounded watchdog may detect missing triggers, but it may not manufacture readiness or repeatedly log unchanged state.
4. A non-`None` device or host value for any required P0 component is a semantic residency blocker, not merely telemetry. For P0.1 the supported component manifest is exactly `FULL` (KV) plus `MAMBA`; absence must be observed for both device and host tiers on the exact final node. Any additional warm-hit-capable active component is unsupported and fails closed until separately designed.
5. Diagnostics are bounded per identity and release lifecycle: one immutable first-failure record, at most one record for each distinct blocker code, and one terminal publish or retirement record. Suppression affects logging only, never reconcile attempts. The terminal record carries aggregate attempt/suppression counts and causal references.
6. Acceptance is staged: deterministic one- and two-radix-identity gates first, then one fresh `S=8`, RH-off P0.1 run. In this contract, “1–2 node” means one or two radix build identities in one cache, not one or two physical hosts. Multi-host/fleet topology is explicitly out of scope.

The recommendation is intentionally fail-closed and marker-gated. It does not weaken the accepted six-field identity, typed node lookup, durability, token-completion, queue-emptiness, or at-most-once publication predicates.

## Input validation and observed facts

### Authoritative inputs inspected

- `.memory/phase2-hicache-design/work/ARCH-20260908-P0-BUILD-COMPLETE-CONTRACT.md`
- `.memory/phase2-hicache-design/work/DBG-20260908-P0-RESIDENCY-R17-OUTCOME-TRIGGER.md`
- `.memory/phase2-hicache-design/work/REV-20260908-P0-RESIDENCY-BARRIER-NODE-SIDECAR-FIX1.md`
- `.memory/phase2-hicache-design/work/REV-20260908-P0-RESIDENCY-BARRIER-NODE-LOOKUP-FIX1.md`
- `review/gates/P0-RESIDENCY-BARRIER-EMITTER-FIX5.md`
- `review/gates/P0-RESIDENCY-BARRIER-DIAGNOSTIC-FIX6.md`
- `review/gates/P0-RESIDENCY-BARRIER-NODE-SIDECAR-FIX1.md`
- `review/gates/P0-RESIDENCY-BARRIER-NODE-LOOKUP-FIX1.md`
- r17-aligned `python/sglang/srt/mem_cache/unified_radix_cache.py`
- `3090-dev/test_p0_residency_barrier_emitter.py`
- `3090-dev/p0_session_barrier_vehicle.py`

The designated report worktree's product file is not the r17 source: its SHA-256 is `b162b1289043441dbffbe1d4dc8f6317766039a0a320d71209eb7fd3766d207b` and it has no current residency implementation. The accepted gates point to the sibling `sglang-3090-24g-opt` worktree. That r17-aligned source has SHA-256 `3dce9fe5f6551d586ea858301075ac75b5487181b9f36fe03d7b0fca87619c69`, matching the debugger's local/deployed hash. The inspected vehicle SHA-256 is `5965d8d8744dc0f0f106064b9dd69d26a4069b67ff88fbf0614c3a2766d3bd62`.

The r17 evidence directory was not locally mounted. This task did not use SSH, as prohibited. Runtime facts below therefore rely on the designated debugger report and its recorded immutable trace hash `da99dfacd885573ab7736d1229e8ec54c766d1cda2f98620d9d8f870116d59ea`.

### Observed facts

1. The accepted build contract establishes one exact logical build identity:

   ```text
   B = (run_id, session_id, session_generation, build_rid,
        node_id, final_kv_hash)
   ```

   `build_complete` is emitted only for `result.last_device_node`; ancestors do not receive build registration.
2. `_t38c_record_node_context` intentionally records a distinct node/hash sidecar for the final node and each ancestor. Sidecar existence is identity context, not build authority.
3. Current `_t38c_note_detach` admits any valid sidecar identity to `_t38c_residency_detached`; it does not require membership in `_t38c_build_identities`.
4. r17 consequently retained 460 ancestor identities that could never satisfy the final-node-only build predicate. They generated 471,464 `build_not_ready` outcomes. The retry epoch advanced to 200,923 in about 325 seconds.
5. The accepted typed `NodeId` repair worked in r17: `node_lookup` outcomes were zero.
6. Ten exact identities reached both build and durability readiness. Every post-durability fold for those identities returned `live_component_value`; no strict residency barrier was published. The trace did not identify the blocking component/tier.
7. The current live predicate checks `FULL` and `MAMBA`, device `value` and `host_value`, and returns on any non-`None` value. This is a direct read of cache state.
8. Current exact completion callbacks re-enter the fold. Durability promotion re-enters the fold. Every storage-control drain also enumerates all pending identities and re-enters the fold.
9. The accepted FIX5 contract requires the primary KV release queue and every extra host release queue to be empty under `_t38c_release_handoff_lock`, with the cache residency `RLock` held outside it, before publication.
10. The current vehicle requires ordered exact build, KV, Mamba, durability, residency, then warm evidence. It is frozen to `sessions=25`; `_validate_frozen` rejects `S=8`.

### Assumptions requiring implementation confirmation

- Component-data mutation for one `UnifiedRadixCache` is scheduler/tree-owner serialized. The proposed event hook runs after the relevant tree mutation commits and outside any tree-internal lock that would invert the accepted residency-lock ordering.
- For this P0 workload, the complete set of warm-hit-capable components is `FULL` and `MAMBA`. If `SWA` or another component is active and can serve a warm hit for the target node, P0.1 must fail closed and return for architecture rather than silently exclude it.
- A deployment of the timing repair restarts the engine. No supported in-process migration from r17's already-populated pending map is assumed.

## Ownership and boundaries

| Concern | Authority/owner | Allowed P0.1 capability | Prohibited capability |
| --- | --- | --- | --- |
| Build identity and terminal node eligibility | `UnifiedRadixCache.cache_finished_req` accepted `build_complete` boundary | Register exactly one final-node identity after sidecar readback | Derive eligibility from sidecar, parenthood, detach, hash similarity, timestamp, or vehicle state |
| Node component residency | Exact final node's component data | Observe `FULL`/`MAMBA` device and host presence after mutations | Treat logs, token completion, or queue emptiness as proof that component values are absent |
| Detach/release expectation | Cache-owned residency lifecycle | Register exact pool/tier/digest/token only for an eligible identity | Create pending state or release token for an ancestor/non-build identity |
| Free completion | Allocator/controller completion callback | Mark one exact owned release token complete after free returns | Infer completion from enqueue, dequeue, queue size, or elapsed time |
| Durability | Existing combined durability barrier | Add exact identity to `durability_ready` after accepted KV+Mamba frontier evidence | Recompute, weaken, or infer durability from residency state |
| Queue quiescence | Owning cache controller | Snapshot all owning release queues under the accepted handoff lock | Drain queues from the fold, sample unlocked, or use a fixed sleep |
| Residency publication | Cache-owned strict reconciler | Publish one existing `residency_barrier` for one exact identity | Let vehicle, logger, diagnostic state, or watchdog publish |
| Warm visibility | Product warm lookup plus vehicle reducer | Observe warm lookup only after residency publication | Issue or accept warm work from a diagnostic or timer |

The vehicle remains a consumer/oracle. It does not become lifecycle authority. Diagnostics remain derived observation and cannot advance any state.

## Terminal-node eligibility contract

### Eligibility invariant

`ELIGIBLE(B)` is true if and only if all of the following are true:

- `B` is a complete exact six-field `p0_durable.v3` identity with `warm_rid=None`;
- `B` was inserted into the cache-owned build registry by a successful accepted `build_complete` emission/readback for `result.last_device_node`;
- typed lookup resolves `B.node_id` to exactly one live non-root, non-forced-miss node;
- that node's current own final hash equals `B.final_kv_hash`; and
- the node sidecar readback equals `B`'s run/session/generation/build/node/hash context.

No other condition can make an identity eligible. In particular, a valid parent sidecar, a detach record, a completed token, a durable ancestor, or a matching hash prefix is insufficient.

### Admission and retirement rules

1. `_t38c_note_detach` must check exact build membership before calling `remember_slot_context` or mutating pending state.
2. An ineligible ancestor/non-build detach may emit one bounded diagnostic with `reason=nonterminal_not_build_registered`; it must not create an expected token, pending map entry, retry work, or publication candidate.
3. A sidecar conflict, changed node hash, missing typed node, root/tombstone, session retirement, engine reset, or component reattachment after detach sealing moves the lifecycle to `RETIRED_INVALID`. No publication is possible from that sink.
4. Any pre-existing pending identity not in the build registry is pruned to `RETIRED_INELIGIBLE` before reconciliation. In the supported deployment path, engine restart starts with empty transient maps; the prune rule exists for fixtures and defensive consistency, not as a rolling-upgrade protocol.
5. Sidecars may continue to exist on ancestors because storage attribution uses them. They are not removed by this contract; only residency eligibility is narrowed.

This resolves r17's authority mismatch without granting parents a second build lifecycle.

## Lifecycle state machine

### State representation

The cache owns one transient lifecycle record per eligible `B`. It contains monotonic facts plus a derived ordered state. Required facts are:

```text
build_registered
detach_seen
detach_sealed
durability_ready
expected_release_tokens
completed_release_tokens
component_snapshot
queue_snapshot
publication_event_id
retirement_reason
reconcile_attempt_count
diagnostic_reason_set
suppressed_diagnostic_count
```

The record is diagnostic-marker-gated and process-local, like the existing P0 trace state. It is not persisted and is not a cache correctness authority outside this P0 gate.

### Ordered states

| State | Entry predicate | Allowed next state(s) |
| --- | --- | --- |
| `UNTRACKED` | No exact build registration | `BUILD_CREATED`; ineligible detach stays untracked and may produce one bounded diagnostic |
| `BUILD_CREATED` | Exact final-node build registration exists | `DETACHING`, `RETIRED_INVALID` |
| `DETACHING` | At least one exact eligible detach expectation exists | `DETACH_SEALED`, `RETIRED_INVALID` |
| `DETACH_SEALED` | At least one device detach exists; every required component/tier is absent on the exact node; all detach expectations for the one-shot release have been registered | `DURABILITY_READY`, `RETIRED_INVALID` |
| `DURABILITY_READY` | Existing exact combined KV+Mamba durability barrier is present | `FREES_COMPLETE`, `RETIRED_INVALID` |
| `FREES_COMPLETE` | Every expected exact release token has completed after its allocator free returned | `QUEUES_EMPTY`, `RETIRED_INVALID` |
| `QUEUES_EMPTY` | Primary KV and all configured extra host-release queues are empty in one locked snapshot | `RESIDENCY_PUBLISHED`, `RETIRED_INVALID` |
| `RESIDENCY_PUBLISHED` | Existing strict event write returned an event ID; identity is atomically recorded as published and pending tokens are retired | `WARM_VISIBLE`, terminal session retirement |
| `WARM_VISIBLE` | Vehicle observes a product `warm_lookup_start`/warm request for the same build identity after the residency event | terminal evidence state |
| `RETIRED_INVALID` | Identity/hash/context conflict, unsupported component, reattachment after sealing, session retirement before publish, or other non-recoverable invariant breach | terminal; never publish |

`WARM_VISIBLE` is an evidence/reducer state, not a mutation of the cache residency registry. The product registry's success terminal is `RESIDENCY_PUBLISHED`.

### Ordering semantics

The arrows define the order in which readiness may be asserted, not a requirement to discard safe evidence that physically arrives early. Async facts are joined under the exact identity and projected through the ordered predicates:

- A free completion that arrives before durability is retained as exact token evidence, but the derived state cannot advance past `DETACH_SEALED` until durability is ready.
- Durability that arrives before detach sealing is retained, but the derived state remains `BUILD_CREATED`/`DETACHING` until the component detach boundary is sealed.
- An empty queue snapshot taken before all exact frees complete does not establish `QUEUES_EMPTY`; queue emptiness must be resampled after the final completion trigger.
- Timestamps never repair a missing or reversed identity event. The logger's event IDs/local ordering and exact causal references are the evidence order.

Publication requires all predicates simultaneously in this strict order:

```text
eligible exact final build
AND detach_seen
AND device_detach_seen
AND FULL.device absent
AND FULL.host absent
AND MAMBA.device absent
AND MAMBA.host absent
AND exact combined durability ready
AND every expected release token complete
AND owning primary and extra release queues empty under handoff lock
AND not already published or retired
```

The publication event must be written while the accepted cache-residency-lock -> release-handoff-lock ordering prevents an enqueue race. No collective, allocator free, queue drain, or callback is allowed while executing the strict publication fold.

### One-shot release invariant

P0.1 proves one cold transition for one immutable build. If any required component value becomes present after `DETACH_SEALED` and before publication, the identity is retired invalid rather than regressed or assigned a second release cycle. Supporting repeated restore/evict cycles would add generation and authority semantics and requires a fresh architecture task.

## Reconciliation and retry contract

### Decision: event-driven authoritative reconciliation

Use event-driven reconciliation. A transition owner commits its state, then requests one idempotent reconcile for the exact identity. The required triggers are:

| Trigger | When reconcile is mandatory |
| --- | --- |
| `build_registered` | After exact final build registration succeeds |
| `eligible_detach_registered` | After a new exact device/host release expectation is recorded and after the component slot has been cleared |
| `detach_sealed` | After a component mutation makes the complete required component/tier snapshot absent |
| `durability_ready` | Immediately after exact combined durability readiness is committed |
| `free_complete` | Immediately after each exact allocator free returns and token completion is committed; the final completion must trigger without waiting for another request |
| `release_queues_drained` | At the end of the owning drain transaction when queue state may have crossed to empty; reconcile affected pending identities after drain bookkeeping |
| `session_retired` / `identity_invalidated` | Immediately retire matching pending state and tokens; never publish |

Reconcile may run inline under the existing reentrant cache residency lock or through a bounded cache-owned deduplicating ready set drained by the scheduler owner. If queued, the ready set key is the exact identity, capacity is bounded by eligible builds in the run, and enqueue is idempotent. An unbounded event queue is forbidden.

### Polling boundary

- Remove full enumeration of all pending identities on every storage-control drain as a correctness/liveness mechanism.
- A watchdog is optional and observation-only. It may inspect at most the bounded set of eligible identities once per configured coarse interval and schedule a missing reconcile, but it must not publish directly, change facts, or emit unchanged per-epoch outcomes.
- Correctness tests must pass with the watchdog disabled. Every asynchronous readiness transition must prove its own trigger.
- A missed trigger is a liveness defect, not permission to add a fixed sleep or high-rate poll.

This preserves strict retries while eliminating r17's epoch x pending-identity amplification.

## `live_component_value` semantics and proof

### Decision: semantic blocker

`live_component_value` names a semantic blocker: the exact final node still owns a device- or host-resident value usable by the warm cache path. `cold_residency=true` would be false while such a value exists, even if detach logs, free callbacks, durability, and queues otherwise look complete.

The blocker predicate is direct state, not an inference from telemetry:

```text
for component in required_component_manifest:
    component_data[component].value is None
    AND component_data[component].host_value is None
```

For P0.1, `required_component_manifest` must be recorded at build registration and must equal `FULL,MAMBA`. Missing component data, an unknown active warm-hit component, lookup ambiguity, or snapshot failure is fail-closed and cannot be treated as absence.

### Required component/tier evidence

Every first `LIVE_COMPONENT_VALUE` diagnostic and every terminal publish/retire record must carry a privacy-safe exhaustive snapshot for the exact final node:

```json
{
  "required_component_manifest": ["FULL", "MAMBA"],
  "component_tiers": [
    {
      "component": "FULL",
      "pool": "kv",
      "device_present": false,
      "device_slot_count": 0,
      "device_lock_ref": 0,
      "host_present": false,
      "host_slot_count": 0,
      "host_lock_ref": 0
    },
    {
      "component": "MAMBA",
      "pool": "mamba",
      "device_present": true,
      "device_slot_count": 1,
      "device_lock_ref": 0,
      "host_present": false,
      "host_slot_count": 0,
      "host_lock_ref": 0
    }
  ],
  "live_component_count": 1,
  "snapshot_complete": true
}
```

Normative details:

- `*_present` is derived only from `is not None`, matching the semantic predicate. Zero-length non-`None` values remain present and blocking.
- Slot counts describe metadata only; raw indices, tensors, state, tokens, prompts, or cache contents are forbidden.
- Lock refs are observational context. A zero lock ref does not prove absence and cannot satisfy the gate.
- A publish record requires all four presence booleans false, `live_component_count=0`, and `snapshot_complete=true`.
- Detach/completion evidence additionally reports pool, tier, slot count, digest, and release token reference. It does not substitute for the direct component snapshot.

This schema makes r17's unresolved component/tier owner observable before any separate eviction/free repair is considered.

## Bounded diagnostic outcome contract

### Separation from strict state

Diagnostic emission is best-effort and exception-contained. Whether a record is emitted, deduplicated, coalesced, or lost must not alter eligibility, state facts, reconcile scheduling, publication, or retirement.

### Finite reason vocabulary

Use a finite enum, not dynamic reason strings:

```text
NONTERMINAL_NOT_BUILD_REGISTERED
NODE_LOOKUP_FAILED
IDENTITY_INVALID
DETACH_NOT_SEALED
UNSUPPORTED_COMPONENT
DURABILITY_NOT_READY
LIVE_COMPONENT_VALUE
TOKEN_INCOMPLETE
QUEUE_SURFACE_MISSING
QUEUE_NONEMPTY
LOGGER_FAILED
RETIRED_INVALID
PUBLISHED
```

### Emission bound and preservation rules

For each exact eligible identity's one-shot lifecycle:

1. Emit the first observed false predicate as `first_failure=true` with full state and causal references.
2. Emit at most one record for each distinct reason code. Repeated reconciles with the same reason increment in-memory `reason_attempt_count` and `suppressed_diagnostic_count`; they do not append another record.
3. Emit exactly one terminal record when publication succeeds or retirement occurs. It includes first-failure event ID/reason, all observed reason codes, total reconcile attempts, per-reason attempt counts, suppressed count, first/last monotonic timestamps, and terminal causal references.
4. `NONTERMINAL_NOT_BUILD_REGISTERED` is bounded once per `(run_id,node_id,final_kv_hash)` and creates no lifecycle record. Thus ancestors may produce bounded discovery evidence but no retry stream.
5. No retry epoch or poll attempt is part of the diagnostic dedup key. Epochs may be counters in a terminal summary but can never authorize a new physical record.
6. Logger failure leaves the identity pending and retryable. It cannot mark publication complete. A later state trigger retries the strict fold; diagnostics remain bounded.

With 13 finite codes, an eligible lifecycle produces no more than 14 outcome records (at most one per code plus one terminal record; a terminal code is not emitted twice). Normal successful paths should produce far fewer. Strict reconcile attempts themselves are not capped by this diagnostic bound.

### Diagnostic evidence schema

Each emitted outcome requires:

```text
schema_version, evt, event_id, run_id
session_id, session_generation, build_rid, node_id, final_kv_hash
eligible_terminal, lifecycle_state, trigger, reason, result
first_failure, reconcile_attempt_count, reason_attempt_count
suppressed_diagnostic_count
build_event_id, durability_event_id
detach_event_ids_digest, completion_event_ids_digest
expected_release_count, completed_release_count
device_detach_seen, detach_sealed
required_component_manifest, component_tiers, live_component_count,
snapshot_complete
queue_snapshot_locked, primary_queue_empty, extra_queue_empty,
extra_queue_emptiness
ts_wall_ns, ts_mono_ns, local_seq, rank, process_id, thread_id
```

Terminal records additionally require `first_failure_event_id`, `first_failure_reason`, `observed_reasons`, `reason_attempt_counts`, `first_attempt_ts_mono_ns`, `last_attempt_ts_mono_ns`, and either `publication_event_id` or `retirement_reason`.

## Strict publication evidence schema

The existing vehicle-facing `residency_barrier` identity and meaning remain unchanged. P0.1 adds proof fields; it does not rename or weaken the event:

```json
{
  "schema_version": "p0_durable.v3",
  "evt": "residency_barrier",
  "run_id": "<run>",
  "event_id": "<unique>",
  "session_id": "<session>",
  "session_generation": 1,
  "build_rid": "<response.id>",
  "warm_rid": null,
  "node_id": "<exact final node>",
  "final_kv_hash": "<exact final hash>",
  "result": true,
  "cold_residency": true,
  "reason": "all_detached_frees_complete",
  "lifecycle_state_before": "QUEUES_EMPTY",
  "trigger": "free_complete|release_queues_drained|durability_ready|detach_sealed",
  "build_event_id": "<causal ref>",
  "durability_event_id": "<causal ref>",
  "expected_release_count": 2,
  "completed_release_count": 2,
  "device_detach_seen": true,
  "required_component_manifest": ["FULL", "MAMBA"],
  "component_tiers": "<exhaustive snapshot; all absent>",
  "live_component_count": 0,
  "snapshot_complete": true,
  "queue_snapshot_locked": true,
  "primary_queue_empty": true,
  "extra_queue_empty": true,
  "extra_queue_emptiness": {"mamba": true},
  "reconcile_attempt_count": 7,
  "suppressed_diagnostic_count": 4
}
```

The exact identity tuple must match build, accepted KV/Mamba evidence, and durability. Publication state is committed only after the logger returns a non-null event ID. Exact duplicate calls remain idempotent; any changed identity is a conflict, never last-write-wins.

## Invariants

| ID | Normative invariant | Failure oracle |
| --- | --- | --- |
| `R17-T1` | Only an exact final-node identity registered by accepted `build_complete` may enter pending residency state. | Parent/non-build detach creates no token/pending entry/retry candidate. |
| `R17-T2` | Sidecar context is necessary but never sufficient for eligibility. | A valid parent sidecar remains ineligible. |
| `R17-T3` | Readiness projection cannot skip the ordered states or publish before all predicates are simultaneously true. | Any missing earlier predicate yields no barrier. |
| `R17-T4` | Every transition that can satisfy the next predicate triggers exact-identity reconciliation without requiring a later request or periodic poll. | Watchdog disabled; final async transition still publishes once. |
| `R17-T5` | `FULL` and `MAMBA` device/host non-`None` values are semantic blockers. | Any one of four live fields prevents publication and is named in evidence. |
| `R17-T6` | Exact free completion means allocator free returned for every owned expected token. | Enqueue/dequeue or unmatched token never counts as complete. |
| `R17-T7` | Queue emptiness is sampled under the owning handoff lock immediately before publication, with cache residency lock outermost. | Non-empty/missing/unlocked queue surface cannot publish. |
| `R17-T8` | Publication is at most once per exact identity and occurs before warm visibility. | Repeat triggers produce one barrier; warm-before-barrier is non-PASS. |
| `R17-T9` | Diagnostic suppression cannot suppress reconcile or alter strict state. | Disable/fail/coalesce logging; publication behavior is unchanged. |
| `R17-T10` | Diagnostic physical records are finite per identity/lifecycle and retain first failure plus terminal transition evidence. | Repeated unchanged reconcile grows counters, not JSONL lines. |
| `R17-T11` | Reattachment after detach sealing retires the one-shot lifecycle fail-closed. | No stale-token publication after a value becomes present again. |
| `R17-T12` | Unknown or additional active warm-hit components fail closed in P0.1. | Unsupported component produces retirement/no barrier. |

## Required test scenarios

### A. Deterministic one-radix-node gate

1. Happy path with watchdog/poll disabled: exact build; eligible device/host detaches; direct all-absent component snapshot; durability; exact frees; queue transition to empty; exactly one residency barrier; warm marker after it.
2. Permutation table: durability and individual completions may arrive before the earlier derived state. Facts are retained, no state is skipped, and the final missing transition triggers publication without polling.
3. Each of `FULL.device`, `FULL.host`, `MAMBA.device`, and `MAMBA.host` is independently live. Each blocks and emits a component-specific snapshot; clearing it and invoking its transition trigger permits later progress.
4. Missing/unknown component, incomplete snapshot, zero-length non-`None` value, changed hash, missing node, wrong typed node, root, forced miss, sidecar conflict, missing build, and missing durability all fail closed.
5. Token cases: unmatched, cross-cache, stale generation, duplicate completion, completion before durability, partial completion, and final completion with no next request.
6. Queue cases: primary non-empty, each extra queue non-empty, missing lock/queue/map, enqueue-versus-publication race, and drain-to-empty with no subsequent request.
7. Logger exception/absence: no publication state is committed; later legitimate trigger retries strict publication.
8. Reattachment after sealing: lifecycle retires; stale completed tokens cannot publish.
9. Marker off: no P0.1 state or events and no cache behavior change.

### B. Deterministic two-radix-node gate

Use one cache with two exact final build identities plus at least one ancestor sidecar/detach:

1. Ancestor detach produces at most one ineligible diagnostic and no pending/token/reconcile entry.
2. Two eligible final identities maintain disjoint expected/completed tokens, component snapshots, durability facts, counters, and publication IDs.
3. Shared primary/extra queues block both while non-empty. The drain-to-empty trigger reconciles the bounded eligible ready set; each publishes only if its own facts are complete.
4. Interleave detach, completion, durability, retirement, and queue callbacks across both identities for deterministic race schedules. No cross-identity join, starvation, deadlock, duplicate publication, or per-epoch log growth is allowed.
5. Seed a legacy parent pending entry. Reconciliation retires/prunes it once and never revisits it.

The independent reviewer must accept A and B before any live expansion. Local acceptance requires the focused fixture, V4.3 fixture, compile/AST/diff checks, explicit lock-order audit, and a bounded-log assertion. Passing old fixtures alone is insufficient.

### C. Fresh `S=8` RH-off P0.1 expansion

The current vehicle is hard-frozen to `S=25`; it cannot honestly evidence this stage unchanged. Before execution, a separately reviewed harness change must add a named P0.1 `S=8` profile or separate vehicle entry point while preserving the existing S=25 profile unchanged. The resolved config and source hashes must prove which profile ran.

Acceptance requires all of the following:

- fresh run ID, marker-before-engine audit, exact reviewed source/harness hashes, `S=8`, active/build workers no greater than 8, and RH explicitly off;
- eight planned sessions, each with exactly one logical final build identity and exact response-ID join;
- for all eight: ordered exact build, KV, Mamba, combined durability, strict residency, product warm lookup, and successful warm response/restore evidence;
- no eligible identity publishes while any required component tier is live, any expected token incomplete, or any owning release queue non-empty;
- zero parent/non-build identities in pending state at every captured state summary and at finalization;
- zero `node_lookup`, identity-conflict, unsupported-component, stale-token, warm-before-barrier, or duplicate-publication outcomes;
- diagnostics obey the per-identity finite bound; unchanged blocker repetition increases summary counters without proportional trace growth;
- every started eligible identity reaches `RESIDENCY_PUBLISHED` and `WARM_VISIBLE`, or the run is `NOT_VERIFIED`/fail-closed; partial session success is not PASS;
- engine/vehicle terminate cleanly and the immutable bundle includes final process audit, complete native vehicle output, event counts, per-session lifecycle rows, source/config hashes, trace hash, and independent tester verdict.

S=8 acceptance authorizes only the next existing P0 decision chosen by the orchestrator. It does not authorize S=25, Ready Horizon, fleet, multi-host, Agent, or economics work.

## Evidence bundle additions

The tester's immutable bundle must include:

```text
source-hashes.txt
config-resolved.json
trace-copy.jsonl and digest
lifecycle-by-identity.jsonl
diagnostic-bounds.json
pending-state-snapshots.jsonl
component-tier-first-blockers.jsonl
queue-transition-evidence.jsonl
build-warm.jsonl
barrier-waits.jsonl
reducer-result.json
verdict.json
final-process-audit.txt
```

Each lifecycle row requires identity, component manifest, first/last state order, causal event references, expected/completed release counts, first blocker, distinct blocker set, reconcile attempts, emitted/suppressed diagnostic counts, publication event ID/order, warm event ID/order, and retirement reason if any. Analyzer arrival order is authoritative for the causal gate; wall timestamps are supporting evidence only.

## Migration, rollback, and reversibility

- State is marker-gated and transient. There is no storage format, cache key, network API, allocator format, session API, or durable-data migration.
- Forward deployment requires an engine restart with a fresh run ID. Mixed r17/P0.1 ranks and in-process conversion of r17 pending maps are unsupported and non-PASS.
- The narrow seam is the residency eligibility/reconcile/diagnostic helper surface plus focused harness. Reverting it restores r17 behavior without rewriting data, but r17's ancestor retry amplification and missing component oracle return; therefore rollback means stop the P0 evidence run or disable the diagnostic marker, not claim a P0 pass.
- Removal proof: marker-off tests show no P0 state/events; source/static audit shows no vehicle/diagnostic authority; fresh process starts with empty lifecycle maps.
- No new background thread is required. Event-driven callbacks and a bounded deduplicating ready set minimize operational blast radius.

## Structural trade-offs and rejected alternatives

| Alternative | Decision | Reason |
| --- | --- | --- |
| Give every ancestor a build lifecycle | Reject for P0.1 | Expands build authority, identity cardinality, durability joins, and vehicle semantics; contradicts final-node build registration. |
| Keep ancestors pending but hide their logs | Reject | Masks impossible work while retaining token/state leaks and unbounded reconcile cost. |
| Poll all pending identities on every drain | Reject | r17 demonstrates unbounded epoch x identity amplification and polling is unnecessary when transition owners are known. |
| Fixed sleep before warm | Reject | Time is not proof of component absence, free completion, durability, or queue quiescence. |
| Treat `live_component_value` as telemetry only | Reject | Would permit `cold_residency=true` while a warm-hit-capable value remains resident. |
| Require both device and host detach events for every component | Reject | A tier never populated has nothing to detach; direct exhaustive absence plus exact completion of all actual detaches is the correct oracle. |
| Allow lifecycle regression/repeated release cycles | Defer | Requires a release generation and stale-token policy beyond this one-shot P0 contract. |
| Let watchdog/poller publish | Reject | Creates a second timing authority and obscures missing event triggers. |

## Pattern Intake and Novel Mechanism gate

Observed repository policy requires a completed Pattern Intake before any non-exempt implementation G1/G2 dispatch. No completed intake was supplied to this architecture task. That omission does not invalidate this read-only recommendation, but it blocks the next coder admission.

This design changes the residency eligibility and retry/failure boundary and composes final-build authority with event-driven lifecycle reconciliation. The recommended preliminary classification is `NOVEL_MECHANISM`, consistent with the r17 debugger's reroute. Under a fresh Task ID, the orchestrator must require:

- complete corpus search and Pattern Intake at the mandated revision/scope;
- a Novel Mechanism declaration covering eligibility authority, one-shot lifecycle, event triggers, diagnostic bounds, failure model, oracle, and rollback;
- explicit orchestrator/architecture-gate acceptance before implementation;
- atomic mappings from `R17-T1` through `R17-T12` to patterns/novel declaration and concrete tests.

This report is an architecture input to that gate, not a substitute for it and not an accepted novelty declaration.

## Explicit non-goals

- No product, test, vehicle, launcher, gate, ledger, or remote change in this task.
- No repair of why r17's `FULL` or `MAMBA` value stayed live; P0.1 first makes the owner/tier observable and preserves fail-closed behavior.
- No ancestor build/durability authority.
- No repeated restore/evict release generations.
- No change to storage persistence, KV/Mamba durability semantics, expected-rank topology, session generation, or build identity.
- No weakening of queue, token, component, typed lookup, root/tombstone, logger-success, or at-most-once predicates.
- No Ready Horizon, S=25 acceptance, multi-host/fleet, Agent, capacity economics, cost model, tuning, or performance claim.
- No claim that r17 proves permanent deadlock; it proves bounded-interval liveness failure and diagnostic amplification.

## Next tasks (fresh Task IDs required)

1. **Pattern/authority task before coder admission** — complete the required Pattern Intake and Novel Mechanism declaration for `R17-T1`–`R17-T12`; obtain orchestrator acceptance under the existing gate family. This work is not included in the present Task ID.
2. **Coder task: product lifecycle** — implement only the accepted terminal eligibility, lifecycle facts, event-driven reconcile triggers, component/tier snapshots, legacy prune, and bounded diagnostic semantics in the r17-aligned product path. Preserve the existing strict barrier identity/event and accepted lock ordering. Authorized tests should extend the focused residency fixture for Sections A/B. The coder must provide a symbol-level change manifest and must stop if component mutation ownership or active component manifest differs from the assumptions above.
3. **Coder task: P0.1 vehicle profile** — separately add an exact named `S=8` profile or isolated entry point, preserving the existing frozen S=25 behavior. Extend reducer evidence rows for lifecycle/component/diagnostic bounds without making diagnostics readiness authority. Do not combine this with product lifecycle implementation unless the orchestrator explicitly authorizes coordinated write ownership.
4. **Tester task: deterministic gate** — independently execute the one-/two-radix-identity matrix with watchdog disabled, lock races, transition permutations, bounded-log assertions, marker-off checks, compile/static checks, and exact source hashes. No live execution until independent reviewer acceptance.
5. **Reviewer task** — read this accepted design (if accepted), Pattern Intake/Novel declaration, product/harness diffs, focused evidence, and change manifests; publish the implementation gate verdict. Blocking findings prevent S=8.
6. **Tester task: fresh S=8 RH-off** — after implementation acceptance, run the exact staged live profile and produce the immutable evidence bundle above. No RH/fleet/Agent/economics expansion is authorized.

## Risks and open decisions for orchestrator

| ID | Risk/open decision | Evidence/impact | Recommendation |
| --- | --- | --- | --- |
| `OD-1` | Accept/amend/reject final-build-only eligibility | r17 proves parent pending identities can never match build registration. | Accept final-only eligibility; retain parent sidecars for diagnostics/storage only. |
| `OD-2` | Confirm active component manifest | Current predicate checks `FULL`/`MAMBA`; source supports other component types. | Gate P0.1 to exact `FULL,MAMBA`; fail closed on additional warm-hit components. |
| `OD-3` | Confirm scheduler/tree mutation serialization and lock order | Event hooks must observe committed component state without inversion. | Require coder static/runtime evidence; return to architecture if another thread can mutate component slots outside the assumed boundary. |
| `OD-4` | Approve separate S=8 vehicle profile | Current vehicle rejects any session count other than 25. | Add an isolated P0.1 profile; do not relax or overwrite S25. |
| `OD-5` | Accept one-shot invalidation on reattachment | It is safer and narrower than adding release generations. | Accept for P0.1; defer repeated cycles. |
| `OD-6` | Pattern/Novel admission | Required artifact is absent and authority boundary is changing. | Block coder G1/G2 until completed and accepted. |

## Status packet

- Status: `done`
- Artifacts: this architecture report only.
- Evidence: authoritative build contract; accepted FIX5/FIX6, node-sidecar, and typed-lookup gate records; r17 debugger reduction and immutable trace/source hashes recorded there; direct inspection of the r17-aligned source, focused fixture, component data, and vehicle.
- Summary: recommend final-build-only residency eligibility, ordered one-shot readiness projection, event-driven mandatory reconciliation, semantic component/tier absence, and finite diagnostics; gate deterministic one-/two-radix-identity behavior before a separate S=8 RH-off run.
- Followups: orchestrator acceptance; mandatory Pattern Intake/Novel declaration; separate coder, reviewer, deterministic tester, vehicle-profile, and live S=8 tasks under fresh Task IDs.
- Open issues: orchestrator decisions `OD-1`–`OD-6`; component mutation serialization and exact active component manifest require implementation evidence. No live or implementation acceptance is claimed.
