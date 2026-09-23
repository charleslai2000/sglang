ENTRY: ACCEPT

# Primary-host allocability epoch/wake gate contract

```yaml
contract_version: 1.0.0-proposed
task_id: ARCH-20260909-HOST-ALLOC-EPOCH
orchestration_epoch: 20260909-P4
role: architect
target_branch: 3060-12g-qwen35-4b
status: proposed
decision: PENDING_ORCHESTRATOR_ACCEPTANCE
implementation_authority: none_granted_by_this_document
```

## 1. Purpose, authority, and evidence boundary

This contract proposes the architecture and acceptance gates for closing the
confirmed 3060 HiCache liveness gap in which a positive, sidecar-complete L3
hit reaches `WAIT_CAPACITY/HOST_ALLOC`, but no later retry occurs when a host
lock release makes primary-host cache material evictable without increasing
the already-free page count.

This document is design evidence, not implementation acceptance. The
orchestrator/design authority must accept or reject it. A coder owns any
implementation and change manifest, a tester owns execution evidence, and an
independent reviewer owns the implementation-gate verdict.

### Observed facts

- Commit `1e6a82194e7f5d071823e4abb68514c6d421e4b3` and its accepted review map
  `revoked_alloc_failed` to non-miss `DENIED_ALLOC -> WAIT_CAPACITY/HOST_ALLOC`.
- In the supplied live 3060 run, q/x/w each had a positive 54,976-token KV and
  Mamba L3 hit, then allocation failure, HOST_ALLOC wait, no later retry, and
  T13 timeout/recompute. y/z restored successfully. No invalid crop, hybrid
  discard, or Mamba fetch failure was observed.
- `Scheduler._restore_wait_capacity_fits` currently wakes HOST_ALLOC only when
  the complete primary KV span is already free. It does not call eviction.
- `UnifiedRadixCache._try_alloc_storage_hit` is the authoritative allocation
  path and can perform `alloc(full) -> evict_host(full) -> alloc(full)`.
- `UnifiedTreeCore.dec_host_lock_ref` can change
  `evictable_host_leaves` without changing primary-host free pages.
- Direct tree eviction frees returned host values synchronously; queued KV and
  auxiliary releases are returned by the storage-control drain. There is no
  restore-visible allocability generation for these changes.
- Auxiliary prefetch staging is allocated separately before the primary KV
  hit allocation. Mamba requires one trailing sidecar allocation and retains
  all-or-nothing hybrid finalization.

### Proposals awaiting acceptance

- A cache-owned monotonic generation vector records relevant host
  allocability changes. The primary KV member is mandatory; required
  auxiliary pools have separate members.
- A scheduler-owned FIFO arbiter grants at most one HOST_ALLOC full-span retry
  for each newly observed relevant generation vector.
- Allocation remains authoritative in the cache. A generation is only an
  invalidation/wake signal; it never proves that a request fits.

### Assumptions

- The scheduler and storage-control drain retain their current same-process
  reconciliation relationship. If generation mutation and observation can
  occur on different threads, the implementation must use an atomic counter
  or the controller's existing synchronization boundary and prove visibility.
- Counter wrap is treated as operationally impossible only if a non-wrapping
  Python integer is used. A fixed-width counter requires explicit wrap-safe
  comparison and a regression.
- The accepted scope is the Unified HiCache path used by the 3060 Qwen3.5
  KV+Mamba configuration. HiRadix, 3090 deployment behavior, distributed
  coordination, and storage durability are not implicitly changed.

## 2. Required ownership and dependency direction

| Concern | Owner | Required interface | Must not own/do |
| --- | --- | --- | --- |
| Generation state and bump accounting | Host-pool/cache-controller boundary, surfaced by `UnifiedRadixCache` | `host_allocability_snapshot(required_pools) -> HostAllocabilitySnapshot`; one internal bump API per pool | Scheduler must not synthesize generations from polling or mutate them. |
| Evictable-leaf transition detection | `UnifiedTreeCore` mutation, reported through `UnifiedRadixCache.dec_host_lock_ref` | return or side-channel indicating which host pool's evictable set/amount changed | Metrics or scheduler scans must not become eviction truth. |
| Full-span allocation and reclaim | `UnifiedRadixCache.prefetch_from_storage` and `_try_alloc_storage_hit`, using existing component allocators and `evict_host` | typed allocation-failure metadata identifying failed resource domains | Scheduler must not allocate, evict, crop, or infer a lower checkpoint. |
| HOST_ALLOC wait cursor and fairness | `Scheduler` restore reconciliation, preferably a small `HostAllocWakeArbiter` helper | enqueue/remove/select/commit-attempt over request IDs and generation snapshots | Cache generation must not become request-order authority. |
| Restore state semantics | `hicache_restore.py` plus scheduler event adapter | `DENIED_ALLOC` preserves positive-hit/non-miss semantics and carries wait metadata | No miss epoch/anchor/generation may be armed. |
| Telemetry | Existing restore/cache logging boundary | schema in section 8, joined by RID and attempt ID | Telemetry must not decide wake, fit, hit, or success. |

