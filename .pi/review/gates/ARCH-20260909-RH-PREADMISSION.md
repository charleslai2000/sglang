ENTRY: ACCEPT

# Ready Horizon direct-request pre-admission architecture contract

```yaml
contract_version: 1.1.0-accepted
task_id: ARCH3060-RH-ARCH-20260909
orchestration_epoch: 20260909-rh-ab18
role: architect
status: accepted
gate_verdict: ACCEPT
architect_recommendation: ACCEPT_IMPLEMENTATION_DESIGN
decision_authority: orchestrator_and_existing_gate_owners
corpus_revision: 82ab235606233160701b15f657a71794cfd29a30
implementation_revision: f629d4e2c19eb74571b4154438fd651ce24ff53b
implementation_authority: architecture_design_only
implementation_admission: AUTHORIZED_FOR_INDEPENDENT_IMPLEMENTATION_REVIEW
```

## 1. Decision and scope

This contract proposes one RH-ON-only ownership transfer. Direct requests are
made visible in `Scheduler.waiting_queue` before any initial storage prefetch,
and the existing `Scheduler._ready_horizon_pass` becomes the sole owner of the
initial speculative-prefetch decision. It does not add a second issue path.

RH-OFF retains the current behavior and order in
`Scheduler._add_request_to_queue`: ordinary initial `_prefetch_kvcache(req)`
before append to `waiting_queue`. Demand retries, storage budget/allocation,
eviction, transfer, hybrid finalization, host-allocability epochs, timeout, and
admission remain under their current owners.

This artifact is design evidence, not implementation acceptance. The
orchestrator must accept, amend, or reject it. No source change is authorized.

## 2. Evidence boundary

### Observed facts

1. `Scheduler._add_request_to_queue` currently calls
   `_prefetch_kvcache(req)` before appending `req` to `waiting_queue`.
2. A prefill pass runs `check_hicache_events`,
   `_reconcile_restore_states`, and `_ready_horizon_pass` before ordinary
   admission construction.
3. `ReadyHorizonPolicy._state_funnel` admits `NONE`, `MISS_RECOMPUTE`, and a
   narrow `WAIT_CAPACITY` subset, while excluding `RESTORING`, `HOST_ALLOC`,
   `FRONTIER`, and `REVALIDATE`.
4. `_ready_horizon_pass` examines the configured waiting-queue frontier and
   obtains material eligibility through `_restore_potential_for(req)`. No
   direct-HTTP prediction signal is required by the observed policy.
5. In the RH-ON trace, eager enqueue had already moved requests to
   `RESTORING` or `WAIT_CAPACITY/PREFETCH_BUDGET` before RH could stage them.
   The only source-correlated `ready_stage` event occurred after all client
   deadlines.
6. Every RH-ON and RH-OFF RID had a 54,976-token KV+Mamba storage hit. RH-ON
   returned one HTTP 200 and four timeouts; RH-OFF returned two HTTP 200s and
   three timeouts. The supplied evidence does not prove an RH-ON performance
   improvement.
7. Later `HOST_ALLOC` waits were real allocability failures: 54,976 KV units
   required, 21,057 free, zero evictable. No KV generation advanced, so
   auxiliary-only generation changes correctly did not wake hybrid waits.
8. Explicit RH eligibility and `ready_host` events do not exist in the
   reviewed path. Their absence makes the requested rate not computable; it
   is not evidence of zero.
9. Runtime/source identity was not hash-pinned.

### Proposals awaiting acceptance

- Transfer RH-ON initial-prefetch authority from enqueue to the existing RH
  pass.
- Require an origin-tagged, request-local active-attempt claim before any
  prefetch resource side effect.
- Add bounded decision, stage, readiness, and admission telemetry joined by
  `(rid, attempt_id)`.

### Assumptions

- Queue mutation, RH planning, and initial issue remain serialized by the
  scheduler owner. If implementation evidence shows concurrency, the attempt
  claim must be atomic under that owner's synchronization boundary.
