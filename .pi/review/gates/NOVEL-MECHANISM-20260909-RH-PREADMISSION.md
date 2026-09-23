# Novel Mechanism Declaration: RH-ON Pre-Admission Prefetch Authority

```text
task_id: ARCH3060-RH-NOVEL-20260909
orchestration_epoch: 20260909-rh-ab18
status: accepted design gate; implementation authorized for independent review
gate_verdict: ACCEPT
corpus_revision: 82ab235606233160701b15f657a71794cfd29a30
implementation_revision: f629d4e2c19eb74571b4154438fd651ce24ff53b
repository_branch: 3060-12g-qwen35-4b
```

## 1. Decision requested

The orchestrator and existing gate owners are asked to decide whether to accept
the following new scheduling boundary:

> While Ready Horizon is enabled (`RH-ON`), the RH pre-admission stage is the
> sole semantic owner of the one initial prefetch issue for each selected
> request/stage generation. The ordinary eager enqueue path must not issue a
> second initial prefetch. While RH is disabled (`RH-OFF`), the existing eager
> ordinary-prefetch behavior remains unchanged.

This declaration supplies design evidence to G-ARCH/G-SYSTEM/G-TECH/G-ALGO and
later implementation gates. It does not approve itself, authorize source
changes, replace the required Pattern Intake, or accept an implementation.

## 2. Evidence and trigger

### Observed facts

The following facts come only from the designated reports:

1. `DBG-20260909-RH-NO-STAGING.md` reports that
   `Scheduler._add_request_to_queue` invokes `_prefetch_kvcache(req)` before
   appending the request to `waiting_queue`. The later scheduler RH pass thus
   observes an already changed restore state.
2. The RH state funnel excludes `RESTORING` and `HOST_ALLOC`. In the bounded
   five-request RH-ON run, there was no pre-deadline `ready_stage`; the only
   observed RH issue occurred after client terminal bounds. One successful
   request restored through the ordinary eager path, not RH.
3. Calling both paths is unsafe: it can duplicate I/O, reservations, state
   transitions, and budget consumption.
4. The later `HOST_ALLOC` waits were real KV allocability failures: 54,976 KV
   units were required, 21,057 were free, and none were evictable. The
   host-allocation epoch mechanism did not lose a wake; it correctly held
   waiters because the required KV generation did not advance.
5. `SCOUT-20260909-RH-PATTERN-CORPUS.md` pins the searched repository to
   `82ab235606233160701b15f657a71794cfd29a30`. It identifies reusable RH
   patterns for typed state, event-gated refill, stable READY-first ordering,
   RH-OFF no-op behavior, and separation from HOST_ALLOC authority.
6. The scout found no accepted RH-specific mechanism assigning exactly one
   pre-admission issue owner, no canonical full Pattern Intake artifact for
   this task, and no current-HEAD live 3060 RH acceptance result.

### Assumptions requiring later verification

- The reviewed local source behavior represents the implementation to be
  changed. The debugger found matching runtime schemas but no cryptographic
  deploy-hash identity.
- RH mode is fixed for a scheduler process or changed only through a
  drain/restart transition. An in-place mode flip with active requests is not
  assumed safe.
- “Exactly one” applies to the initial pre-admission issue for one logical
  request/stage generation. A causally later demand retry after a completed,
  denied, or revoked attempt is a distinct operation and remains governed by
  restore/HOST_ALLOC contracts.

## 3. Why known patterns do not fully fit

The corpus contains the pieces but not their required composition:

- `RH-IMP-001` through `RH-IMP-004` establish RH policy inputs, event-gated
  refill, READY-first ordering, and the scheduler integration point.
- `RH-IMP-005` and `RH-IMP-006` keep typed restore/HOST_ALLOC handling and
  physical full-span allocation in their current owners.
- `RH-ANTI-001` through `RH-ANTI-003` reject staging `HOST_ALLOC`, per-pass
  retry spin, miss conflation, arbitrary crop, and auxiliary-only wake.