Dependency direction is:

```text
host pool/tree mutation
  -> cache-owned allocability generation
  -> read-only snapshot exposed by UnifiedRadixCache
  -> scheduler FIFO wake arbiter
  -> one normal full-span prefetch reissue
  -> existing cache/component allocators and evictors
  -> existing all-or-nothing hybrid finalization
```

There must be no callback from the host pool into scheduler request objects
and no scheduler-owned mirror that can diverge from the cache generation.

## 3. Normative data contracts

Names below are contractual interface roles; the implementer may select
repository-consistent concrete names if the change manifest maps them one to
one.

```python
HostPoolId = PoolName  # KV is the primary anchor pool

@dataclass(frozen=True)
class HostAllocabilitySnapshot:
    # Monotonic per process/cache instance. KV is always present.
    generation_by_pool: Mapping[HostPoolId, int]
    # Diagnostic levels only; never sufficient proof of fit.
    free_units_by_pool: Mapping[HostPoolId, int]
    evictable_units_by_pool: Mapping[HostPoolId, int]

@dataclass(frozen=True)
class HostAllocFailure:
    requested_primary_tokens: int
    required_aux_units: Mapping[HostPoolId, int]
    failed_domains: FrozenSet[HostPoolId]
    positive_hit_tokens: int
    sidecar_hit_pages: Mapping[HostPoolId, int]
    allocability_snapshot: HostAllocabilitySnapshot
    full_span_only: bool = True

@dataclass
class HostAllocWaitCursor:
    snapshot: HostAllocabilitySnapshot
    blocked_domains: FrozenSet[HostPoolId]
    requested_primary_tokens: int
    required_aux_units: Mapping[HostPoolId, int]
    fifo_sequence: int
```

Required semantic rules:

1. `generation_by_pool[KV]` is the authoritative primary-host allocability
   generation. It starts at a defined non-negative value per cache instance
   and only increases.
2. Auxiliary/Mamba pools use distinct generation members. A KV generation
   change is not an auxiliary-capacity fact.
3. `free_units` and `evictable_units` are telemetry/probe values. The existing
   allocator plus evictor remains the only fit authority.
4. `HostAllocFailure.failed_domains` must name the actual failed allocation
   domain. If exact attribution is unavailable, it must conservatively include
   every unresolved required domain; it must never report KV-only when an
   auxiliary allocation is unresolved.
5. The terminal transfer from cache to scheduler must preserve this metadata
   as a typed value or a schema-versioned equivalent. A bare terminal string
   is insufficient for generation-correlated acceptance.

## 4. Generation invariants and bump sites

### INV-GEN-1 — Monotonicity

For one cache instance and pool, `generation_after >= generation_before`.
Every qualifying mutation below changes it exactly once per completed
mutation batch, regardless of the number of requests awakened. Reset creates
a new cache-instance identity; it must not make an old wait cursor comparable
to the new instance.

### INV-GEN-2 — Completed primary free

After a direct primary-host free actually returns one or more KV units to the
allocator, the KV generation must advance. The bump occurs after the allocator
free returns successfully, not when eviction is planned. This includes host
values freed through `UnifiedRadixCache._free_values/_drain_host_frees` and
any direct `HostPoolGroup.free(..., pool=KV)` call in the in-scope path.

A no-op/empty free and an exception before completion do not bump. A batched
free may bump once with the aggregate returned units.

### INV-GEN-3 — Queued primary release drain

Enqueueing with `append_host_mem_release` does not bump. The KV generation
advances only after `_drain_release` has successfully returned one or more
queued KV units to `mem_pool_host`. Each drain batch bumps once and records
the aggregate returned units.

Auxiliary `_drain_extra_release` advances only the corresponding auxiliary
pool generation; it must not masquerade as a primary KV change.