- Ready Horizon is process-start configuration; hot toggle is out of scope.
- Scope is the Unified HiCache KV+Mamba path exercised by the supplied RTX
  3060 reports. HiRadix, persistence formats, distributed coordination, and
  deployment are unchanged.

## 3. Boundaries and ownership

| Concern | Owner | Required interface/invariant |
| --- | --- | --- |
| Direct enqueue | `Scheduler._add_request_to_queue` | RH-OFF issues then appends; RH-ON appends only. HTTP handlers never issue or predict prefetch. |
| RH ordering/selection | `Scheduler._ready_horizon_pass` plus `ReadyHorizonPolicy` | Existing frontier, state, potential, negative-cursor, headroom/reserve, physical-budget, and speculative-budget gates remain authoritative. |
| Issue deduplication | Existing request-local HiCache restore-control state | One active attempt acquired before reservations or I/O. Telemetry and RID log scans are not authority. |
| Storage work | Existing `_prefetch_kvcache` to `UnifiedRadixCache` path | Existing budget, allocation, eviction, transfer, and cleanup remain authoritative. |
| Demand retry | Existing `_reconcile_restore_states` path | Explicit demand origin; only after the previous attempt is terminal. |
| Hybrid readiness | Existing KV+Mamba finalizer | All required material remains all-or-nothing. A telemetry event cannot create readiness. |
| Admission | Existing scheduler admission path | Runs after the cycle's RH decision and cannot issue a second initial prefetch. |
| Telemetry | Scheduler/restore event adapters | Observational only; logging failure cannot change product behavior. |

Required dependency direction:

```text
direct request
  -> Scheduler._add_request_to_queue
  -> RH-OFF: sole eager issue -> queue append
  -> RH-ON: queue append only
  -> check_hicache_events
  -> _reconcile_restore_states
  -> _ready_horizon_pass (sole RH-ON initial issue owner)
  -> _prefetch_kvcache (claim + existing cache path)
  -> existing finalize/restore state
  -> ordinary admission
```

No second allocator, transfer engine, reservation ledger, restore machine, or
storage-to-HTTP callback is introduced.

## 4. Exact symbol contract

Existing symbols with fixed roles:

- `Scheduler._add_request_to_queue`
- `Scheduler._ready_horizon_pass`
- `Scheduler._reconcile_restore_states`
- `Scheduler._prefetch_kvcache`
- `Scheduler._restore_potential_for`
- `ReadyHorizonPolicy._state_funnel`
- `UnifiedRadixCache` existing prefetch/allocation/finalization path

Required semantic types at the scheduler/restore boundary:

```python
class HiCachePrefetchOrigin(Enum):
    EAGER_RH_OFF = "eager_rh_off"
    READY_HORIZON = "ready_horizon"
    DEMAND_RETRY = "demand_retry"

class HiCachePrefetchIssueStatus(Enum):
    ISSUED = "issued"
    HELD = "held"
    SKIPPED_ACTIVE = "skipped_active"
    SKIPPED_STATE = "skipped_state"
    FAILED_BEFORE_ISSUE = "failed_before_issue"

@dataclass(frozen=True)
class HiCachePrefetchIssueResult:
    status: HiCachePrefetchIssueStatus
    attempt_id: int | None
    origin: HiCachePrefetchOrigin
    reason: str
    state_before: str
    state_after: str
```

The existing request-local HiCache restore-control record receives:

```python
prefetch_attempt_seq: int = 0
active_prefetch_attempt_id: int | None = None
active_prefetch_origin: HiCachePrefetchOrigin | None = None
last_rh_decision_fingerprint: tuple | None = None
```

The active-attempt fields are correctness state. The decision fingerprint is
telemetry-only and cannot affect policy or issue.

The internal issue signature becomes origin-explicit, with no default:

```python
Scheduler._prefetch_kvcache(
    req,
    *,
    demand_restore: bool,
    origin: HiCachePrefetchOrigin,
) -> HiCachePrefetchIssueResult
```

Add scheduler-owned helpers:

```python
Scheduler._claim_hicache_prefetch_issue(req, origin) -> int | None
Scheduler._release_hicache_prefetch_issue(req, attempt_id, terminal_reason) -> None
```

The claim checks allowed restore state and absence of an active attempt,
increments `prefetch_attempt_seq`, and installs the active attempt before any
budget reservation, allocation, or I/O. Release compares `attempt_id`; a stale
completion cannot clear a newer claim. If repository naming requires a
spelling change, the implementation manifest must map it one-to-one.

## 5. Normative control flow

### RH-OFF unchanged

When `enable_ready_horizon` is false,
`Scheduler._add_request_to_queue(req)` preserves:

```python
_prefetch_kvcache(
    req,
    demand_restore=False,
    origin=HiCachePrefetchOrigin.EAGER_RH_OFF,
)
waiting_queue.append(req)
```

The explicit origin and claim are internal hardening. Issue timing relative to
append, budget class, state transitions, retry/error behavior, admission, and
responses must be trace-equivalent to the pinned pre-change RH-OFF fixture.
No RH decision event is emitted.

### RH-ON queue-first pre-admission

When `enable_ready_horizon` is true,
`Scheduler._add_request_to_queue(req)` performs:

```python
waiting_queue.append(req)
# no _prefetch_kvcache call in this branch
```

The next normal prefill cycle retains:

```text
check_hicache_events
_reconcile_restore_states
_ready_horizon_pass
ordinary admission construction/evaluation
```

For a newly appended `NONE` request, reconciliation must not perform an
unclassified initial prefetch. `_ready_horizon_pass` applies every existing RH
gate. For each `plan.to_issue` entry it calls exactly:

```python
_prefetch_kvcache(
    req,
    demand_restore=False,
    origin=HiCachePrefetchOrigin.READY_HORIZON,
)
```

It records an issued stage only when the result is `ISSUED`. `HELD`,
`SKIPPED_ACTIVE`, and `SKIPPED_STATE` are non-issue decisions. Every path that
can produce `can_run=True` for a waiting request must follow that cycle's RH
decision. A fully passing candidate gets one stage issue before admission; an
excluded candidate gets a reason and no issue. There is no same-pass eager
fallback.

### Demand retry

Existing capacity/host-allocation retry calls:

```python
_prefetch_kvcache(
    req,
    demand_restore=True,
    origin=HiCachePrefetchOrigin.DEMAND_RETRY,
)
```

A new retry attempt is allowed only after the preceding attempt is terminal
and its matching claim has been released. Existing demand-budget,
host-allocability epoch, and full allocation/eviction semantics are unchanged.

## 6. Atomic invariants

1. **INV-RH-1 Exclusive initial owner:** RH-OFF initial origin is only
   `EAGER_RH_OFF`; RH-ON initial origin is only `READY_HORIZON`. A request can
   never observe both for its initial attempt.
2. **INV-RH-2 Claim before effect:** one active attempt maximum. A second
   caller returns `SKIPPED_ACTIVE` without budget, reservation, state, counter,
   allocation, or I/O mutation.
3. **INV-RH-3 Queue visibility:** under RH-ON, a direct request is queued in
   `NONE` before its first RH decision and has not been made `RESTORING` by
   enqueue.
4. **INV-RH-4 No RESTORING duplicate:** repeated RH passes, admission scans,
   and event polls cannot issue while an active attempt is nonterminal.
5. **INV-RH-5 Policy completeness:** authority transfer bypasses none of the
   frontier, state, potential, negative, headroom/reserve, physical-budget, or
   speculative-budget gates.
6. **INV-RH-6 Non-issue purity:** exclusion/hold performs no resource or
   restore-state side effect and does not advance the attempt sequence.
7. **INV-RH-7 Correlated cleanup:** success, miss, allocation denial, transfer
   error, timeout, abort, and retirement release resources first and then only
   the matching claim.
8. **INV-RH-8 Authority preservation:** RH permission proves neither storage
   hit nor host fit. Existing allocator and all-required-material finalizer
   remain authoritative.