- `RH-TST-001` through `RH-TST-005` offer candidate harnesses and neighboring
  oracles, but none proves exclusive initial-issue ownership across enqueue
  and the RH pass.

Adopting the existing enqueue pattern leaves RH unable to stage direct
requests before admission. Adopting the existing RH pass without changing
enqueue creates two possible initial issuers. Exclusive ownership therefore
adds a scheduler authority and failure boundary not represented by one known
accepted pattern. That is the novel mechanism.

## 4. Boundary and ownership contract

### Owned by the RH-ON pre-admission stage

- Selection of an RH-eligible request from the configured waiting frontier.
- Authorization of its one initial pre-admission prefetch issue.
- A stable, request-correlated stage identity sufficient to suppress a second
  initial issue for the same logical request/stage generation.
- RH decline/park semantics for state funnel, negative cache, headroom,
  reserve, and speculative-budget conditions.
- READY classification and READY-first ordering only after the existing
  resident/full-prefix compatibility contract is satisfied.

The scheduler may remain the mechanical caller of the lower prefetch API; in
RH-ON mode it does so under RH stage authorization. Mechanical call placement
must not create a second semantic owner.

### Explicitly not owned by RH

- Physical host allocation, eviction, full-span fit, transfer completion, and
  hybrid finalization remain in the cache/restore layer.
- `WAIT_CAPACITY/HOST_ALLOC`, per-pool allocation generations, FIFO retry
  grants, and demand retries remain with restore/HOST_ALLOC arbitration.
- Storage hit/miss truth, cancellation cleanup, and request terminal state
  remain with their existing owners.
- Telemetry observes decisions; it cannot grant a stage, prove physical fit,
  or wake a HOST_ALLOC waiter.

### Mode contract

| Mode | Initial pre-admission issue authority | Required compatibility |
| --- | --- | --- |
| RH-ON | RH pre-admission stage, exactly once per request/stage generation | Ordinary eager enqueue must not issue or reserve the same initial prefetch. |
| RH-OFF | Existing ordinary eager enqueue path | Behavior, ordering, state transitions, and performance path remain unchanged. |

Mode selection must be immutable for the lifetime of active requests, or a
future gate must define a drain-safe handoff. This prevents an RH-ON request
from being reinterpreted by the RH-OFF eager owner during transition.

## 5. Required interfaces

This declaration specifies semantics, not final symbol names. The accepted
implementation shape must expose or preserve these interfaces:

1. **Mode boundary:** enqueue can determine RH-ON versus RH-OFF before an
   ordinary eager issue is possible.
2. **Stage identity:** the scheduler can correlate request identity, logical
   stage generation, issue owner/kind, and resulting restore attempt. The
   identity must be idempotent against repeated scheduler passes.
3. **Policy view:** RH continues to consume immutable request state, restore
   potential, causal epochs, frontier, headroom/reserve, and budget data.
4. **Issue result:** the lower prefetch path returns the existing typed
   outcome/state transition without transferring allocation authority to RH.
5. **Observation:** bounded request-correlated records distinguish RH-stage,
   ordinary eager, and later demand-retry issues and join stage authorization
   to finalize and admission. Missing telemetry cannot change behavior.

Whether stage identity is represented by an explicit token or an equivalent
existing monotonic state transition is an implementation-shape decision for
the relevant gates. It must have a deterministic oracle either way.

## 6. Atomic invariants