### INV-GEN-4 — Lock release to evictability

`UnifiedRadixCache.dec_host_lock_ref` must advance the KV generation when and
only when the completed tree mutation changes the primary host-evictable leaf
set or primary evictable amount in a way that can expose a new eviction
candidate. Detection belongs at the tree mutation boundary: compare a cheap
before/after primary evictability summary, or extend `DecLockRefResult` with
explicit changed pools/deltas. A generic scan in scheduler is prohibited.

If the same lock release changes an auxiliary pool's independent evictability,
advance that pool's generation separately. Releasing a lock that leaves the
relevant evictable set/amount unchanged does not bump.

### INV-GEN-5 — Forbidden bump sources

No generation may advance because of:

- failed `alloc` or failed reclaim;
- prefetch reservation/ticket release by itself;
- entering or leaving a restore state;
- a generic scheduler/reconciliation pass;
- elapsed time, paced retry counters, or timeout;
- observing a free-level increase without owning the causal mutation;
- storage publish/miss generation, session generation, or Ready Horizon's
  `_ready_host_release_epoch`.

The existing Ready Horizon release epoch has different ownership and semantics
and must not be reused as this generation.

## 5. Restore state and retry protocol

### 5.1 Entry ordering

For a positive L3 hit whose complete staging allocation fails:

```text
positive sidecar-complete query
  -> full primary allocation/reclaim attempt fails
  -> no crop and no lower-frontier search
  -> release prefetch reservation/ticket
  -> release allocated primary/aux staging and anchor lock
  -> capture the post-cleanup allocability snapshot
  -> emit DENIED_ALLOC(genuine_miss=false, HostAllocFailure)
  -> WAIT_CAPACITY/HOST_ALLOC with HostAllocWaitCursor
```

The snapshot must include generation bumps caused by cleanup in the failed
attempt. Capturing before cleanup would allow the request to wake on its own
release and is a blocking defect.

The wait invariant is `prefetch reservation held == false`. The existing
restore timeout timestamp is preserved across no-op scheduler passes and
generation-triggered failed retries; it is not reset to extend T13.

### 5.2 Relevant-generation predicate

A waiter is eligible only when:

- it remains `WAIT_CAPACITY/HOST_ALLOC` and is not canceled/terminated;
- the ordinary prefetch/demand budget permits one issue;
- for every domain in `blocked_domains`, the current pool generation is
  strictly newer than the waiter's captured generation; and
- the current generation vector has not already received the arbiter's one
  global HOST_ALLOC grant.

Unblocked required pools are still allocated and validated on retry, but do
not need to advance merely because another domain failed. If a retry discovers
a new auxiliary failure, the next cursor names that auxiliary domain and
captures its current generation. Therefore a later KV-only generation cannot
re-arm an auxiliary-blocked hybrid request.

Generation advancement is an opportunity, not proof of fit. Do not restore
the old `available_size >= requested` precondition for HOST_ALLOC; it recreates
the circular wait by suppressing the eviction path.

### 5.3 Bounded FIFO arbiter

- Maintain a scheduler-owned FIFO sequence for HOST_ALLOC waiters. Enqueue a
  RID once; cancellation, timeout, success, or state departure removes it.
- For each distinct newly observed relevant generation vector, grant at most
  one candidate globally. Coalesced jumps are one opportunity at the latest
  snapshot, not one retry per skipped integer.
- Selection scans FIFO, removes stale entries, and chooses the first eligible
  waiter. A budget denial does not consume the generation opportunity.
- After a granted attempt, a failed waiter captures the post-attempt snapshot
  and moves to the FIFO tail. This supplies round-robin fairness across later
  generation changes. It may not immediately consume another grant generated
  by its own eviction/free work.
- Scheduler passes with no relevant generation change issue zero HOST_ALLOC
  retries. The legacy 121-pass/paced retry is not a HOST_ALLOC liveness path.
- T13 remains the bounded fail-safe if no relevant change occurs or repeated
  genuine opportunities remain insufficient.

### 5.4 Exactly one authoritative retry shape

One grant invokes the normal complete-frontier path once. For each required
pool, its allocator may perform at most:

```text
alloc(required-full-span)
  -> one existing bounded reclaim/evict attempt if permitted
  -> alloc(required-full-span) once more
```

The grant must not loop inside scheduler or cache. Any failure returns
`HostAllocFailure`, completes cleanup, records the post-attempt snapshot, and
parks again. Any direct free caused by the reclaim is incorporated into that
snapshot, preventing self-spin.

