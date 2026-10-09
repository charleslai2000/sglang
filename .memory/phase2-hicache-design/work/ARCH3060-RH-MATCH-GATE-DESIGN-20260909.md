ENTRY: ACCEPT

status: done
task_id: T3060-RH-MATCH-GATE-DESIGN-20260909
orchestration_epoch: 20260909-rh-ab43
role: architect
source_repository: /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt
source_branch: 3060-12g-qwen35-4b
source_revision: f629d4e2c19eb74571b4154438fd651ce24ff53b
artifact_repository: /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache
architect_recommendation: ACCEPT_WITH_REVISED_PATTERN_AND_NOVEL_GATES
decision_authority: orchestrator_and_existing_gate_owners

# 3060 Ready Horizon current-match gate contract

## Decision

The minimal safe correction is to give an RH refill invocation one current,
one-shot prefix-match preparation for each potentially stageable frontier
request before `ReadyHorizonView.staging_eligible` is computed, and to consume
that exact preparation in the subsequent RH issue call. The lower issue path
must not call `Req.init_next_round_input` a second time when the one-shot
preparation is valid.

The preparation is gated behind the existing causal `epoch_event` /
`should_refill` decision, uses `cow_mamba=False`, is valid only within the
current scheduler-owned `_ready_horizon_pass`, and fails closed if request
identity or the resolved node changed. A failed validation performs one normal
rematch in `_prefetch_kvcache_impl`; it must never issue from stale/default
request fields.

This recommendation preserves the accepted exclusive initial-issue boundary:
RH-ON remains queue-first and RH-owned, while RH-OFF remains eager-before-queue.
It does not authorize implementation and does not amend or self-accept the
existing Pattern Intake, Novel Mechanism, G-ARCH, G-IMPL, or reviewer gates.

## Evidence boundary

### Observed facts

1. The inspected branch is `3060-12g-qwen35-4b` at
   `f629d4e2c19eb74571b4154438fd651ce24ff53b`. It is checked out in the sibling
   worktree named above; the requested report resides in the shared phase task
   memory.
2. `Scheduler._get_new_batch_prefill_raw` calls `check_hicache_events`, then
   `_reconcile_restore_states`, then `_ready_horizon_pass` before
   `SchedulePolicy.calc_priority` and before the admission loop's
   `req.init_next_round_input(self.tree_cache)`.
3. `_ready_horizon_pass` currently calls `_ready_horizon_views` immediately.
   `_ready_horizon_views` calls `_restore_potential_for`, which reads
   `req.last_host_node`, `req.host_hit_length`, and
   `req.full_untruncated_fill_ids`.
4. Fresh `Req` construction initializes `last_node` and `last_host_node` to
   `None`, host-hit lengths to zero, and `full_untruncated_fill_ids` has not yet
   been refreshed for the next round. `Req.reset_for_retract` clears
   `last_node` but does not clear `last_host_node`; therefore a retracted
   request can carry a stale host anchor unless it is rematched.
5. The current RH issue path eventually calls
   `_prefetch_kvcache_impl`, which invokes
   `req.init_next_round_input(self.tree_cache, cow_mamba=False)` before its
   storage gate. This is too late for the preceding RH eligibility decision.
6. `Req.init_next_round_input(..., cow_mamba=False)` refreshes fill IDs,
   computes the same SWA/key-limit/positional-override match geometry used by
   issue, calls `tree_cache.match_prefix`, and writes the complete match result
   back to the request.
7. `cow_mamba=False` prevents the Mamba component's destination allocation,
   eviction-for-allocation, and deferred COW assignment. The inspected Mamba
   finalizers allocate and possibly evict only when `cow_mamba` is true.
8. Prefix matching is not literally read-only. The unified tree match refreshes
   component LRU/access metadata, can split a matched node, and applies emitted
   cache actions. Those are existing match semantics. Calling the same match
   twice would duplicate work and can change replacement behavior.