| ID | Invariant | Corpus relation | Required oracle |
| --- | --- | --- | --- |
| `RH-PA-I1` | In RH-ON, each selected request/stage generation has at most one initial prefetch issue. | New composition over `RH-IMP-004`. | Count request-correlated lower-layer calls by stage identity; exactly one after authorization and zero duplicates across repeated passes. |
| `RH-PA-I2` | In RH-ON, ordinary eager enqueue issues zero initial prefetches. | Departs from current enqueue behavior diagnosed by DBG. | Direct enqueue reaches the waiting frontier in a stageable state; no ordinary-eager issue precedes RH authorization. |
| `RH-PA-I3` | An eligible RH-ON request receives its one stage decision before ordinary admission; an ineligible request receives no issue and an explicit bounded decline reason. | Adapts `RH-IMP-001`, `RH-IMP-002`, `RH-TST-001`. | Deterministic frontier fixture checks event order and every decline gate. |
| `RH-PA-I4` | RH-OFF is behavior-preserving, including the existing eager issue and ordering. | Adopts `RH-IMP-003`, `RH-MAP-005`. | OFF-mode trace/call sequence equals the pre-change baseline. |
| `RH-PA-I5` | `RESTORING`, `HOST_ALLOC`, `REVALIDATE`, frontier-excluded, and backup-pending requests cannot receive an RH duplicate issue. | Adopts `RH-ANTI-001`, `RH-MAP-002`. | Negative state-funnel tests plus repeated-pass duplicate checks. |
| `RH-PA-I6` | READY means required host material is resident and full-prefix compatible; authorization or storage hit alone is not READY. | Adopts `RH-MAP-001`. | Existing strict-marker, consumed/dropped, and partial-prefix tests remain green. |
| `RH-PA-I7` | Hybrid KV+Mamba material remains durable and all-or-nothing through issue, transfer, allocation, finalize, and admission; RH cannot crop or synthesize a lower checkpoint. | Adapts `RH-IMP-006`; rejects `RH-ANTI-003`; preserves `RH-DEF-001`. | Full hybrid hit/finalize fixture; missing or invalid Mamba sidecar cannot be reported READY or silently converted to a lower checkpoint. |
| `RH-PA-I8` | HOST_ALLOC wake requires the existing all-required-domain generation predicate; Mamba-only advancement cannot wake a request still blocked on KV. | Adopts `RH-MAP-006`; preserves HOST_ALLOC epoch ownership. | 54,976-required/21,057-free/zero-evictable fixture remains held on Mamba-only changes; a KV generation change may grant one FIFO retry. |
| `RH-PA-I9` | RH release epochs, telemetry, and speculative budget signals cannot prove host fit or mutate HOST_ALLOC generations. | Adopts `RH-MAP-003`, `RH-MAP-004`, `RH-MAP-007`. | Cross-authority negative tests and unchanged-epoch no-refill tests. |
| `RH-PA-I10` | Cancellation or terminalization retires stage identity and reservations without permitting a late duplicate or admission. | New failure-boundary invariant. | Cancel before issue, during transfer, and after finalize; repeated passes remain idempotent. |

## 7. Failure model and containment

| Failure | Observable hazard | Required containment |
| --- | --- | --- |
| Both enqueue and RH issue | Duplicate I/O, reservation, budget debit, or conflicting restore transition | RH-ON ordinary-eager issue count is structurally zero; idempotent stage identity rejects repeats. |
| Neither path issues | Eligible request stalls before admission | Causal RH decision record and bounded safety reconciliation expose the missing transition without granting HOST_ALLOC authority. |
| Repeated RH pass or self-traffic | Retry storm | Existing epoch/event gating plus stage idempotency; unchanged inputs produce no issue. |
| Speculative budget/headroom denial | Unfair spin or eviction | Park on the typed reason; wake only on subscribed causal signal or bounded safety fuse; no RH eviction. |
| Storage miss or transfer error | False READY/admission | Existing typed miss/error state and negative-cache behavior; no READY marker. |
| Positive hit but full allocation fails | Miss conflation or crop | Preserve `DENIED_ALLOC`/`WAIT_CAPACITY/HOST_ALLOC`; lower allocator remains authoritative. |
| KV blocked while only Mamba generation advances | Invalid retry and hybrid corruption | Existing all-required-domain generation predicate keeps the waiter parked. |
| Missing/partial Mamba material | KV-only false success | Preserve hybrid all-or-nothing finalization and durability; reject/discard through existing typed path. |
| Cancel/timeout races with issue/finalize | Resource leak or post-terminal admission | Request terminal state fences issue/finalize; cleanup is idempotent and observable. |
| Mode changes with active requests | Ownership transfer and duplicate issue | Disallow live transition; drain/restart before mode change unless separately designed and gated. |
| Telemetry loss or sampling | Behavior changes or false authority | Decisions do not depend on logs; acceptance harness uses deterministic call/state oracles. |