### 5.5 Hybrid success rule

Hybrid success requires all of the following for the same RID/attempt:

- the complete page-aligned KV frontier is allocated and fetched;
- every required auxiliary transfer, including Mamba trailing state, has its
  full required allocation and complete storage hit;
- existing all-or-nothing hybrid validation succeeds;
- no arbitrary crop or lower checkpoint was substituted.

Primary generation advancement, primary allocation success, or a positive KV
hit alone may not transition a hybrid request to READY. Auxiliary failure is
non-miss `HOST_ALLOC`, with exact failed-domain metadata and no busy loop.

## 6. Explicit prohibitions and non-goals

The implementation must not:

- crop a hybrid positive hit to arbitrary available KV capacity;
- classify allocation pressure as an L3 miss or arm sticky miss evidence;
- infer, query, or advertise a lower sidecar-complete checkpoint;
- convert the generation into a fit promise or capacity reservation;
- retain a prefetch reservation while parked;
- wake from time/poll count, generic passes, unrelated storage publication, or
  unrelated session generation;
- allow more than one global full-span HOST_ALLOC retry for one observed
  generation vector;
- weaken timeout, cancellation, all-or-nothing finalization, storage
  durability, or device-admission contracts;
- alter the 3090 branch/deployment, remote host, storage contents, persisted
  formats, or public API as part of this mechanism.

Performance tuning, lower-frontier discovery, cross-process wake delivery,
durable generations, fleet policy, and Ready Horizon redesign are explicit
non-goals and require fresh Task IDs.

## 7. Migration, compatibility, and reversibility

This mechanism introduces process-local transient state only. It must not
change storage keys, files, cache serialization, or remote protocols.

Recommended migration sequence:

1. Add cache-owned generation/snapshot and exact bump instrumentation with
   focused mutation tests.
2. Add typed allocation-failure metadata and post-cleanup snapshot ordering.
3. Add scheduler cursor/FIFO arbiter and replace only the HOST_ALLOC free-level
   wake predicate.
4. Add telemetry and deterministic regressions.
5. Run independent source/unit gates, then a separately authorized 3060 live
   test against a pinned revision.

The seam is the `UnifiedRadixCache.host_allocability_snapshot` interface and
the scheduler HOST_ALLOC branch. Rollback is a source revert at a quiescent
engine restart; no data rewrite is required. Mixed old/new objects in one
process are unsupported and must fail closed at initialization/schema check,
not silently fall back to free-only polling. Removal proof is absence of the
generation interface, cursor/arbiter state, and new telemetry symbols plus the
restored prior HOST_ALLOC behavior. Rollback restores the known T13 fallback
and therefore reopens the liveness defect without corrupting cache data.

## 8. Request-correlated telemetry contract

All records use a stable schema version, monotonic timestamp, wall timestamp,
worker/rank identity, `rid`, and `attempt_id`. Generation-change records may
use `rid=null` when no request caused the mutation; a causal RID/trace context
must be included when available.

| Event | Required fields |
| --- | --- |
| `host_allocability_change` | `schema`, `ts_mono_ns`, `ts_wall_ms`, `worker`, `rank`, `cache_instance_id`, `pool`, `generation_before`, `generation_after`, `cause` (`direct_free`, `queued_release_drain`, `lock_release_evictable`), `returned_units`, `evictable_before`, `evictable_after`, `causal_rid`, `trace_context` |
| `restore_host_alloc_wait` | common IDs, `state`, `reason`, `positive_hit_tokens`, `sidecar_hit_pages`, `requested_primary_tokens`, `required_aux_units`, `blocked_domains`, `captured_generations`, `free_units`, `evictable_units`, `prefetch_reservation_held` (must be false), `fifo_sequence`, `wait_started_mono_ns`, `deadline_mono_ns` |
| `restore_host_alloc_wake_decision` | common IDs, `decision` (`hold_no_generation`, `hold_budget`, `hold_global_grant_used`, `grant`, `drop_stale`), `captured_generations`, `current_generations`, `blocked_domains`, `fifo_sequence`, `generation_vector_id`, `global_grant_used`, `budget_available` |
| `restore_host_alloc_retry_result` | common IDs, `generation_vector_id`, `full_frontier_tokens`, `crop_attempted` (must be false), `lower_checkpoint_queried` (must be false), per-pool `required/free_before/evictable_before/alloc1/reclaimed/alloc2/free_after/evictable_after`, `failed_domains`, `terminal`, `genuine_miss` (must be false on alloc failure), `captured_generations_after`, `reservation_released` |
| `restore_hybrid_finalize` | common IDs, `kv_expected/fetched`, per-sidecar `expected/fetched`, `all_or_nothing`, `result`, `restore_state_after` |