9. The live final RH-ON report at the same revision completed 5/5 HTTP calls,
   but every RID emitted only `rh_preadmission.v1 exclude
   reason=no_restore_potential`; there was no RH issue, ready-stage,
   ready-host, or joinable RH admission. The report therefore classified the
   ready-host rate as not computable, not zero.
10. The paired RH-OFF report observed one 54,976-token KV storage query and one
    Mamba sidecar hit per RID, demonstrating recoverable storage material for
    that workload. It is evidence of the missed eligibility opportunity, not
    proof that every candidate can physically stage.
11. The accepted RH architecture, Pattern Intake, and Novel Mechanism gates
    are pinned to `f629d4e2c1` and preserve exclusive RH-ON initial ownership,
    RH-OFF eager order, typed attempt fencing, allocator/HOST_ALLOC ownership,
    hybrid all-or-nothing readiness, and Mamba durability boundaries.
12. `MambaComponent.drive_host_eviction` owns the existing write-back
    flush-before-evict behavior. No RH symbol owns or may bypass that path.

### Assumptions to verify in implementation review

- Queue mutation, matching, RH planning, issue, and admission remain serialized
  on the scheduler owner. If this is false, the one-shot ticket requires an
  atomic cache-generation/freshness mechanism and this design must be revised.
- No callback between preparation and its immediate issue mutates the request's
  token identity. The ticket validation below makes violation fail closed.
- Root may be a legitimate storage-query origin when a current match resolves
  it and `prefetch_gate_ok` accepts it. “Real storage anchor” therefore means a
  current-match-proven, extant, gate-valid anchor, not necessarily a non-root
  node. An uninitialized/default root-like value is never sufficient.

### Proposal

The proposed symbols and contracts below are recommendations for orchestrator
and gate-owner acceptance. They are not observed implementation facts.

## Ownership and dependency boundaries

| Concern | Owner after change | Contract |
| --- | --- | --- |
| Causal refill timing | `Scheduler._ready_horizon_pass` / `ReadyHorizonPolicy` | Match preparation runs only after `should_refill` permits a real refill evaluation. |
| Match geometry and cache semantics | Existing `Req.init_next_round_input` and cache `match_prefix` | Reuse exact existing geometry; `cow_mamba=False`; do not implement a parallel tree walker. |
| Preparation lifetime | Scheduler-local one-shot value | Valid only inside one `_ready_horizon_pass`; never persisted on `Req`, across passes, or across admission. |
| RH eligibility | Existing `ReadyHorizonView` and `_restore_potential_for` | Construct the view only after a current match exists for a potentially stageable request. |
| Initial issue claim | Existing `_claim_prefetch` / `_prefetch_kvcache` | Claim still precedes reservation, allocation, eviction, restore-state mutation, and I/O. Match discovery is not an issue claim. |
| Storage anchor truth | Existing tree/cache gate | Issue only from a current-match-proven extant anchor that passes existing buffer/cache-mode gate semantics. |
| Allocation, eviction, I/O, finalize | Existing Unified cache/controller | No authority transfer to RH; all full-span KV+aux checks remain authoritative. |
| Mamba durability | Existing Mamba component | `cow_mamba=False` preparation allocates/evicts no Mamba slot; all later host eviction continues through flush-before-evict. |
| Admission | Existing admission loop | Its `init_next_round_input(self.tree_cache)` remains authoritative and may perform the separate admission-time Mamba COW. |

Required direction:

```text
RH-ON queued request
  -> causal refill gate
  -> one current non-COW prefix preparation
  -> ReadyHorizonView / existing policy gates
  -> existing prefetch claim
  -> consume one-shot preparation (or one safe fallback rematch)
  -> existing storage/allocation/finalization
  -> separate admission-time match/COW
```

The admission-time match is not a duplicate of the RH staging match: it has a
different owner and purpose, can occur after asynchronous storage/cache
changes, and is the point where Mamba COW is permitted.

