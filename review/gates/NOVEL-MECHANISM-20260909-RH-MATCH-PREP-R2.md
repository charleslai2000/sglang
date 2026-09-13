# Novel Mechanism R2 — Ready Horizon current-match preparation

```yaml
schema_version: project-novel-mechanism-1
artifact_id: NM-RH-MATCH-PREP-20260909-02
supersedes: NM-RH-MATCH-PREP-20260909-01
task_id: T3060-RH-MATCH-GATE-ACCEPT-20260909
orchestration_epoch: 20260909-rh-ab49
repin_task_id: T3060-RH-MATCH-GATE-REPIN-20260909
repin_orchestration_epoch: 20260909-rh-ab53
role: architect
source_branch: 3060-12g-qwen35-4b
searched_source_revision: f629d4e2c19eb74571b4154438fd651ce24ff53b
accepted_scope_revision: 20260909-rh-ab49
pattern_intake: /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/storage/review/gates/pattern-intake/PATTERN-INTAKE-20260909-RH-MATCH-PREP.md
architecture_gate: /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/review/gates/ARCH-20260909-RH-MATCH-PREP.md
declaration: NOVEL_MECHANISM_REQUIRED
gate_verdict: ARCHITECT_ACCEPT
orchestrator_acceptance: ACCEPTED
orchestrator_acceptance_source: T3060-RH-MATCH-GATE-REPIN-20260909
implementation_revision: 9213ee01d90ba3925e7fe928e80cc41354ee4fff
implementation_parent_revision: c4ad01ef5d7578bb542fe3e514a71cdbccb6c07a
implementation_status: PINNED_PENDING_INDEPENDENT_IMPLEMENTATION_REVIEW_TESTER_AND_RUNTIME_ACCEPTANCE
decision_authority: architect_recommendation_orchestrator_final_acceptance
```

## Explicit decision and novelty

The architect gate accepts as a design input one ephemeral scheduler-local
capability proving that an RH candidate received a current, non-COW prefix match
in the causally due pass. Policy may read the prepared request fields; the
immediate RH issue may consume the capability once after identity, lifecycle,
anchor-existence, and storage-gate validation. Invalidity permits exactly one
ordinary non-COW rematch and otherwise fails closed.

The exact addition of `tree_core.is_l3_durable(anchor_node_id)` to
`UnifiedRadixCache.has_restore_potential` is included in the same mechanism.
This clause aligns the policy-side potential predicate with the already-owned
`prefetch_gate_ok` predicate. It does not establish durability, traverse or
mutate the tree, allocate, evict, finalize, publish, or issue I/O. No other
cache-layer change is authorized.

The novelty remains the one-shot transfer of freshness evidence across a
mutating match, policy, and issue. Known patterns cover matching and issue
separately but do not provide a pass-scoped capability or its invalidation
rules. The L3 clause is not independently novel; it is required predicate
alignment inside this boundary so the prepared current anchor is judged by one
eligibility vocabulary from policy through issue.

The orchestrator accepted this explicit architect recommendation through
repin task `T3060-RH-MATCH-GATE-REPIN-20260909`. The accepted design chain is
pinned to `9213ee01d90ba3925e7fe928e80cc41354ee4fff` (parent
`c4ad01ef5d7578bb542fe3e514a71cdbccb6c07a`). This declaration remains design
authority only: it does not accept implementation conformance, tests,
independent review, deployment, or runtime value.

## Boundaries, owners, and invariants

- Scheduler owns causal placement, pass lifetime, identity fencing, one-shot
  routing, and fallback containment.
- `Req.init_next_round_input(..., cow_mamba=False)` and existing cache match
  logic retain match geometry and normal match-owned mutations.
- `has_restore_potential` may only recognize an extant L3-durable anchor in
  parity with existing root/backuped cases; `prefetch_gate_ok` remains the
  issue-time authority and is rerun.
- Existing active-attempt claim owns issue deduplication. The capability is not
  a claim, reservation, readiness marker, lock, or cache version.
- Existing allocators, finalizers, HOST_ALLOC generation/FIFO, admission-time
  COW, and Mamba flush-before-evict retain exclusive authority.
- RH-OFF remains eager-before-queue and creates no RH prepared capability.
- Telemetry is observational and cannot validate a capability or change state.

Atomic invariants `RH-MG-I1..I12` and mappings `RH-MG-MAP-001..012` from R1
remain binding. R2 adds `RH-MG-I13`: for an extant anchor, policy potential and
the existing issue gate use the same backuped/root/L3-durable eligibility set;
missing and extant non-durable anchors remain ineligible. `MG-T18` is its
required real-method parity oracle.

## Failure model and required containment

| Failure | Containment |
| --- | --- |
| No current preparation | Candidate cannot become eligible from stale/default fields. |
| Match error or unknown anchor | Zero issue, attempt, reservation, allocation, or I/O; emit failure evidence. |
| Identity/lifecycle/anchor change | Invalidate; exactly one fallback rematch; rerun existence and gate checks. |
| Duplicate normal match | Blocking defect; count two is valid only for recorded invalidation fallback. |
| Mamba field, alloc, or evict delta during preparation | Blocking ownership defect. |
| Policy/issue L3 predicate drift | Blocking defect under `MG-T18`. |
| Any broader cache edit | Scope violation; remove it or obtain a fresh Task ID and gate chain. |
| Telemetry loss | Product behavior unchanged; evidence is missing/not-computable. |

## Rejected alternatives

- Removing the L3 clause while retaining current-match preparation is rejected:
  a current extant L3-durable anchor would still be excluded before the issue
  gate that already accepts it, leaving the observed eligibility split intact.
- A separate L3 task is unnecessary because no new owner or side effect is
  introduced by exact predicate parity. Any broader cache change does require a
  separate task.
- Double matching, enqueue-time matching, persistent Boolean/RID tickets,
  admission-time COW suppression, direct RH allocation/eviction, and a new pure
  tree walker remain rejected or deferred as recorded in R1.

## Migration, rollback, and removal

There is no persistent, wire, storage-key, or mixed-version migration. Rollout
requires independent tests/review at the pinned commit and a drained restart.
Rollback is a drained restart with RH disabled or revert of the bounded
scheduler-plus-predicate descendant. Removal deletes the pass-local capability,
its preparation/consumption/telemetry helpers, the exact L3 parity clause, and
focused tests. Existing RH-OFF, claim, allocator, finalizer, HOST_ALLOC,
admission, and durability contracts remain intact.

## Open uncertainty

Scheduler-owner serialization and callback behavior must be demonstrated by
independent evidence at the pinned implementation revision. If identity can mutate without a fenced
field or cache topology can invalidate a still-extant anchor semantically, a
new atomic/cache-generation design is required. Package-backed and live runtime
behavior are not established by this gate.