Acceptance evidence must join query, allocation failure, generation change,
wake decision, retry, and final disposition by RID and attempt ID. Aggregate
counters alone are insufficient. Logs are observability, not wake authority.
Sensitive keys, token contents, and host addresses are excluded.

## 9. Deterministic regression matrix

Use fake primary and auxiliary pools/tree state with explicit counters and
call histories. The aligned primary hit is 54,976 tokens and the Mamba
sidecar is required. Tests must not rely on wall-clock polling.

| ID | Setup/action | Required oracle |
| --- | --- | --- |
| HAE-01 unlock-to-evict success | Primary free `< 54,976`; sufficient L3-backed primary leaf locked; first complete attempt fails and parks. Release the lock. | KV generation advances once only if evictable set/amount changes; one FIFO grant invokes one full allocator/evictor retry; complete KV+Mamba reaches READY; no crop/miss/lower checkpoint; reservation was absent while waiting. |
| HAE-02 direct-free success | No usable evictable leaf; direct primary tree eviction/free returns enough units. | Free completes before one KV bump; exactly one reissue at the full frontier succeeds; telemetry units and generations correlate. |
| HAE-03 queued-drain success | Enqueue a sufficient KV release, then drain it. | No enqueue bump; one post-free drain bump; one full retry and success. |
| HAE-04 empty/failed mutation | Empty free, failed alloc/reclaim, unchanged lock release, generic scheduler passes. | No generation bump and zero HOST_ALLOC retries. |
| HAE-05 no-change timeout | Hold free and evictability constant over many passes through T13. | Stable wait timestamp/cursor, zero retries, reservation false, exactly one timeout recompute, no 121-pass retry reuse. |
| HAE-06 insufficient change/self-spin | One small free/unlock advances generation but cannot satisfy full span. | At most one global retry for that vector; failed attempt snapshots post-reclaim generations and moves FIFO tail; subsequent passes do not retry; no crop/miss. |
| HAE-07 FIFO fairness | Three waiters, repeated insufficient then sufficient generation vectors. | One grant per vector; attempts rotate FIFO after failure; canceled/timed-out entries are removed; no waiter repeatedly consumes opportunities while another eligible waiter starves. |
| HAE-08 budget interaction | Relevant generation advances while prefetch budget is unavailable, then budget frees without another host change. | Generation opportunity is retained while budget-blocked; exactly one grant occurs when budget permits; waiter holds no reservation itself. |
| HAE-09 primary-only change with aux blocked | Mamba allocation is the failed domain; advance only KV generation. | No wake, no hybrid success, no miss, no spin. Advance Mamba generation after real release/unlock; one full retry may proceed. |
| HAE-10 aux race after KV wake | Initial failed domain is KV; KV generation advances; retry allocates KV but Mamba loses a race and fails. | Atomic cleanup of all staging; result identifies Mamba; post-cleanup vector captured; later KV-only changes do not wake; all-or-nothing success only after relevant Mamba change. |
| HAE-11 generation coalescing | Advance relevant generation multiple times before reconciliation. | One opportunity at latest vector, not N immediate retries; all telemetry retains before/after causal records. |
| HAE-12 cleanup ordering | Failed retry performs eviction/free and releases aux/anchor during cleanup. | New wait cursor equals the post-cleanup vector; the request cannot wake on its own cleanup. |
| HAE-13 reset/instance boundary | Wait cursor from cache instance A is presented after instance B initializes. | Cursor is incomparable/stale and fails closed; no numeric-generation false wake. |
| HAE-14 genuine miss separation | Query returns zero or below-threshold genuine result. | Existing miss/recompute semantics remain; allocability generation does not reclassify or wake it. |
| HAE-15 KV-only compatibility | Positive KV-only hit under pressure. | Same generation/FIFO bound and full-span retry apply without requiring absent auxiliary domains; no regression to safe existing KV-only behavior. |

Required evidence classes:

- source-level unit tests for bump inclusion/exclusion and snapshot ordering;
- deterministic scheduler/cache integration tests for HAE-01 through HAE-15;
- static audit proving all in-scope primary free paths and
  `dec_host_lock_ref` route through the bump contract;
- request-correlated log fixture/schema validation;
- separately authorized live 3060 reproduction showing at least one
  unlock/free-triggered full KV+Mamba success and no self-spin;
- independent reviewer reconciliation against the exact implementation
  revision. Performance results cannot substitute for correctness evidence.

## 10. Gate acceptance criteria

The implementation gate may ACCEPT only if all are true:

1. The orchestrator/design authority has accepted this contract or a pinned
   superseding revision.
2. The repository-required full Pattern Intake and Novel Mechanism declaration
   are complete, separately accepted through the existing authority gate, and
   pinned by path/digest. Section 11 does not self-approve or waive them.
3. Every in-scope direct primary free, queued KV drain, and effective host-lock
   release has static and runtime evidence for exactly the required bump; all
   forbidden sources have negative evidence.
4. HOST_ALLOC captures the post-cleanup cursor, releases its reservation, and
   does not arm miss evidence or reset the timeout.
5. There is at most one global full-span retry per newly observed relevant
   generation vector, with deterministic FIFO fairness and no same-vector or
   self-generated spin.
6. The allocator/evictor, not scheduler or generation, remains fit authority.
7. KV and each required auxiliary domain are independently represented;
   hybrid READY requires complete KV+sidecar allocation/fetch and existing
   all-or-nothing validation.
8. No arbitrary crop, miss classification, lower-checkpoint inference, or
   generic scheduler/paced retry is present on this path.
9. HAE-01 through HAE-15 pass at the pinned revision, telemetry schemas join
   by RID/attempt, and a reviewer accepts the implementation with no blocking
   finding.
10. Live 3060 evidence is required before a runtime-liveness claim. No 3090,
    durability, fleet, or performance claim is inferred.

## 11. Pattern Intake / Novel Mechanism declaration

```yaml
schema_version: 1.0.0-proposed
task_id: ARCH-20260909-HOST-ALLOC-EPOCH
epoch: 20260909-P4
classification: NOVEL_MECHANISM
mechanism_id: NM-HOST-ALLOC-EPOCH-1
status: proposed
required_decision_owner: orchestrator/design-authority
full_pattern_intake_path: PENDING_FRESH_TASK
novel_declaration_path: this-document#11
acceptance_decision_id: PENDING
```

### Classification and nearest local analogues

This is not EXEMPT: it changes state-machine admission, allocator wake
ownership, ordering, fairness, failure behavior, and test oracles.

The inspected repository contains useful local analogues but no accepted
task-specific pattern artifact:

| Analogue | Useful property | Why it does not fit directly | Disposition |
| --- | --- | --- | --- |
| Ready Horizon `CausalEpochs` and per-RID negative cursor | Causal change invalidates parked negative evidence; generic passes do not. | `_ready_host_release_epoch` is synthesized from free-level growth, lacks lock-to-evictability signal, and belongs to Ready Horizon rather than restore allocation. | Partial reuse of monotonic cursor concept only. |
| T15 demand-restore ticket | Bounded concurrency for a wake reissue. | It is backup-frontier authority, not host allocability or multi-pool failure attribution. | Adapt bounded-ticket shape in scheduler arbiter. |
| Buffer-mode parked-hit FIFO | FIFO allocation fairness and no overtaking. | Cache-mode positive-hit allocation has already revoked and released its reservation; retaining the operation would change ownership/lifecycle. | Reuse FIFO policy, not retained-operation semantics. |
| Existing full allocation + one eviction + allocation | Bounded allocator authority. | No causal wake exists to re-enter it after an evictability-only change. | Adopt unchanged as retry body. |
| Existing hybrid all-or-nothing finalization | Prevents partial KV-only hybrid success. | It validates transfer completion after issue; it does not govern wake-domain generations. | Adopt and add per-pool wait attribution. |

Novelty is triggered because the composition creates a new cross-boundary
contract between tree lock release, host-pool free completion, scheduler
admission, and multi-pool fairness. No inspected accepted gate defines that
authority/failure boundary.

### Atomic novel invariants

`NM-INV-1` through `NM-INV-10` correspond respectively to INV-GEN-1 through
INV-GEN-5, post-cleanup wait capture, relevant-domain wake, one-vector/one-
grant fairness, full-span-only retry, and hybrid all-or-nothing success. They
remain **proposed** until accepted by the orchestrator/design authority.