## 8. Observable acceptance oracle

The minimum deterministic oracle is:

1. Enqueue five direct `/generate`-equivalent requests with RH enabled,
   frontier 8, and fake full KV+Mamba 54,976-token L3 hits.
2. Before ordinary admission, assert each selected eligible request has one
   RH-owned stage authorization and exactly one correlated lower prefetch
   call. Assert zero `ordinary_eager` calls and zero duplicate reservations or
   budget debits for those stage identities.
3. Re-run scheduler passes with unchanged epochs and while each request is
   `RESTORING`; issue counts must remain unchanged.
4. Join each authorization to its typed issue result, hybrid finalize outcome,
   resident/full-prefix READY marker, and admission or terminal cleanup.
5. Force every decline class: state funnel, negative cache, frontier,
   headroom/reserve, and physical/speculative budget. Each receives no issue
   and a deterministic reason; telemetry absence must not alter the result.
6. Repeat with RH disabled. Assert the pre-change eager ordinary call/state and
   queue/admission ordering remain the RH-OFF baseline, with no RH stage.
7. Reuse the 54,976-required/21,057-free/zero-evictable hybrid fixture. A
   positive hit that fails allocation must enter HOST_ALLOC, not miss or READY;
   Mamba-only generation changes must not wake it. A later KV generation
   advance may grant one FIFO demand retry, whose failed full allocation
   returns to a cursor without spin.
8. Exercise cancellation before issue, during transfer, and after finalize;
   prove no post-terminal duplicate, admission, or leaked reservation.

Evidence must include deterministic test output and immutable request/stage
call traces. A live 3060 run is a later system/performance gate prerequisite,
not a substitute for these ownership oracles.

## 9. Alternatives considered

### A. Defer ordinary eager issue under RH-ON; let the RH pass authorize it

**Recommended design input.** It reuses the existing RH frontier, state,
headroom, negative-cache, causal-epoch, and budget decisions while making the
initial owner unambiguous. RH-OFF retains the original eager path.

Trade-off: enqueue-to-I/O latency now depends on the next RH pass, so runtime
latency/fairness and queue-progress evidence is required. A missed RH trigger
becomes a visible liveness failure and must be covered by the bounded safety
reconciliation oracle.

### B. Reclassify the existing eager enqueue call as the RH stage

**Not recommended on current evidence.** This could minimize call-placement
change, but enqueue currently runs before waiting-frontier selection and the
RH policy gates. Calling it “RH” without applying equivalent frontier,
headroom, negative-cache, epoch, and speculative-budget semantics would move
the label, not the authority. It is viable only if a later architecture gate
proves those semantics can be evaluated atomically at enqueue.

### C. Keep eager enqueue and also run RH staging

**Rejected.** It has two initial-issue owners and directly permits duplicate
I/O, reservation, budget, and restore-state effects.

### D. Let RH absorb HOST_ALLOC generation and retry authority

**Rejected.** RH release epochs and host allocability generations have
different owners and meanings. Merging them risks auxiliary-only wake, miss
conflation, allocation inference, and fairness changes.

### E. Add observability only

**Not sufficient for the stated contract.** It would diagnose the current
ordering but would not create an RH-owned pre-admission opportunity.

## 10. Migration, rollout, rollback, and removal

### Migration/rollout

1. Complete a canonical Pattern Intake pinned to the implementation revision,
   including all stable, anti-pattern, bug, harness, benchmark, deferred, and
   missing IDs and atomic invariant mappings.
2. Obtain decisions from the existing architecture/system/technology/algorithm
   gates on the final call placement and stage-identity representation.
3. Implement only behind the existing RH mode boundary. Preserve the RH-OFF
   path byte-for-byte where practical and prove behavior equivalence.