## Concrete symbol contract

### New scheduler-local value

Add an immutable private value in `scheduler.py` (exact spelling may vary if
mapped one-to-one in the implementation manifest):

```python
@dataclass(frozen=True)
class _ReadyHorizonPreparedMatch:
    req: Req
    rid: str
    pass_seq: int
    enqueue_seq: int | None
    session_generation: int | None
    retraction_count: int
    fill_object_id: int
    fill_len: int
    output_len: int
    extra_key: object
    cache_salt: object
    last_device_node: object
    last_host_node: object
```

The value is capability-like proof that the scheduler performed the match in
this pass. It is not persisted and contains no allocator handle or lock.

### New/changed helpers

```python
Scheduler._rh_match_candidate(req: Req) -> bool
Scheduler._prepare_ready_horizon_match(req: Req, pass_seq: int)
    -> _ReadyHorizonPreparedMatch | None
Scheduler._rh_prepared_match_valid(req: Req, prepared, pass_seq: int) -> bool

Scheduler._prefetch_kvcache(
    req,
    *,
    origin: HiCachePrefetchOrigin,
    demand_restore: bool = False,
    prepared_match: _ReadyHorizonPreparedMatch | None = None,
) -> PrefetchIssueResult
```

`prepared_match` has no public/default trust semantics. It may suppress the
normal `init_next_round_input` only when all of these are true:

- `origin is HiCachePrefetchOrigin.READY_HORIZON`;
- object identity, RID, current pass sequence, enqueue sequence, session
  generation, retraction count, fill object identity/length, output length,
  `extra_key`, and `cache_salt` match;
- request match fields still equal the prepared anchors;
- both non-null anchors resolve under `tree_cache.node_exists` (root counts as
  extant only when returned by this current match);
- the existing `prefetch_gate_ok` check is executed again immediately before
  storage issue; buffer-mode device-anchor fallback remains exactly where it
  is today.

If validation fails, `_prefetch_kvcache_impl` discards the ticket and performs
exactly one ordinary `init_next_round_input(..., cow_mamba=False)` before
continuing. A bare Boolean skip flag, a RID-only cache, or a request-persistent
“initialized” marker is forbidden.

### `_ready_horizon_pass` order

Refactor only enough to place expensive matching after the causal gate:

1. Return immediately when RH is off or no cache controller exists.
2. Compute `frontier_reqs`, `now`, and `CausalEpochs`. The current
   `_ready_horizon_epochs(frontier_reqs, views, cc)` does not read `views`; its
   unused argument should be removed or passed an empty value without changing
   epoch semantics.
3. Run the existing `epoch_event` and `should_refill`; return unchanged when no
   refill is due.
4. For each live frontier request for which the existing state funnel could
   stage (`NONE`, `MISS_RECOMPUTE`, `WAIT_CAPACITY/PREFETCH_BUDGET`, or
   `WAIT_CAPACITY/DEVICE_QUOTA` with no host hit), perform exactly one current
   `req.init_next_round_input(self.tree_cache, cow_mamba=False)` and retain its
   one-shot ticket. Do not prepare `RESTORING`, READY, terminal, active-prefetch,
   FRONTIER, BACKUP_PENDING, REVALIDATE, or HOST_ALLOC requests.
5. Build `_ready_horizon_views` from the now-current request fields and execute
   the existing negative-cache, headroom, reserve, physical/speculative budget,
   and watermark policy unchanged.
6. For each `plan.to_issue`, pass that RID's ticket to `_prefetch_kvcache`.
   `_prefetch_kvcache_impl` consumes it or falls back once as specified above.
7. Drop all tickets on every exit. They must not reach the next pass or the
   admission loop.

Preparation failure must fail closed for RH staging, emit
`match_prepare_failed`, and leave the request for the ordinary scheduler's
existing handling. It must not reuse stale fields, synthesize a root anchor,
transition restore state, or acquire an issue claim.

