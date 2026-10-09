# Novel Mechanism — Ready Horizon one-shot current-match preparation

```yaml
schema_version: project-novel-mechanism-1
artifact_id: NM-RH-MATCH-PREP-20260909-01
task_id: T3060-RH-MATCH-GATE-INTAKE-20260909
orchestration_epoch: 20260909-rh-ab46
role: architect
artifact_repository: /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache
design_source_repository: /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt
design_source_branch: 3060-12g-qwen35-4b
searched_source_revision: f629d4e2c19eb74571b4154438fd651ce24ff53b
design_input: ARCH3060-RH-MATCH-GATE-DESIGN-20260909.md
design_input_revision: f629d4e2c19eb74571b4154438fd651ce24ff53b
pattern_intake: storage/review/gates/pattern-intake/PATTERN-INTAKE-20260909-RH-MATCH-PREP.md
declaration: NOVEL_MECHANISM_REQUIRED
disposition: PROPOSED_FOR_GATE_OWNER_ACCEPTANCE
gate_verdict: PENDING
implementation_revision: null
implementation_status: NOT_YET_ACCEPTED
decision_authority: orchestrator_and_existing_gate_owners
```

## 1. Declaration and non-authority

This declaration proposes an ephemeral, scheduler-local capability proving that
a potentially stageable Ready Horizon (RH) request received a current prefix
match in this causal refill pass. The RH policy consumes request fields produced
by that match; the immediate RH issue may skip its normal duplicate match only
when the capability still validates. Invalidity causes exactly one ordinary
non-COW rematch. The capability expires on every pass exit and cannot reach
admission.

This is a new input to the existing architecture/system/technology/algorithm
gates. It does not approve itself, authorize implementation, accept tests, or
replace independent implementation review. The accepted RH pre-admission
Novel Mechanism covers exclusive initial-issue ownership at
`f629d4e2c19eb74571b4154438fd651ce24ff53b`; it does not cover this new
match-freshness/consumption boundary. `f629` is therefore the pinned design
input, while implementation of this mechanism remains not yet accepted.

## 2. Trigger and why known patterns do not fully fit

Known patterns provide all neighboring operations but not their safe
composition:

- `RH-IMP-001/002/004` provide immutable policy views, causal refill, and the
  scheduler integration/issue boundary.
- `RH-MATCH-IMP-001/002` provide the exact request match geometry and the
  existing issue-time non-COW match.
- `RH-MATCH-IMP-003` provides extant-node and storage-gate validation.
- `RH-MATCH-IMP-005` proves that `cow_mamba=False` avoids Mamba destination
  allocation and COW assignment.
- Existing claim, allocator, hybrid-finalizer, HOST_ALLOC, admission-COW, and
  flush-before-evict contracts remain reusable unchanged.

None provides a capability that lets one mutable match be used first by RH
policy and then consumed by issue without rematching, while proving request,
pass, token/key, and anchor freshness. Moving the existing match before policy
without such a proof risks stale issue. Keeping both calls duplicates LRU,
node-split, and cache-action effects. A Boolean/RID marker cannot distinguish
retraction, session/token/key changes, pass lifetime, or deleted anchors.

The composition therefore creates a new trusted boundary:

```text
causal refill authority
  -> one mutating, non-COW current match
  -> ephemeral identity/freshness proof
  -> RH policy reads prepared fields
  -> existing issue claim
  -> validate and consume proof, or rematch once
  -> existing storage/allocator/finalizer
```

The novelty is not prefix matching itself. It is the one-shot transfer of
freshness evidence across policy and issue in the presence of mutable cache
topology and request lifecycle changes.

## 3. Corpus evidence

The complete inventory and dispositions are in the paired Pattern Intake,
pinned to source revision `f629d4e2c1` and inheriting the earlier bounded
corpus at `82ab235606`. Relevant IDs are:

- Stable: `RH-IMP-001..006`, `RH-MATCH-IMP-001..007`.
- Negative: `RH-ANTI-001..003`, `RH-MATCH-ANTI-001..008`.
- Bug-derived: `RH-BUG-001..002`, `RH-MATCH-BUG-001..002`.
- Harness/test: `RH-TST-001..005`, `RH-MATCH-TST-001..004`.
- Benchmark: `RH-BENCH-001`, `RH-MATCH-BENCH-001..002`.
- Deferred: `RH-DEF-001..003`, `RH-MATCH-DEF-001..002`.
- Missing: `RH-MISS-001..004`, `RH-MATCH-MISS-001..004`.

Observed source evidence at `f629` shows that `_ready_horizon_pass` builds
views before causal gating, `_restore_potential_for` reads request match fields,
and `_prefetch_kvcache_impl` matches only afterward. Unified matching can split
nodes, refresh LRU/access metadata, and apply cache actions. The final RH-ON
trace then shows all requests excluded as `no_restore_potential`, while the
paired OFF trace demonstrates recoverable storage material. This is defect
evidence, not proof of physical capacity or performance improvement.

## 4. Boundary, ownership, interfaces, and dependencies