4. First run deterministic ownership, hybrid-durability, HOST_ALLOC, cancel,
   and OFF-mode tests. Then perform independent implementation review.
5. Roll out through process restart with RH mode fixed. Use bounded,
   request-correlated stage/issue/finalize/admission evidence before any wider
   deployment. Performance and fairness tuning require their own evidence.

No persistent data migration is expected; the mechanism changes ephemeral
scheduler ownership and request state. That assumption must be revalidated if
stage identity is persisted or propagated across processes.

### Rollback

Drain active requests and restart with RH disabled. This returns initial
prefetch authority to the existing ordinary eager enqueue path. Do not flip
mode in place for requests whose stage identity or transfer is active. The
rollback must not alter cache format, Mamba sidecar format, allocation epoch,
or HOST_ALLOC cursor state.

### Removal

If the mechanism is abandoned, remove the RH-ON exclusive-routing branch and
its stage-identity-only state after draining active requests, restore the
single ordinary eager owner for all modes, and remove only tests/telemetry
specific to this authority split. Preserve independent RH policy, hybrid
durability, and HOST_ALLOC epoch contracts unless separately authorized.

## 11. Risks, reversibility, and unresolved evidence

- **Liveness/latency:** deferring enqueue issue can add one scheduler-pass
  delay or expose a missed trigger. Deterministic and live evidence are needed.
- **Fairness:** frontier selection can change which direct request starts I/O
  first. Existing stable priority boundaries must remain authoritative.
- **Idempotency:** request identity alone may be insufficient if a legitimate
  later demand retry exists; the implementation must distinguish stage
  generation from retry attempt without inventing cross-layer authority.
- **Hybrid safety:** any shortcut that treats KV completion as READY before
  durable Mamba finalization is blocking.
- **Source/runtime identity:** the debugger evidence is not deploy-hash pinned.
- **Corpus completeness:** the designated scout found no canonical full
  Pattern Intake and no accepted RH-specific mechanism or current-HEAD live
  acceptance evidence.

The change is structurally reversible because mode ownership is process-local
and no persistent format change is proposed. Reversibility becomes weaker if
future implementation persists stage identity, supports live mode flips, or
merges RH and HOST_ALLOC state; each would require a fresh architecture task.

## 12. Architect recommendation (non-authoritative)

Accept Alternative A as the proposed architecture direction: RH-ON receives
exclusive initial pre-admission issue authority, RH-OFF retains ordinary eager
behavior, and lower allocation/hybrid/HOST_ALLOC owners remain unchanged.

Implementation admission remains pending until the canonical Pattern Intake
is completed and existing gate owners accept the final implementation shape
and evidence plan. This recommendation is evidence for the orchestrator, not
an authority decision.

## 13. Final gate decision and implementation binding — 2026-09-09

Sections 1 and 12 record the original proposal-stage posture. For the exact
final source revision `f629d4e2c19eb74571b4154438fd651ce24ff53b`, that
posture is superseded by this decision.

**Novel Mechanism verdict: ACCEPT.** Alternative A—RH-ON queue-first with the
RH pass as sole initial issue owner, while RH-OFF retains eager-before-append—
is accepted as the implementation design. The implementation is admitted to
independent review under this mechanism. This is not self-approval of G-IMPL,
reviewer acceptance, runtime deployment, or performance.

### Bound revisions and change manifest

- Corpus/search revision (unchanged):
  `82ab235606233160701b15f657a71794cfd29a30`.
- Final implementation revision:
  `f629d4e2c19eb74571b4154438fd651ce24ff53b`.
- Implementation commits: `3ddc39c223`, `3785c99759`, `7831d45dd4`,
  `6881529acb`, `67b39b5aca`, `6edf69ce29`, `f629d4e2c1`.