9. **INV-RH-9 RH-OFF equivalence:** request ordering, issue count/timing,
   budget class, state/error behavior, and admission semantics are unchanged
   when disabled.
10. **INV-RH-10 Telemetry is observational:** missing telemetry invalidates
    evidence but cannot alter product state or be interpreted as a zero.

## 7. Telemetry

### `rh_preadmission.v1`

Emit `evt=rh_preadmission_decision schema=rh_preadmission.v1` for the first
frontier observation, every decision-fingerprint change, and every issue.
Required fields:

```text
rid, request_enqueue_seq, rh_pass_seq, decision_id,
frontier_rank, frontier_n, restore_state_before, wait_reason_before,
active_prefetch_attempt_id, staging_eligible, restore_potential,
negative_cache_blocked, negative_cursor, causal_epoch,
headroom_tokens, reserve_floor_tokens,
physical_budget_limit_tokens, physical_budget_used_tokens,
speculative_budget_limit_tokens, speculative_budget_used_tokens,
decision, reason, issue_origin, attempt_id
```

`decision` is `issue|hold|exclude`. Closed reasons are `issued`,
`outside_frontier`, `state_funnel`, `no_restore_potential`, `negative_cache`,
`reserve_floor`, `physical_budget`, `speculative_budget`, `active_attempt`, and
`request_terminal`. Fields not evaluated after an earlier gate are `null`, not
zero. The fingerprint covers frontier bucket, state/wait, potential, negative
cursor, causal epoch, headroom/reserve bucket, budget bucket, decision, and
reason. It may suppress only an identical repeat. No prediction field is
required because prediction is not an observed authority.

### `rh_stage.v2`

Version the existing marker as `evt=ready_stage schema=rh_stage.v2` with:

```text
rid, decision_id, attempt_id, issue_origin, demand_restore,
restore_state_before, restore_state_after, result, reason,
frontier_rank, headroom_tokens, reserve_floor_tokens,
physical_budget_used_tokens, speculative_budget_used_tokens
```

`result=issued` is emitted only after exactly one reservation/I/O submission
is accepted. Holds/skips remain decision events.

### `rh_ready_host.v1` and admission join

On existing all-required-material transition to `READY`, emit
`evt=ready_host schema=rh_ready_host.v1`:

```text
rid, attempt_id, issue_origin, completed_kv_tokens,
required_aux_pools, completed_aux_units, restore_state_before,
restore_state_after, finalize_result, ready_monotonic_ns
```

The first subsequent admission record includes:

```text
rh_decision_id, hicache_prefetch_attempt_id, hicache_prefetch_origin,
ready_host_observed, admission_monotonic_ns, can_run
```

Join by `(rid, attempt_id)` and derive `ready_host_before_admission` from event
order. The bounded-run rate is:

```text
denominator = distinct RIDs whose first complete RH decision has
              staging_eligible=true and decision=issue
numerator   = denominator RIDs with matching ready_host before first
              can_run=true admission
rate        = numerator / denominator
```

Any missing mandatory decision, attempt, readiness, admission, or ordering
field makes the rate `not_computable`, never zero.

## 8. Failure and rollback

1. Before accepted issue: release partial reservation, clear only the matching
   claim, restore pre-issue state, return `FAILED_BEFORE_ISSUE`, and continue
   the existing safe recompute/admission path. Never eager-fallback in the
   same pass.
2. After accepted issue: retain existing miss, allocation-denial, transfer,
   timeout, and abort transitions. Release resources before the matching
   claim and preserve retry metadata.
3. Claim inconsistency: fail closed against duplicate issue, emit an invariant
   error, and rely on existing timeout/recompute rather than speculative
   reissue.
4. Telemetry failure: product behavior continues, but acceptance evidence for
   that run fails.
5. Retirement: verify no active claim/reservation remains; stale completions
   cannot mutate a retired or newer attempt.
6. Operational rollback: restart with RH disabled, restoring the eager-before-
   append branch. No durable format, seed, or migration exists.
7. Source rollback is local to scheduler/restore control and telemetry. Mixed
   in-process versions are unsupported; restart is the boundary.