### New narrow owner

`Scheduler._ready_horizon_pass` owns only the lifetime and routing of the
one-shot proof:

1. create it after the existing `epoch_event`/`should_refill` decision;
2. associate it with one live, potentially stageable frontier request;
3. pass it only to that request's immediate RH-origin issue;
4. discard it on every success, decline, exception, or pass exit.

The proof contains identity/freshness observations only. It is not a lock,
reservation, allocator handle, issue claim, readiness marker, or cache version.

### Existing owners retained

| Concern | Owner and invariant |
| --- | --- |
| Match geometry | `Req.init_next_round_input` and existing cache consensus; no second walker. |
| Match-owned mutation | Unified cache implementation; allowed only as effects of the one normal match. |
| RH eligibility/negative/budget policy | Existing `ReadyHorizonView` and policy after preparation. |
| Initial issue deduplication | Existing active-attempt claim, acquired before resource effects. |
| Anchor/storage truth | Existing `node_exists` and `prefetch_gate_ok`, rerun immediately before issue. |
| Allocation, eviction, transfer, finalize | Existing cache/controller/finalizer; proof grants none of these. |
| HOST_ALLOC generation/FIFO retry | Existing restore/scheduler authority; unchanged. |
| Admission and Mamba COW | Existing admission-time initialization; never suppressed. |
| Mamba durability | Existing flush-before-evict path; never bypassed. |
| Telemetry | Observational only. |

### Required proof fields

The immutable internal value must fence, at minimum: request object identity,
RID, RH pass sequence, enqueue sequence, session generation, retraction count,
fill object identity and length, output length, `extra_key`, `cache_salt`, and
the matched device/host anchors. Exact spelling may differ only with a
one-to-one implementation manifest.

It is consumable only when:

- origin is `READY_HORIZON`;
- every identity field still equals the live request/pass;
- request match fields still equal the prepared anchors;
- every non-null anchor still resolves through `node_exists`;
- the existing cache/buffer `prefetch_gate_ok` semantics are rerun.

The existing buffer-mode device-anchor fallback remains in its current owner.
A current matched root may be valid where the existing gate permits it; a
default/uninitialized root-like value is never proof.

## 5. Atomic invariants and observable oracles

| ID | Invariant | Observable oracle |
| --- | --- | --- |
| `RH-MG-I1` | Potentially stageable eligibility never reads uninitialized or stale/default anchors. | Fresh and retracted fixtures prove preparation precedes view; default excludes and current valid root is gate-dependent. |
| `RH-MG-I2` | One match per candidate per due pass; exactly one extra only after logged validation failure. | Instrument `match_prefix`; issued normal path count=1, invalidated path count=2, no-event count=0. |
| `RH-MG-I3` | `cow_mamba=False` preparation changes no Mamba request COW fields and calls no Mamba alloc/evict. | Snapshot three request fields and allocator/evict counters before/after. |
| `RH-MG-I4` | Preparation creates no attempt, reservation, storage query, restore transition, or READY marker; normal match-owned LRU/split/action effects are permitted. | Separate match and issue spies; failure path has zero resource effects. |
| `RH-MG-I5` | Issue requires a valid proof or completed fallback plus the existing successful claim. | One claim, one storage query, one attempt; active claim blocks duplicate. |
| `RH-MG-I6` | A usable anchor is current-match-proven, extant at consumption, and accepted by the existing gate. | Default/root/deleted-node matrix; deleted anchor rematches or holds without stale dereference. |
| `RH-MG-I7` | RH-OFF remains eager-before-append and creates no proof/preparation telemetry. | Pre/post AST and behavioral call-order equivalence. |
| `RH-MG-I8` | RESTORING, active-attempt, HOST_ALLOC, REVALIDATE, FRONTIER, BACKUP_PENDING, READY, terminal, and active chunked requests are not prepared or issued. | State/lifecycle parameterized zero-call test. |
| `RH-MG-I9` | Retraction invalidates all prior match provenance. | Incremented `retraction_count` plus stale host anchor causes fresh match. |
| `RH-MG-I10` | Admission performs its own initialization/COW and receives no RH proof. | Admission spy after accepted stage; normal Mamba COW/cleanup remains. |
| `RH-MG-I11` | RH calls no allocator/eviction API; Mamba host eviction still flushes non-durable victims first. | RH call graph spy and unchanged OFF/ON flush event-order tests. |
| `RH-MG-I12` | Telemetry cannot establish validity, issue, wake HOST_ALLOC, clear negatives, or mark READY. | Logging disabled/sampled/failed produces identical decisions and state. |

The authoritative detailed mapping is `RH-MG-MAP-001..012` in the paired
Pattern Intake, with deterministic cases `MG-T1..MG-T17`.

## 6. Failure model and containment