## Lifecycle contract

### Fresh requests

Fresh RH-ON requests are appended without eager issue as already accepted.
Their first causally due RH evaluation refreshes fill IDs and matches once with
`cow_mamba=False`. Eligibility is computed only afterward. A current match
that proves an extant root and passes the existing root query gate is allowed;
an absent/stale/default field is not.

### Already initialized requests

Do not rely on old request fields for an RH issue. A potentially stageable
request receives a new current-pass preparation when refill is due. The old
fields are overwritten by the normal match result. Non-stageable/active/READY
requests are not rematched by RH. Any later admission performs its existing
admission-time rematch and Mamba COW.

### Retracted requests

`reset_for_retract` clears `last_node` but can leave `last_host_node` stale.
Every retracted request that re-enters the RH stageable funnel must therefore
receive a fresh preparation regardless of a non-null old host anchor. Ticket
identity includes `retraction_count`. The preparation uses `_refresh_fill_ids`
through `init_next_round_input`, thereby rebuilding the retracted input shape.
It must not free, allocate, clear, or COW Mamba state. Existing retraction and
admission owners remain responsible for pool lifecycle.

### Chunked requests

The active `Scheduler.chunked_req` is outside `waiting_queue` and therefore
outside the RH frontier; RH must never prepare or stage it. Its existing
`init_next_round_input()` and `add_chunked_req` order remains unchanged. If a
formerly chunked request is fully retracted and returned to `waiting_queue`, it
is treated as a retracted waiting request and gets a new ticket; no chunk
snapshot may be reused.

### Changed or terminal requests

Finished/aborted requests and requests with active attempts are excluded
without preparation. Any token, generation, enqueue, retraction, key/salt, or
anchor change invalidates the ticket. Invalid tickets cause one fallback match,
not an issue from stale state.

## Atomic invariants

| ID | Invariant |
| --- | --- |
| `RH-MG-I1` | RH eligibility is never computed from an uninitialized or stale/default anchor for a potentially stageable request. |
| `RH-MG-I2` | A causally due RH evaluation performs at most one prefix match per candidate before its initial issue; a validation failure permits exactly one explicit fallback rematch. |
| `RH-MG-I3` | `cow_mamba=False` preparation leaves `mamba_pool_idx`, `mamba_cow_src_index`, and `mamba_needs_clear` unchanged and calls neither Mamba allocation nor Mamba eviction. |
| `RH-MG-I4` | Match preparation creates no restore attempt, reservation, storage query, state transition, or readiness marker. Existing match-owned LRU/split/cache-action semantics are allowed and measured. |
| `RH-MG-I5` | An RH issue requires both a valid current preparation (or completed fallback rematch) and the existing successful active-attempt claim. |
| `RH-MG-I6` | “Known anchor” means returned by the current match, extant at consumption, and accepted by existing cache/buffer gate semantics; non-null/default request storage is insufficient. |
| `RH-MG-I7` | RH-OFF executes the same eager-before-append call sequence and never constructs an RH preparation ticket. |
| `RH-MG-I8` | RESTORING, active-attempt, HOST_ALLOC, REVALIDATE, FRONTIER, BACKUP_PENDING, READY, terminal, and active chunked requests receive no RH match or duplicate issue. |
| `RH-MG-I9` | Retracted candidates cannot reuse a pre-retraction match; `retraction_count` and a current preparation fence stale anchors. |
| `RH-MG-I10` | Admission-time match/COW remains separate; RH tickets cannot suppress it or escape into `PrefillAdder`. |
| `RH-MG-I11` | RH does not call an allocator or eviction API. Any host eviction remains cache-owned, and Mamba write-back victims still pass through flush-before-evict. |
| `RH-MG-I12` | Telemetry observes preparation and consumption but cannot make an anchor known, clear a negative, issue, wake HOST_ALLOC, or mark READY. |

## Failure model and containment