### Failure model and oracle

- Preconditions: positive complete L3 frontier; transient primary or auxiliary
  staging failure; one or more waiting requests.
- Concurrency boundary: free/unlock mutations may occur between scheduler
  passes and allocator retries; requests compete for one released capacity
  opportunity.
- Unsafe outcomes: permanent circular wait despite reclaimable material,
  thundering herd, same-request self-spin, reservation deadlock, arbitrary
  crop, false miss, or KV-only hybrid success.
- Transient state: cache-instance generation vector, request wait cursor, FIFO
  sequence, and last-granted vector. There is no new durable state.
- Fail-safe: remain parked without reservation until a relevant generation or
  T13; on retry failure atomically clean up and snapshot post-attempt state.
- Oracle: allocator call history, authoritative tree/pool before-after state,
  restore state, reservation ledger, and complete KV+Mamba finalization. The
  test model and telemetry observe these owners and do not become product
  truth.

### Alternatives

| Alternative | Decision rationale |
| --- | --- |
| Keep free-level polling | Rejected: cannot observe lock release to evictability and recreates the confirmed circular wait. |
| Retry every scheduler pass or every N passes | Rejected: unrelated to causal change; permits self-spin and load amplification. |
| Wake all waiters on any free/unlock | Rejected: thundering herd and no per-domain hybrid correctness. |
| Reserve capacity while waiting | Rejected: waiter can block the capacity change needed for its own progress. |
| Search/crop to a lower frontier | Rejected: no sidecar-complete lower checkpoint is evidenced; violates scope and safety guard. |
| Retain failed positive-hit operation in cache FIFO | Not selected in this contract: materially changes cache-mode lifecycle and reservation ownership. |
| Proposed generation vector + one FIFO grant | Selected for consideration: causal, bounded, reversible, and keeps allocator/finalizer authority unchanged. |

### Pattern Intake governance gap

The target worktree contains only an EXEMPT artifact and does not contain the
full pattern/testing corpus or task templates referenced by the project-level
contract. The authorized write set also excludes creation of the required
`storage/review/gates/pattern-intake/<task>/pattern-intake.md` and separate
novel declaration. Therefore this section records the mandatory novelty
classification and design rationale but **is not a completed full Pattern
Intake**. G1/G2 implementation admission remains blocked until the
orchestrator dispatches a fresh Task ID to search the complete pinned corpus,
disposition every relevant stable ID, build atomic pattern-to-test rows, and
write/pin the conforming artifacts. This governance gap does not make the
architecture shape incomplete; it prevents implementation authority from
being inferred from this document.

## 12. Open decisions and risks

| ID | Item | Recommendation | Gate effect / reversibility |
| --- | --- | --- | --- |
| OD-1 | Concrete generation owner (`HostPoolGroup` versus controller wrapper) | Prefer the lowest common mutation boundary that sees successful free and can expose per-pool snapshots; keep scheduler read-only. | Must be settled in accepted implementation shape. Reversible interface seam. |
| OD-2 | Tree evictability change signal | Extend `DecLockRefResult` or `_update_evictable_leaf_sets` to report changed pools without O(N) scheduler scans. | Blocking if exact change cannot be proven. No persistence impact. |
| OD-3 | Cross-thread visibility | Use existing owner-thread serialization if proven; otherwise atomic/locked increments. | Blocking race concern until tested. |
| OD-4 | Typed terminal compatibility | Replace/extend terminal strings atomically in producer and consumer with schema assertion. | Mixed in-process versions fail closed; source rollback only. |
| R-1 | One global grant can defer a fit-capable later waiter after an insufficient first candidate. | FIFO rotation plus next causal generation; T13 bounds waiting. Any more permissive policy requires a new authority decision and stampede evidence. | Accepted trade-off only if orchestrator approves. |
| R-2 | High mutation rate can create many generation records. | Coalesce retries, not causal mutation counters; telemetry may be sampled only if request-correlated acceptance events remain complete. | Operational, non-correctness risk. |
| R-3 | Missing complete pattern corpus in target worktree. | Fresh Pattern Intake task before G1/G2. | Implementation admission blocked; architecture report remains done. |

Extra corpus, design, implementation, test, deployment, remote, storage, or
3090 work requires a fresh Task ID.

Status: `done` for the proposed architecture gate contract; acceptance remains
with the orchestrator and existing gate owners.