## 9. Test acceptance

| ID | Oracle | Required result |
| --- | --- | --- |
| RH-G01 | Static/call-site audit | Every `_prefetch_kvcache` call has explicit origin; initial owners are exactly OFF enqueue or ON RH pass; retries are demand-only. |
| RH-G02 | Pinned deterministic RH-OFF fixture | One eager issue occurs before append; issue timing, budget class, state/error, and admission trace are equivalent to pre-change. |
| RH-G03 | Five direct enqueues, RH-ON, frontier 8, generous budgets, fake complete KV+Mamba hits | All queue in `NONE`; every fully passing candidate gets one RH issue before admission; zero eager issues. |
| RH-G04 | Repeated RH passes during active transfer | One reservation and I/O submission per RID; later passes exclude active/`RESTORING`; no duplicate. |
| RH-G05 | State and policy table | Exact results for `NONE`, `MISS_RECOMPUTE`, allowed wait, excluded states, potential, negative cursor, reserve, and both budgets; every exclusion is side-effect free. |
| RH-G06 | Budget hold then causal release | Hold creates no claim/resource; later eligible pass creates one attempt; no same-pass fallback. |
| RH-G07 | Fault injection at claim/reservation/allocation/submission | Exact cleanup; stale attempt cannot clear newer claim; at most one submission. |
| RH-G08 | Success/miss/denial/error/timeout/abort/retirement matrix | Claims/resources release once; only all-material success emits joined `ready_host`. |
| RH-G09 | Telemetry parser/fingerprint fixture | Fields/null rules and bounded suppression hold; issue never suppressed; incomplete join yields `not_computable`. |
| RH-G10 | 54,976-required/21,057-free/zero-evictable KV+Mamba fixture | Allocation may still fail; auxiliary-only epoch does not wake KV+Mamba; later demand retry is full-span and non-spinning. |
| RH-G11 | Independent bounded RH-OFF/RH-ON replay with pinned deploy/source hash | Terminal outcomes and health/storage invariants; OFF has no RH decision path; ON has complete joins and no duplicate attempt per RID. |
| RH-G12 | Independent implementation review | No prediction requirement, second allocator, host-epoch relaxation, hybrid partial success, storage-format change, or unrelated source change. |

RH-G11 proves mechanism and observability, not performance. Because supplied
RH-ON aggregate success regressed, any latency/throughput claim requires a
separate performance gate with repetitions, thresholds, and variance policy.

## 10. Risks and reversibility

| Risk | Mitigation and gate effect |
| --- | --- |
| RH-ON requests outside the frontier defer initial I/O. | Test frontier progression and benchmark separately. Flag-off rollback is immediate. |
| Leaked claim suppresses retries. | Lifecycle/retirement matrix; blocking correctness finding. |
| Claim cleared before resources permits overlap. | Resources-first cleanup order; blocking correctness finding. |
| Decision logs recreate high-volume admission logs. | Fingerprint suppression, while first/change/issue records remain mandatory. |
| Causal runtime lacks deploy hash. | Pin source and deployed artifact in implementation/live evidence. |
| Physical host shortage still dominates. | Keep allocator and epoch semantics unchanged; classify allocation separately from RH correctness. |
| Request-local fields alter in-process interface. | Ephemeral, scheduler-owned, non-serialized; source-only rollback. |

## 11. Pattern Intake and Novel Mechanism gate

This is not EXEMPT: it changes issue authority, queue-relative ordering,
failure behavior, telemetry interfaces, and test oracles. No completed task-
specific Pattern Intake or accepted Novel Mechanism declaration was supplied.
The authority transfer itself creates a new composition boundary.

G1/G2 implementation admission is therefore blocked until a fresh Task ID:

- pins corpus revision/scope and dispositions for stable, anti-pattern,
  bug-derived, harness/test, benchmark, deferred, and missing IDs;
- maps each atomic invariant to an adopted/adapted pattern and exact test;
- supplies a Novel Mechanism declaration covering authority, failure model,
  oracle, alternatives, migration, rollback, and removal;