| Failure | Required behavior |
| --- | --- |
| No preparation before view | Contract assertion/test failure; candidate must not be called `no_restore_potential` from default fields. |
| Match returns no extant anchor | Exclude `anchor_unknown`; zero issue/attempt/allocation/I/O. |
| Ticket stale before issue | Emit invalidation reason, perform one ordinary non-COW rematch, rerun existing gate, then issue or hold. |
| Match raises | Fail closed for RH, emit bounded diagnostic, no stale issue. Existing scheduler error policy remains authoritative. |
| First candidate's issue mutates tree before later candidate | Later ticket validation fails if its node disappeared and triggers one rematch. No long-lived topology claim is inferred. |
| Mamba allocator/COW change during preparation | Blocking defect; no issue acceptance even if request completes. |
| Preparation causes direct RH eviction call | Blocking ownership defect. Cache-internal actions from the one normal match remain cache-owned. |
| RH issue declines or alloc fails | Existing typed state, negative-cache, HOST_ALLOC FIFO/generation, timeout, and retry contracts apply unchanged. |
| Mamba host pressure | Existing cache component must spare/flush non-durable checkpoint before eviction; RH adds no bypass. |

## Rejected alternatives

1. **Call `init_next_round_input` before views and again in
   `_prefetch_kvcache_impl`.** Rejected: duplicates matching/LRU/topology work
   and can change replacement behavior.
2. **Prepare at enqueue and reuse later.** Rejected: queue residence permits
   cache topology, storage durability, token generation, retraction, and
   session identity to change; freshness is unproven.
3. **Use a Boolean `match_prepared=True` or RID-only cache.** Rejected: no
   identity, generation, or anchor freshness proof and easy misuse by RH-OFF or
   demand retry.
4. **Move `SchedulePolicy.calc_priority` before RH.** Rejected: changes policy
   timing/order, matches the whole queue, and prevents RH from operating in
   some current capacity-early-return conditions.
5. **Add a second pure tree walker.** Rejected for the minimal fix: it would
   duplicate Full/SWA/Mamba consensus and key-limit semantics and create a
   larger cache interface. Existing match is safe only under the bounded
   non-COW, one-shot contract above; it is not labeled globally read-only.
6. **Treat root/default as automatically eligible.** Rejected: provenance,
   extant-node, and gate checks are required. A current matched root remains a
   legitimate origin only where the existing cache contract permits it.
7. **Allow RH preparation to perform Mamba COW to save admission work.**
   Rejected: speculative candidates would allocate/evict device Mamba state
   before admission and violate ownership and cleanup boundaries.
8. **Reuse preparation across passes.** Rejected: introduces cache-version and
   invalidation authority not present in the accepted design.

## Telemetry and measurement contract

Add bounded observational schema `rh_match_prepare.v1` (sampled consistently
with existing RH decision logging) with:

```text
rid, enqueue_seq, pass_seq, session_generation, retraction_count,
restore_state_before, result={prepared,skipped,ineligible,failed,invalidated},
reason, fill_len, device_hit_tokens, host_hit_tokens,
anchor_kind={unknown,root,node,buffer_device_fallback}, anchor_id,
anchor_exists, anchor_gate_ok, cow_mamba=false,
match_duration_us, match_count_for_pass, fallback_rematch,
mamba_pool_idx_changed, mamba_cow_src_changed, mamba_needs_clear_changed
```

Join existing `rh_preadmission.v1` and `rh_stage.v2` by `(rid, pass_seq,
decision_id, attempt_id)` and add `match_prepared=true|false` plus
`anchor_kind`. Logging failure changes no decision.

Required measurements:

- RH preparation-to-issue match count: expected `1` per issued fresh candidate;
  `2` only with an explicitly logged invalidation/fallback.
- `anchor_known_rate = known_current_anchor / potentially_stageable_frontier`;
  missing is not zero.
- `rh_issue_rate = issued / prepared_and_policy_eligible` with decline reasons
  retained separately.