| Failure | Hazard | Required containment |
| --- | --- | --- |
| View built without preparation | False `no_restore_potential` or stale eligibility. | Fail closed/assert in deterministic contract; do not issue from request defaults. |
| Preparation raises or returns no known anchor | Scheduler error or false root issue. | Emit bounded `match_prepare_failed`/`anchor_unknown`; zero claim/reservation/query/state transition. |
| Request identity/token/key changes | Proof refers to different logical input. | Invalidate and perform one ordinary non-COW rematch. |
| Anchor deleted or replaced before issue | Stale-node dereference or wrong storage origin. | `node_exists` failure invalidates; one rematch, then gate or hold. |
| Earlier candidate mutates tree used by later candidate | Cross-candidate stale topology. | Validate each proof immediately before consumption; rematch later candidate once. |
| Match called twice normally | Duplicate LRU/split/action effects and extra cost. | Blocking test failure; only invalidation permits count=2. |
| Preparation performs Mamba COW/alloc/evict | Speculative pool mutation and ownership leak. | Blocking defect even if request completes; negative field/counter oracle. |
| Proof survives pass/admission | Stale capability suppresses later authoritative match. | Stack/pass-local storage only; drop on every exit; no request persistence. |
| Existing storage gate changes between match and issue | Issue from no-longer-valid origin. | Rerun `prefetch_gate_ok`; decline under existing typed semantics. |
| RH allocates/evicts directly | Authority transfer and durability/fairness violation. | Blocking scope defect; stop and redispatch architecture work. |
| Telemetry fails | Missing evidence or accidental control coupling. | Product decision unchanged; acceptance reports missing/not-computable. |

Preparation telemetry may report request/pass identity, result/reason,
match-count, fallback, anchor kind/existence/gate, duration, and Mamba deltas.
It must be bounded and joined to RH decision/stage/readiness/admission records.
It is never validity authority.

## 7. Alternatives considered

1. **Recommended: one current non-COW match plus ephemeral validated proof.**
   Reuses exact match geometry, repairs eligibility, avoids normal duplicate
   matching, and keeps all lower authorities intact.
2. **Match before views and match again in issue. Rejected.** Duplicate mutable
   match effects can alter replacement behavior and cost.
3. **Prepare at enqueue. Rejected.** Queue residence permits request and cache
   changes; it also moves work before the causal gate.
4. **Boolean/RID/request-persistent initialized marker. Rejected.** It lacks
   pass, token/key, retraction, session, and anchor freshness.
5. **Move scheduling priority calculation before RH. Rejected.** It changes
   whole-queue timing and policy ordering beyond the narrow defect.
6. **Add a pure peek/tree walker. Deferred.** It could avoid cache mutation,
   but expands component interfaces and risks diverging Full/SWA/Mamba/key
   consensus. It requires a fresh architecture task.
7. **Treat root/default as automatically eligible. Rejected.** Provenance and
   extant/gate checks are mandatory.
8. **Perform Mamba COW during preparation. Rejected.** Admission owns COW and
   cleanup; speculative preparation may not allocate device Mamba state.
9. **Reuse proof across passes with a cache generation. Deferred/rejected for
   this task.** It introduces cache-version authority and invalidation rules.

## 8. Migration, rollout, rollback, and removal

No persistent state, storage format, key format, wire interface, or
cross-process migration is proposed. The proof is stack/pass-local and dies
with the scheduler pass.

Migration/rollout sequence:

1. Existing gate owners accept or amend this declaration, its Pattern Intake,
   and the pinned match-gate design.
2. A fresh coder task changes only the scheduler-local implementation and
   focused tests, producing an exact symbol/file manifest and descendant SHA.
3. Fresh tester and reviewer tasks bind deterministic evidence and independent
   acceptance to that SHA.
4. Deploy only through a drained process restart; run paired, hash-pinned RH-OFF
   and RH-ON bounded evidence before wider enablement.

Rollback is drain/restart with RH disabled, which preserves the established
RH-OFF eager path, or revert the scheduler-only descendant and restart. Do not
hot-toggle RH with active requests.

Removal deletes the proof type/helpers, preparation/consumption branch, and
specific telemetry/tests. It restores issue-time matching while leaving the
accepted exclusive RH-ON initial owner, RH policy, RH-OFF path, restore/claim,
allocator/finalizer, HOST_ALLOC, and durability contracts intact. No durable
cleanup is required.

## 9. Risks, uncertainty, and recommendation

Primary risks are match-owned mutation before issue claim, cross-candidate
anchor invalidation, accidental second match, preparation overhead, false root
provenance, and suppression of admission COW. The mechanism is reversible and
its risks are observable through match counts, validation reasons, anchor
checks, and Mamba/allocator negative oracles.

Open uncertainty remains whether scheduler-owner serialization is complete for
every callback between preparation and issue. Implementation review must prove
it. If it cannot, this mechanism must be rejected in favor of a freshly gated
atomic/cache-generation design. Package-backed test availability and post-fix
live behavior are also unproven.

Architect recommendation: accept this declaration only as the design input for
the narrow scheduler-local mechanism described here and in
`ARCH3060-RH-MATCH-GATE-DESIGN-20260909.md`. It does not constitute G-IMPL,
test, reviewer, deploy, performance, or terminal acceptance. Extra work
requires a fresh Task ID.