- obtains the existing gate owners' verdicts.

Architecture dispositions for that intake:

| Alternative | Disposition |
| --- | --- |
| Keep eager issue and also call RH | Prohibited: duplicate issue/reservation authority and RH still sees `RESTORING`. |
| Relabel eager issue as RH staging | Not adopted: bypasses queue frontier/order and RH policy ownership. |
| Remove eager issue in both modes | Not adopted: changes the required RH-OFF baseline. |
| RH-ON queue-first with sole RH issue | Recommended: policy applies once and rollback is flag-off/source revert. |

This document and any Novel Mechanism declaration do not approve themselves.

## 12. Handoff and open decisions

The architect recommends this contract for orchestrator consideration because
it addresses the evidenced ordering gap with a single issue owner while
preserving allocator/finalizer authority. Acceptance remains pending.

Before implementation dispatch, the orchestrator must:

1. Accept, amend, or reject the authority transfer and attempt-claim contract.
2. Supply and accept Pattern Intake and Novel Mechanism artifacts.
3. Confirm the concrete existing owner type for request restore-control fields;
   any name mapping must preserve the exact semantics above.
4. Decide separately whether performance improvement is an acceptance claim.

Status: `done` for this proposed architecture artifact. Implementation
admission and architecture acceptance remain pending with their designated
owners. Extra work requires a fresh Task ID.

## 13. Final architecture acceptance — 2026-09-09

The proposal-stage statements in sections 1, 2, 11, and 12 are historical and
superseded for the exact final implementation revision
`f629d4e2c19eb74571b4154438fd651ce24ff53b`. The corpus remains separately
pinned to `82ab235606233160701b15f657a71794cfd29a30`.

### Verdict and admission

**G-ARCH/RH pre-admission design verdict: ACCEPT.** The final source satisfies
the accepted ownership, interface, failure-containment, and reversibility
contract sufficiently to authorize entry into independent implementation
review. This gate does not approve its own implementation, substitute for the
reviewer, accept deployment, or claim performance.

### Final implementation manifest

The seven-commit range `82ab235606..f629d4e2c1` changes nine files:

| File | Accepted architectural role |
| --- | --- |
| `python/sglang/srt/managers/scheduler.py` | RH mode routing, sole-owner call placement, attempt claim/result lifecycle, terminal fence, telemetry joins, discarded-hybrid no-ready transition, and raw-frontier-`Req` to `ReadyHorizonView` policy join. |
| `python/sglang/srt/managers/schedule_batch.py` | Ephemeral scheduler-owned request fields only; no serialized format. |
| `python/sglang/srt/managers/scheduler_components/hicache_restore.py` | Origin/status enums and frozen typed issue-result boundary. |
| `python/sglang/srt/mem_cache/unified_radix_cache.py` | Existing lower owner carries attempt-correlated terminal/completion evidence and authoritative KV/aux finalization result. |
| Five `3090-dev` tests | Queue/origin, gate-skip, lifecycle/stale fence, joined readiness, hybrid discard, raw-request-to-policy-view mapping, and neighboring restore/storage oracles. |

Accepted symbol mapping: contract
`_claim_hicache_prefetch_issue`/`_release_hicache_prefetch_issue` maps one-to-one
to final `_claim_prefetch`/`_release_prefetch_claim`; contract
`HiCachePrefetchIssueResult` maps to final frozen `PrefetchIssueResult`.
Attempt IDs are monotonic request-local strings rather than integers; this is
accepted because identity, ordering, correlation, and stale fencing semantics
are preserved. `EAGER_DISAGG_PREFILL` is an explicit compatibility origin for
the pre-existing disaggregated path and does not create a second NULL-mode
owner.

### Invariant and test-evidence matrix