- `ready_before_admission_rate = accepted_ready_host attempts observed before
  their matching admission / accepted_ready_host attempts`; do not divide by
  all enqueued requests or report `0/0` as zero.
- Mamba safety deltas during preparation: allocator availability, alloc/evict
  call counts, and the three request COW fields must be unchanged.
- Existing flush-before-evict oracle remains zero lost/non-durable evictions;
  compare its event sequence unchanged with RH OFF and ON.
- Runtime outcome: HTTP completion, timeout, wall/e2e latency, KV hit pages,
  Mamba sidecar units, host-allocation waits/retries, hybrid finalize result,
  and fatal/OOM markers, all joined by RID/attempt. Performance is reported as
  observed paired evidence, not attributed from one run.

## Implementation contract

Authorized future implementation scope should be limited to:

- `python/sglang/srt/managers/scheduler.py` for one-shot preparation, causal
  ordering, ticket validation/consumption, and telemetry;
- a focused test file under `3090-dev/` and, if package-backed fixtures are
  available, registered scheduler tests.

No change is recommended to `schedule_batch.py`, cache tree traversal,
allocator, Unified cache finalization, Mamba component, persistence format,
HOST_ALLOC generations/FIFO, or remote/deployment files. If implementation
requires one of those files, stop and obtain a fresh architecture dispatch;
that is evidence the minimal boundary does not fit.

The implementation manifest must map actual spellings to the symbols above,
pin the descendant revision, and demonstrate that only the normal
`Req.init_next_round_input(..., cow_mamba=False)` call moved into preparation
and was consumed by RH issue. Formatting/type checks and dependency-backed
tests are required when available; missing dependencies remain explicit.

## Test contract

### Deterministic unit/contract cases

1. `test_rh_fresh_req_prepares_before_restore_potential`: fresh `None` anchors,
   seeded L3 KV+Mamba chain; view sees current host anchor and becomes eligible.
2. `test_rh_issue_consumes_prepared_match_once`: instrument
   `match_prefix`; exactly one call from causal refill through issue, one claim,
   one storage query, one attempt.
3. `test_rh_no_refill_event_does_not_match`: unchanged epochs before safety
   interval; zero preparation and zero issue.
4. `test_rh_current_root_is_known_but_default_is_not`: uninitialized/default
   anchor excludes; a current match resolving root proceeds only when existing
   `prefetch_gate_ok` permits root querying.
5. `test_rh_prepared_ticket_identity_change_falls_back_once`: mutate each of
   token length, session generation, retraction count, key/salt, and anchor;
   exactly one fallback rematch and no stale issue.
6. `test_rh_deleted_anchor_falls_back_once`: first candidate changes/deletes a
   later candidate's node; later candidate rematches or holds without stale
   dereference.
7. `test_rh_prepare_non_cow_mamba_no_alloc_or_evict`: seeded matched Mamba
   state; allocator alloc/evict counters and request COW fields unchanged.
8. `test_rh_admission_still_performs_mamba_cow`: after accepted staging,
   admission retains its normal match/COW and cleanup behavior.
9. `test_rh_retracted_req_discards_stale_host_anchor`: stale non-null
   `last_host_node`, cleared `last_node`, incremented `retraction_count`; current
   rematch determines eligibility and ticket identity.
10. `test_rh_active_chunked_req_never_prepared`: `self.chunked_req` is not in
    the frontier and its established chunk initialization order is unchanged.
11. `test_rh_retracted_chunked_requeue_gets_fresh_match`: once returned to the
    waiting queue, no old chunk snapshot/ticket is reused.
12. `test_rh_nonstageable_states_do_not_match`: RESTORING, active attempt,
    READY, HOST_ALLOC, REVALIDATE, FRONTIER, BACKUP_PENDING, terminal; zero RH
    match and issue.
13. `test_rh_prepare_failure_fails_closed`: no issue, attempt, reservation,
    readiness, or stale root fallback; explicit failure reason.