- Changed product symbols: `Scheduler._add_request_to_queue`,
  `_ready_horizon_pass`, `_claim_prefetch`, `_release_prefetch_claim`,
  `_prefetch_kvcache`, `_prefetch_kvcache_impl`, `_feed_restore_terminal`;
  request-local fields on `Req`; `HiCachePrefetchOrigin`,
  `HiCachePrefetchIssueStatus`, `PrefetchIssueResult`;
  `UnifiedRadixCache.prefetch_from_storage`, terminal/completion handoff,
  `_host_alloc_hybrid_completion`, and `_handle_prefetch_result`. The final
  scheduler change adds the raw-frontier-`Req` to `ReadyHorizonView` join
  inside `_ready_horizon_pass`; it does not add a new owner or interface.
- Changed files are the four product files and five test files listed in the
  Pattern Intake final reconciliation. There is no persistence-format,
  allocator-policy, HOST_ALLOC-generation, remote-host, or 3090-branch change.

### Mechanism evidence matrix

| Declared invariant | Final implementation evidence | Oracle/evidence | Verdict |
| --- | --- | --- | --- |
| `RH-PA-I1/I2/I3`: RH-ON queue-first and sole initial issue owner | `_add_request_to_queue` omits eager issue only when RH is enabled; `_ready_horizon_pass` issues with `READY_HORIZON` | RH enqueue tests and final source/call-site audit | ACCEPT |
| `RH-PA-I2`: policy evaluation uses the typed view for each raw frontier request | `_ready_horizon_pass` joins `frontier_reqs` to `views` by RID before reading `staging_eligible` or `state` | `test_ready_pass_joins_raw_frontier_req_to_policy_view`; tester `TEST3060-RH-VIEW-TYPE-20260909.md` | ACCEPT |
| `RH-PA-I4`: RH-OFF preserves eager order | `EAGER_RH_OFF` call remains before queue append | RH-OFF enqueue test; pre-change live trace is context only | ACCEPT structurally; final live trace open |
| `RH-PA-I5/I10`: no duplicate and stale-safe retirement | Active request-local attempt spans `ISSUED`; release compares attempt; cache terminals carry attempt | Gate-pass, stale-release, lifecycle and stale-terminal evidence | ACCEPT |
| `RH-PA-I6/I7`: all-material READY only | Finalizer supplies actual KV/aux counts; scheduler accepts only `accepted`; discarded/rejected maps to recompute and no `ready_host` | Dependency-free ready-host/aux/discard tests and storage durability tests | ACCEPT |
| `RH-PA-I8/I9`: HOST_ALLOC/Mamba authority unchanged | RH consumes typed outcomes; no RH mutation of generation/FIFO/allocator authority | Range scope audit and focused restore/host-allocation evidence | ACCEPT within this change |
| Observable joined oracle | Bounded `rh_preadmission.v1`, `rh_stage.v2`, `rh_ready_host.v1`, `rh_admission.v2` emit request/attempt joins | Required-field AST test and source inspection | ACCEPT for interface; final live join open |

### Rejected alternatives, migration, and reversibility

Alternatives B through E retain their original dispositions. In particular,
dual eager+RH ownership and RH absorption of HOST_ALLOC authority remain
prohibited. State is ephemeral and process-local; no durable migration exists.
Rollout and rollback require a drain/restart boundary. Rollback disables RH and
returns initial authority to eager enqueue; live mode flip remains unsupported.

### Unresolved evidence and risk

- Missing `orjson` blocks dependency-backed RH unit and scheduler-feed runs.
- Independent tester report `TEST3060-RH-VIEW-TYPE-20260909.md` (SHA-256
  `f85a535ddba7cf88760a7c157cc171041f140c1186a102501fb24af83d7996b7`)
  accepts the `f629d4e2c1` view-join fix after the 6/6 dependency-free contract
  run and focused restore/storage checks.
- No live/deploy-hash-pinned execution exists for final revision `f629d4e2c1`;
  older RH traces do not establish final-revision behavior.
- No performance or fairness benefit is accepted. The earlier bounded trace
  regressed aggregate outcomes and remains diagnostic only.
- Independent reviewer acceptance is still mandatory and may block merge.