| Contract invariant | Observed final source | Evidence | Decision |
| --- | --- | --- | --- |
| `INV-RH-1/3/9` sole owner, queue visibility, OFF equivalence | RH-ON appends without issue; RH pass uses `READY_HORIZON`; RH-OFF calls `EAGER_RH_OFF` before append | `test_rh_on_enqueue_is_queue_first_and_rh_owned`, `test_rh_off_enqueue_preserves_eager_order_and_origin`, explicit-origin scan | ACCEPT; full final-revision OFF live trace remains open |
| `INV-RH-3` typed policy input | Raw frontier requests are joined by RID to their `ReadyHorizonView` before policy-only eligibility/state fields are read | `test_ready_pass_joins_raw_frontier_req_to_policy_view`; tester `TEST3060-RH-VIEW-TYPE-20260909.md` | ACCEPT |
| `INV-RH-2/4/6` claim before effect, no active duplicate, non-issue cleanup | `_claim_prefetch` precedes `_prefetch_kvcache_impl`; `SKIPPED_ACTIVE` bypasses it; only `ISSUED` retains claim | Gate-pass/skip regression, active-claim harness, RH unit fixture | ACCEPT |
| `INV-RH-7` correlated cleanup | `_release_prefetch_claim` requires expected attempt; lower terminal records carry attempt; stale terminal returns before transition | `test_stale_release_cannot_clear_newer_claim` and independent lifecycle/terminal harnesses | ACCEPT |
| `INV-RH-8` lower authority and all-material readiness | Cache finalizer owns actual KV/aux counts and accepted/discarded result; scheduler turns only accepted completion into READY/`ready_host` | Aux completion test, storage durability tests, discard/reject terminal test | ACCEPT |
| `INV-RH-10` observational joined telemetry | Decision fingerprint affects emission only; decision/stage/ready/admission schemas carry required correlation and state fields | Required-event-field AST test and source inspection | ACCEPT for architecture/interface; final live evidence open |
| RH-G10 authority preservation | No changed HOST_ALLOC generation, FIFO grant, allocator policy, Mamba allocation authority, or persistent schema | Seven-commit scope audit and focused neighboring tests | ACCEPT within authorized architecture scope |

### Reviewer-block reconciliation

The `7831d45dd4` tester BLOCK is retained as evidence: it found mandatory
ready-host auxiliary fields were null. Revision `6881529acb` moved actual
required pools and completed units from the authoritative finalizer into the
attempt-correlated completion handoff. The `6881529acb` tester BLOCK is also
retained: it found discarded all-or-nothing hybrid material still transitioned
to READY. Revision `67b39b5aca` consumes `finalize_result` before state
transition, maps `discarded`/`rejected` to `DENIED_SHORT` with recompute state
`NONE`, and suppresses `rh_ready_host.v1`. The final focused dependency-free
test covers accepted versus discarded/rejected behavior.

The descendant `f629d4e2c1` fixes the observed RH startup type mismatch without
changing the accepted ownership or policy semantics: `_ready_horizon_pass`
maps raw frontier requests to their corresponding typed policy views before
reading `staging_eligible` and `state`. Independent tester report
`TEST3060-RH-VIEW-TYPE-20260909.md` (SHA-256
`f85a535ddba7cf88760a7c157cc171041f140c1186a102501fb24af83d7996b7`)
records ACCEPT and a passing 6/6 dependency-free contract run at the bound
revision.

### Dependencies, risks, and open evidence

- Dependency direction remains scheduler → typed restore/cache interface →
  lower finalizer result → scheduler admission. No reverse callback or shared
  allocation authority was introduced.
- `orjson` is unavailable, so package-backed RH unit and scheduler-feed runs
  are not evidence for this revision. Existing dependency-free/source-loaded
  focused tests do not replace that missing integration evidence.
- No final-revision live 3060/deploy-hash evidence exists. Earlier traces are
  baseline/diagnostic inputs only. RH-G11, operational acceptance, and any
  latency/throughput/fairness claim remain unresolved.
- Rollback remains reversible through drain/restart with RH disabled; no
  durable data migration or mixed-version protocol exists. Hot mode flip is
  unsupported.
- Independent implementation reviewer verdict remains required. Blocking
  reviewer findings override this admission and require a fresh Task ID.