14. `test_rh_off_eager_order_and_match_count_unchanged`: byte/AST call-order
    fixture plus behavioral spy against the pre-change OFF path; no RH ticket
    or RH preparation event.
15. `test_rh_does_not_wake_host_alloc_or_crop_hybrid`: retain the
    54,976-required/21,057-free/zero-evictable fixture; Mamba-only generation
    cannot wake, KV generation permits only the existing FIFO full-span retry.
16. Existing claim/stale-terminal, hybrid-discard, ready-host auxiliary,
    negative-cache, causal-event, and telemetry join suites must remain green.
17. Existing Mamba flush-before-evict tests must remain green with identical
    event ordering in RH OFF and ON fixtures.

### Hash-pinned bounded runtime acceptance

Run fresh RH-OFF and RH-ON processes at the exact implementation descendant,
using the prior five-way 55K protocol, same model/storage seed, frontier 8,
speculative fraction 0.6, max-running-requests 1, and 180-second client bound.
Record process/deploy revision, args, health, seed counts, pre/post log offsets,
and fatal scans.

Acceptance is correctness-first:

- OFF emits the established eager origin before queue and no RH preparation;
- ON emits a current preparation for each potentially stageable frontier RID;
- no ON candidate is excluded as `no_restore_potential` solely because its
  match was uninitialized;
- every ON initial issue has one preparation, one attempt, and one storage
  query, with no duplicate eager origin;
- every accepted KV+Mamba finalize emits attempt-correlated READY before its
  matching READY admission; discarded/rejected material never does;
- no preparation-time Mamba alloc/evict/COW delta and no flush-before-evict
  violation occurs;
- HOST_ALLOC, timeout, and physical failure remain accurately classified and
  are not counted as match-gate failure;
- missing joins are reported as missing/not-computable.

HTTP completion and latency differences are reported but are not gate-passing
substitutes for the invariant evidence above.

## Pattern Intake and Novel Mechanism implications

This is not EXEMPT. It changes semantic ordering, the scheduler-to-match
interface, stale-anchor handling, the harness/oracle, and the point at which a
mutable cache match can occur. Before G1/G2 implementation dispatch, the
existing `PATTERN-INTAKE-20260909-RH-PREADMISSION.md` must be revised at the
new corpus/implementation baseline with:

- the observed final ON/OFF defect evidence;
- positive pattern: existing scheduler/policy prefix preparation with
  `cow_mamba=False`;
- anti-patterns: default-field eligibility, duplicate match, persistent or
  Boolean skip markers, pre-admission Mamba COW, RH-owned eviction;
- bug IDs for stale retraction anchor and no-restore-potential exclusion;
- mappings `RH-MG-I1` through `RH-MG-I12` to the tests above;
- explicit unchanged flush-before-evict and HOST_ALLOC authority evidence.

The accepted Novel Mechanism declaration also requires an amendment or a new
gate-owner-approved revision. The new one-shot prepared-match capability is a
trusted consumption/freshness boundary, and existing `match_prefix` has
observable cache mutation despite `cow_mamba=False`. That is a new failure
boundary not covered by the accepted exclusive-issuer declaration. The novel
update must include the one-pass lifetime, identity validation, fallback
rematch, allowed match-owned mutations, no-Mamba-allocation oracle, and
rollback/removal path. It must not claim that current matching is pure.

The existing architecture gate must then be repinned to the accepted design
revision before implementation review. Independent coder, tester, and reviewer
dispatches remain mandatory; this architect artifact cannot accept their work.

## Migration, rollback, reversibility, and risk

No persistent data, wire protocol, storage key, or mixed-version migration is
required. Rollout is process drain/restart only; hot RH mode changes with live
requests remain unsupported. Rollback is drain/restart with RH disabled or
revert the scheduler-only descendant; RH-OFF provides the compatibility path.
One-shot tickets disappear with the stack frame and require no cleanup or
state migration.

Primary risks are match-owned cache mutations before issue claim, multi-
candidate anchor invalidation, extra match cost on causal refill, and accidental
suppression of admission-time Mamba COW. The bounded lifetime, post-causal
placement, validation/fallback, per-pass match counters, and negative Mamba
oracles make those risks observable and reversible. A new pure-peek cache API
could remove match mutations but is deliberately deferred because it expands
cache/component interfaces and duplicates consensus logic.

## Artifacts

- This gate-contract/design plus implementation/test contract:
  `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/ARCH3060-RH-MATCH-GATE-DESIGN-20260909.md`
- Read-only inputs: source revision `f629d4e2c1`; accepted RH architecture,
  Pattern Intake, Novel Mechanism, and review artifacts; final RH-ON and RH-OFF
  reports; prior RH causal diagnosis.

## Evidence

- Source symbols inspected: `Req.init_next_round_input`,
  `Req.reset_for_retract`, `Scheduler._ready_horizon_pass`,
  `Scheduler._ready_horizon_views`, `Scheduler._restore_potential_for`,
  `Scheduler._prefetch_kvcache_impl`,
  `Scheduler._get_new_batch_prefill_raw`,
  `SchedulePolicy.calc_priority`, `match_prefix_for_req`,
  `UnifiedRadixCache.match_prefix`,
  `UnifiedTreeCore._match_post_processor`,
  `MambaComponent.finalize_match_result_in_cache`, and
  `MambaComponent.drive_host_eviction`.
- Runtime evidence inspected:
  `TEST3060-RH-FINAL-ON-TRACE-20260909.md` and
  `TEST3060-RH-FINAL-OFF-TRACE-20260909.md`.
- Gate/review evidence inspected:
  `ARCH3060-RH-GATE-ACCEPT-20260909.md`,
  `ARCH3060-RH-PIN-F629-20260909.md`,
  `ARCH-20260909-RH-PREADMISSION.md`,
  `NOVEL-MECHANISM-20260909-RH-PREADMISSION.md`,
  `PATTERN-INTAKE-20260909-RH-PREADMISSION.md`,
  `REVIEW3060-RH-FINAL-JOIN-20260909.md`, and
  `TEST3060-RH-VIEW-TYPE-20260909.md`.

## Summary

Recommend a scheduler-only, causal-gated, one-shot non-COW match preparation
whose result is consumed by the RH issue path. It repairs eligibility before
RH policy, avoids the duplicate issue-time match, fences fresh/retracted/
changed requests, preserves separate admission-time Mamba COW, leaves RH-OFF
and HOST_ALLOC unchanged, and cannot bypass Mamba flush-before-evict. Current
matching is conditionally safe for this use but is not literally read-only.

## Followups

- Orchestrator: accept, amend, or reject this recommendation and dispatch a
  fresh Pattern Intake/Novel/architecture gate revision before implementation.
- Fresh coder task after gate acceptance: implement only the scheduler-local
  scope and produce an exact changed-symbol manifest.
- Fresh tester and reviewer tasks: execute the deterministic and hash-pinned
  contracts independently and bind evidence to the descendant revision.

## Open issues

- Scheduler single-owner serialization between preparation and issue is
  strongly implied by source but requires explicit implementation-review
  confirmation.
- The term “real storage anchor” is resolved here as current-match-proven and
  gate-valid, allowing a current matched root where existing storage semantics
  allow root-origin queries. If product intent requires a non-root durable
  anchor, the orchestrator must amend the contract; that would reject valid
  root-origin full-prefix storage queries and is not recommended from current
  evidence.
- Package-backed RH tests previously lacked `orjson`; dependency-complete test
  availability remains to be established by the future tester.
- No post-fix live evidence exists. Performance, fairness, deployment, and
  terminal acceptance remain open.

Extra implementation, gate mutation, test execution, deployment, or runtime
work requires a fresh Task ID.
