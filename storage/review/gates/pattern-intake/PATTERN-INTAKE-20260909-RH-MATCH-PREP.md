# Pattern Intake — Ready Horizon current-match preparation

```yaml
schema_version: project-contract-full-intake-1
schema_basis: AGENTS.md Pattern Intake and Novel Mechanism Gate
artifact_id: PI-RH-MATCH-PREP-20260909-02
supersedes: PI-RH-MATCH-PREP-20260909-01
task_id: T3060-RH-MATCH-GATE-ACCEPT-20260909
orchestration_epoch: 20260909-rh-ab49
repin_task_id: T3060-RH-MATCH-GATE-REPIN-20260909
repin_orchestration_epoch: 20260909-rh-ab53
role: architect
artifact_repository: /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache
design_source_repository: /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt
design_source_branch: 3060-12g-qwen35-4b
searched_source_revision: f629d4e2c19eb74571b4154438fd651ce24ff53b
inherited_corpus_revision: 82ab235606233160701b15f657a71794cfd29a30
design_input: /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/review/gates/ARCH-20260909-RH-MATCH-PREP.md
design_input_revision: f629d4e2c19eb74571b4154438fd651ce24ff53b
classification: FULL_INTAKE_REQUIRED
disposition: ORCHESTRATOR_ACCEPTED_DESIGN_CHAIN_IMPLEMENTATION_PINNED_PENDING_INDEPENDENT_ACCEPTANCE
gate_verdict: ARCHITECT_ACCEPT
orchestrator_acceptance: ACCEPTED
orchestrator_acceptance_source: T3060-RH-MATCH-GATE-REPIN-20260909
implementation_revision: 9213ee01d90ba3925e7fe928e80cc41354ee4fff
implementation_parent_revision: c4ad01ef5d7578bb542fe3e514a71cdbccb6c07a
implementation_status: PINNED_PENDING_INDEPENDENT_IMPLEMENTATION_REVIEW_TESTER_AND_RUNTIME_ACCEPTANCE
novel_mechanism_trigger: ONE_SHOT_MUTATING_MATCH_FRESHNESS_AND_CONSUMPTION_BOUNDARY
novel_mechanism: /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/review/gates/NOVEL-MECHANISM-20260909-RH-MATCH-PREP-R2.md
accepted_scope_revision: 20260909-rh-ab49
decision_authority: architect_recommendation_orchestrator_final_acceptance
```

## 1. Decision and authority

This intake accepts, at the architect gate, the narrow design in
`ARCH-20260909-RH-MATCH-PREP.md` as the implementation candidate
shape: after the existing causal refill gate, prepare each potentially
stageable frontier request with exactly one current
`Req.init_next_round_input(tree_cache, cow_mamba=False)` match, build the RH
view from that result, and consume a scheduler-local one-shot proof in the
immediate RH issue call. A stale proof fails closed into one ordinary non-COW
rematch. Admission retains its separate match and Mamba COW.

The exact `UnifiedRadixCache.has_restore_potential` L3-durable eligibility
alignment is part of this same boundary. It may add only
`tree_core.is_l3_durable(anchor_node_id)` to the extant-anchor disjunction so
that pre-policy restore potential cannot reject an anchor which the existing
`prefetch_gate_ok` already authorizes. This is predicate parity, not authority
to change traversal, matching, cache mutation, allocation, eviction,
finalization, durability publication, or persistence.

This artifact is evidence for the design chain accepted by the orchestrator in
repin task `T3060-RH-MATCH-GATE-REPIN-20260909`. That acceptance does not
self-approve product code, tests, or implementation conformance. The prior RH pre-admission gates accepted the exclusive
RH-ON initial-issue design at `f629d4e2c1`; they do not accept this additional
match-preparation boundary. `f629d4e2c1` is the pinned design input and searched
source baseline, not an accepted implementation of this fix.

## 2. Evidence boundary

### Observed facts

1. At `f629d4e2c19eb74571b4154438fd651ce24ff53b`,
   `Scheduler._get_new_batch_prefill_raw` orders HiCache event processing,
   restore reconciliation, and `_ready_horizon_pass` before ordinary
   admission work.
2. `_ready_horizon_pass` currently builds `_ready_horizon_views` before
   `epoch_event`/`should_refill`. Each view computes `staging_eligible` through
   `_restore_potential_for`, which reads `last_host_node`, `host_hit_length`,
   and `full_untruncated_fill_ids`.
3. The RH issue path later calls `_prefetch_kvcache_impl`, which performs
   `req.init_next_round_input(self.tree_cache, cow_mamba=False)` before the
   storage gate. The match is therefore after the eligibility decision.
4. `Req.init_next_round_input` refreshes fill IDs; applies the existing input,
   SWA, positional-override, `extra_key`, `cache_salt`, and key-limit geometry;
   calls `tree_cache.match_prefix`; and writes all match results back to the
   request.
5. Fresh requests begin with null anchors and zero host-hit lengths.
   `reset_for_retract` increments `retraction_count` and clears `last_node`, but
   does not clear `last_host_node`; a retracted request can therefore retain a
   stale host anchor until rematched.
6. `cow_mamba=False` makes `MambaComponent.finalize_match_result_in_cache`
   return before destination allocation, eviction-for-allocation, and request
   COW assignment.
7. Prefix matching is not pure. `UnifiedTreeCore` may split a partial node,
   refresh component LRU state and ancestor access times, and return cache
   actions; `UnifiedRadixCache.match_prefix` applies those actions before
   component finalizers.
8. Existing `node_exists` and `prefetch_gate_ok` interfaces provide the
   authoritative extant-anchor and buffer/cache-mode issue checks. The gate
   allows a root returned by a current match; a default root-like value has no
   such provenance.
9. The final RH-ON run at `f629d4e2c1` completed 5/5 HTTP requests, but all five
   emitted `rh_preadmission.v1 decision=exclude
   reason=no_restore_potential`, with no RH issue/ready/admission join. Its RH
   ready-host rate is not computable.
10. The paired RH-OFF run observed one 54,976-token KV storage query and Mamba
    sidecar hit per RID. This proves recoverable material for that workload,
    not physical staging capacity for every request.
11. Existing Mamba host eviction owns flush-before-evict. Existing HOST_ALLOC
    generation/FIFO logic owns physical retry. Neither authority belongs to
    RH match preparation.

### Assumptions requiring implementation review

- Queue mutation, preparation, planning, and issue are serialized by the
  scheduler owner. If not, a cache-generation/atomicity design is required and
  this intake is insufficient.
- No callback between preparation and immediate issue can mutate request
  identity without changing one of the proposed validation fields.
- The ticket implementation remains scheduler-local and ephemeral. The sole
  cache-layer exception is the exact `has_restore_potential` L3-durable parity
  clause accepted here. Persisted tickets, cross-process propagation, live
  mode switching, other cache-interface changes, or any new side effect require
  a fresh Task ID and revised gates.

### Proposed, not observed

- A frozen scheduler-local prepared-match value carries request/pass/token/key/
  anchor identity but no allocator handle or lock.
- It is created only after `should_refill`, consumed only by an RH-origin issue
  in the same pass, and discarded on every exit.
- Failed validation performs exactly one normal non-COW rematch and reruns the
  existing storage gate. Preparation failure excludes without issue.

### Repin facts observed after design acceptance

- Git resolves the final implementation pin to
  `9213ee01d90ba3925e7fe928e80cc41354ee4fff` and its parent to
  `c4ad01ef5d7578bb542fe3e514a71cdbccb6c07a`.
- The baseline-to-pin changed-file manifest contains only
  `python/sglang/srt/managers/scheduler.py`,
  `python/sglang/srt/mem_cache/unified_radix_cache.py`, and three focused tests
  under `3090-dev/`.
- The parent-to-pin telemetry repair changes only
  `Scheduler._emit_rh_match_prepare` and one focused dependency-free test.
- These facts establish the immutable pin and bounded surface; they do not
  establish implementation, tester, reviewer, deployment, or runtime
  acceptance.

## 3. Corpus revision, scope, and method

The source/test corpus was inspected at exact Git revision
`f629d4e2c19eb74571b4154438fd651ce24ff53b`. Scope was limited to the RH
scheduler/policy, request initialization/retraction, Unified cache matching and
anchor gates, Mamba match finalization/host eviction, and the RH/restore/storage
tests under `3090-dev` and registered manager tests. Git symbol search and
exact-revision file reads were used; no remote or external corpus was added.

Gate evidence comprised the prior canonical RH Pattern Intake, Novel Mechanism,
and Architecture gate in the sibling design worktree; the current match-gate
design report; the RH causal debugger report; and final `f629` RH-ON/RH-OFF
tester reports. The earlier scout's bounded corpus remains pinned to
`82ab235606233160701b15f657a71794cfd29a30`; this intake rechecks and extends
that corpus against `f629d4e2c1`. Untracked gate reports are documentary
evidence, not Git content at `f629`.

No claim is made about repositories, branches, or external corpora outside
that scope.

## 4. Gate and report evidence inventory

| ID | Evidence | Disposition |
| --- | --- | --- |
| `RH-GATE-001` | Prior HOST_ALLOC architecture contract separates RH release epochs from HOST_ALLOC generation. | **ADOPT AS BOUNDARY EVIDENCE**. |
| `RH-GATE-002` | Prior HOST_ALLOC Pattern Intake inventories neighboring allocation/failure patterns. | **ADOPT AS HISTORICAL EVIDENCE**; revision differs. |
| `RH-GATE-003` | HOST_ALLOC Novel Mechanism declares the mutation→generation→cursor→FIFO→allocator composition. | **KEEP SEPARATE**; no authority transfer to RH. |
| `RH-GATE-004` | Runtime-compatibility EXEMPT artifact. | **NOT ADOPTED**; this task is semantic and non-exempt. |
| `RH-GATE-005` | Hybrid-frontier review supports no crop and all-or-nothing material. | **ADOPT AS REVIEW EVIDENCE**. |
| `RH-GATE-006` | Capacity-semantics rejection records allocation-failure/miss conflation. | **ADOPT AS NEGATIVE EVIDENCE**. |
| `RH-GATE-007` | Alloc-failed terminal review supports typed `DENIED_ALLOC`/`HOST_ALLOC`. | **ADOPT AS NEIGHBORING EVIDENCE**. |
| `RH-GATE-008` | HOST_ALLOC telemetry deep review retains sampling/live limits. | **ADOPT FOR OBSERVABILITY LIMITS**. |
| `RH-GATE-009` | `PATTERN-INTAKE-20260909-RH-PREADMISSION.md`. | **ADOPT AS ACCEPTED EXCLUSIVE-ISSUER BASELINE**; does not cover pre-view matching. |
| `RH-GATE-010` | `NOVEL-MECHANISM-20260909-RH-PREADMISSION.md`. | **ADOPT AS ACCEPTED AUTHORITY BASELINE**; not approval of a prepared-match capability. |
| `RH-GATE-011` | `ARCH-20260909-RH-PREADMISSION.md` plus pin/accept reports. | **ADOPT AS OWNERSHIP CONSTRAINT** at `f629`. |
| `RH-GATE-012` | `ARCH3060-RH-MATCH-GATE-DESIGN-20260909.md`. | **ADOPT AS PROPOSED DESIGN INPUT**; gate-owner acceptance pending. |
| `RH-GATE-013` | `DBG-20260909-RH-NO-STAGING.md` and final `f629` ON/OFF reports. | **ADOPT AS BUG/RUNTIME EVIDENCE**; performance attribution rejected. |

## 5. Complete relevant pattern inventory and dispositions

### 5.1 Stable implementation patterns

| ID | Evidence | Disposition |
| --- | --- | --- |
| `RH-IMP-001` | `ReadyHorizonView`, `CausalEpochs`, `NegativeCacheEntry`, `RefillPlan`. | **ADAPT** typed immutable policy inputs; views must be built after current preparation. |
| `RH-IMP-002` | `ReadyHorizonPolicy.epoch_event` and `should_refill`. | **ADOPT** as the gate before expensive preparation; never as host-fit proof. |
| `RH-IMP-003` | `partition_ready_first`. | **ADOPT UNCHANGED**; preserve priority and RH-OFF no-op behavior. |
| `RH-IMP-004` | Scheduler RH integration and exclusive RH-ON initial issue at `f629`. | **ADAPT NARROWLY** to insert preparation after causal gating and before views. |
| `RH-IMP-005` | Typed restore state/reason and `HostAllocWakeArbiter`. | **ADOPT AS SEPARATE OWNER**; RH preparation does not wake or rank HOST_ALLOC. |
| `RH-IMP-006` | Unified full-span allocation and hybrid finalization. | **ADOPT AS LOWER-LAYER AUTHORITY**. |
| `RH-MATCH-IMP-001` | `Req.init_next_round_input(tree_cache, cow_mamba=False)` refreshes fill IDs and reuses all existing match geometry. | **ADOPT** as the sole match implementation; do not add a parallel walker. |
| `RH-MATCH-IMP-002` | `_prefetch_kvcache_impl` already performs the same non-COW match immediately before storage gating. | **ADAPT** so a valid one-shot result is consumed; retain one fallback rematch. |
| `RH-MATCH-IMP-003` | `node_exists`, `is_root`, and `prefetch_gate_ok`. | **ADOPT** for consumption-time anchor validity and mode-specific gate truth. |
| `RH-MATCH-IMP-004` | Unified match refreshes LRU/access metadata, may split a node, and applies cache actions. | **ADOPT AS CONSTRAINED MUTATING OPERATION**; do not describe it as read-only or call it twice normally. |
| `RH-MATCH-IMP-005` | Mamba finalizer returns immediately when `cow_mamba` is false. | **ADOPT** as no-Mamba-allocation boundary, with negative counters/field oracles. |
| `RH-MATCH-IMP-006` | `reset_for_retract` increments `retraction_count`, clears device anchor, and leaves host anchor uncleared. | **ADAPT** `retraction_count` into ticket identity and require rematch. |
| `RH-MATCH-IMP-007` | Active `chunked_req` is outside the waiting frontier; admission later invokes its own request initialization/COW. | **ADOPT UNCHANGED**; no ticket crosses either boundary. |

### 5.2 Anti-patterns and bug-derived patterns

| ID | Evidence | Disposition |
| --- | --- | --- |
| `RH-ANTI-001` | RH excludes HOST_ALLOC/REVALIDATE and other non-stageable states. | **ADOPT AS NEGATIVE BOUNDARY**. |
| `RH-ANTI-002` | Prior per-pass polling caused issue/revoke spin. | **REJECT** preparation before/without the causal refill gate. |
| `RH-ANTI-003` | Prior reviews identify miss conflation, arbitrary crop, and auxiliary-only wake. | **REJECT** all three. |
| `RH-MATCH-ANTI-001` | Computing restore potential from fresh default or stale request match fields. | **REJECT**; current preparation is required for potentially stageable candidates. |
| `RH-MATCH-ANTI-002` | Matching before views and again unconditionally in issue. | **REJECT**; duplicates mutable match work. |
| `RH-MATCH-ANTI-003` | Boolean skip flag, RID-only cache, or persistent request `initialized` marker. | **REJECT**; insufficient identity/freshness and leaks across owners/passes. |
| `RH-MATCH-ANTI-004` | Preparing at enqueue or reusing across passes. | **REJECT**; queue residence and cache mutation invalidate provenance. |
| `RH-MATCH-ANTI-005` | Performing Mamba COW/allocation during speculative preparation. | **REJECT**; steals admission/pool lifecycle authority. |
| `RH-MATCH-ANTI-006` | Treating any root/default value as an automatically valid storage anchor. | **REJECT**; require current-match provenance, existence, and existing gate acceptance. |
| `RH-MATCH-ANTI-007` | RH directly evicts or allocates to make preparation succeed. | **REJECT**; match-owned actions are the only permitted mutations. |
| `RH-MATCH-ANTI-008` | Suppressing admission-time initialization/COW with an RH ticket. | **REJECT**; owners and timing differ. |
| `RH-BUG-001` | Positive KV+Mamba hits parked after full-span allocation failure. | **ADOPT AS HOST_ALLOC ORACLE ONLY**. |
| `RH-BUG-002` | Historical ~141/s deterministic miss issue/revoke spin. | **ADOPT AS CAUSAL-GATE ORACLE**. |
| `RH-MATCH-BUG-001` | Final `f629` RH-ON run: 5/5 `no_restore_potential`, no current pre-view match, no joinable RH issue. | **ADOPT AS PRIMARY DEFECT ORACLE**; rate remains not computable. |
| `RH-MATCH-BUG-002` | Retraction clears `last_node` but may preserve stale `last_host_node`. | **ADOPT AS STALE-ANCHOR ORACLE**. |

### 5.3 Harness and test patterns

| ID | Evidence | Disposition |
| --- | --- | --- |
| `RH-TST-001` | `3090-dev/test_ready_horizon_unit.py`; policy, causal, issue, claim, ON/OFF and logging cases. | **ADOPT/EXTEND**. |
| `RH-TST-002` | `3090-dev/test_ready_horizon_partition.py`. | **ADOPT UNCHANGED**. |
| `RH-TST-003` | Prefetch-budget split/registered restore budget tests. | **ADAPT** for no-refill and budget interaction. |
| `RH-TST-004` | Restore scheduler-feed and host-allocability harnesses. | **ADOPT AS NEIGHBORING AUTHORITY ORACLES**. |
| `RH-TST-005` | Storage regression telemetry, hybrid finalization, and durability cases. | **ADAPT** for match/Mamba negative oracles and joins. |
| `RH-MATCH-TST-001` | Existing `test_ready_pass_joins_raw_frontier_req_to_policy_view`. | **RETAIN**; proves request/view association, not current match preparation. |
| `RH-MATCH-TST-002` | Existing ON queue-first, OFF eager-order, active-claim, finalizer-aux, and hybrid-discard dependency-free tests. | **RETAIN** as unchanged baseline; insufficient alone for this fix. |
| `RH-MATCH-TST-003` | Design-specified 17-case deterministic contract covering fresh/root/stale/retracted/chunked/non-stageable/failure/non-COW/admission/OFF/HOST_ALLOC behavior. | **REQUIRE NEW OR EXTENDED TESTS**; no passing implementation evidence yet. |
| `RH-MATCH-TST-004` | Hash-pinned paired five-request RH-OFF/RH-ON replay protocol. | **ADAPT AS POST-IMPLEMENTATION SYSTEM ORACLE**; never substitute HTTP success for joins. |

### 5.4 Benchmark, deferred, and missing IDs

| ID | Evidence | Disposition |
| --- | --- | --- |
| `RH-BENCH-001` | Earlier live 3060 causal bundle. | **DIAGNOSTIC ONLY**; not current-fix acceptance. |
| `RH-MATCH-BENCH-001` | Final `f629` ON 5/5 HTTP 200 versus OFF 2/5 HTTP 200, with materially different/missing joins. | **DIAGNOSTIC ONLY**; no causal performance claim. |
| `RH-MATCH-BENCH-002` | Proposed per-candidate match count/duration, known-anchor, issue, ready-before-admission, allocator/COW deltas. | **REQUIRE AS MEASUREMENT CONTRACT** after implementation; thresholds beyond correctness are deferred. |
| `RH-DEF-001` | Lower sidecar-complete checkpoint discovery. | **DEFER**; outside RH preparation. |
| `RH-DEF-002` | Cross-process generation propagation. | **DEFER**. |
| `RH-DEF-003` | Performance/fairness tuning. | **DEFER**; fresh Task ID. |
| `RH-MATCH-DEF-001` | New pure/peek cache-match API. | **DEFER**; expands component interfaces and duplicates consensus logic. |
| `RH-MATCH-DEF-002` | Persisted/cross-pass ticket with cache generation. | **DEFER/REJECT FOR MINIMAL FIX**; requires a new authority design. |
| `RH-MISS-001` | Earlier corpus found no canonical template/stable corpus. | **HISTORICAL GOVERNANCE GAP**; canonical RH intake now exists, but IDs remain artifact-local. |
| `RH-MISS-002` | Earlier corpus found no accepted RH-specific novel authority. | **RESOLVED ONLY FOR EXCLUSIVE ISSUE** by prior RH Novel gate; unresolved for match preparation. |
| `RH-MISS-003` | No evidence that RH may share HOST_ALLOC authority. | **PRESERVE AS NEGATIVE BOUNDARY**. |
| `RH-MISS-004` | Earlier corpus lacked current-HEAD live RH acceptance. | **PARTIALLY RESOLVED** by `f629` bounded traces; those traces expose this defect and do not accept the fix. |
| `RH-MATCH-MISS-001` | No accepted pattern for a one-pass capability that consumes a mutating prefix match across RH policy and issue. | **NOVEL TRIGGER**. |
| `RH-MATCH-MISS-002` | A post-fix implementation pin, bounded changed-file/symbol manifest, and coder-reported deterministic output exist; independent tester and reviewer acceptance do not. | **PARTIALLY RESOLVED; STILL BLOCKS IMPLEMENTATION ACCEPTANCE**, not completion of this intake. |
| `RH-MATCH-MISS-003` | No post-fix hash-pinned live ON/OFF evidence exists. | **BLOCKS SYSTEM/PERFORMANCE/TERMINAL CLAIMS**. |
| `RH-MATCH-MISS-004` | Package-backed RH execution previously lacked `orjson`. | **OPEN TEST-ENVIRONMENT LIMIT**; dependency-free evidence cannot be upgraded silently. |

No other relevant ID was found in the bounded source, test, gate, and supplied
runtime corpus. Absence is scoped to that corpus, not universal.

## 6. Atomic invariant → pattern → test mapping

The following mappings bind the proposed design; they do not claim that the
tests exist or pass. `MG-Tn` refers to the numbered deterministic cases in
section 7.

| Mapping | Atomic invariant | Pattern binding | Required oracle |
| --- | --- | --- | --- |
| `RH-MG-MAP-001` | Eligibility never uses uninitialized/stale anchors for a potentially stageable request. | Adopt `RH-MATCH-IMP-001`; reject `RH-MATCH-ANTI-001`; bug `RH-MATCH-BUG-001`. | `MG-T1`, `MG-T4`, `MG-T9`. |
| `RH-MG-MAP-002` | One causally due match per candidate before issue; one extra only after explicit invalidation. | Adopt `RH-IMP-002`, adapt `RH-MATCH-IMP-002`; reject `RH-MATCH-ANTI-002/004`. | `MG-T2`, `MG-T3`, `MG-T5`, `MG-T6`. |
| `RH-MG-MAP-003` | Non-COW preparation changes no Mamba allocation/COW fields and invokes no Mamba alloc/evict. | Adopt `RH-MATCH-IMP-005`; reject `RH-MATCH-ANTI-005`. | `MG-T7`, `MG-T8`, plus unchanged allocator counters. |
| `RH-MG-MAP-004` | Preparation creates no issue claim, reservation, storage query, restore transition, or readiness marker; only normal match-owned mutations are allowed. | Constrain `RH-MATCH-IMP-004`; reject `RH-MATCH-ANTI-007`. | `MG-T2`, `MG-T13`; action/LRU instrumentation distinguishes match from issue. |
| `RH-MG-MAP-005` | RH issue requires a valid current proof or completed fallback and the existing active-attempt claim. | Adapt `RH-IMP-004`, `RH-MATCH-IMP-002`; retain `RH-MATCH-TST-002`. | `MG-T2`, `MG-T5`, `MG-T6`; one claim/query/attempt. |
| `RH-MG-MAP-006` | A known anchor is current-match-proven, extant, and accepted by existing gate semantics. | Adopt `RH-MATCH-IMP-003`; reject `RH-MATCH-ANTI-006`. | `MG-T4`, `MG-T6`; default excludes, valid current root is gate-dependent. |
| `RH-MG-MAP-007` | RH-OFF preserves eager-before-append and constructs no preparation. | Adopt `RH-IMP-003/004`, retain `RH-MATCH-TST-002`. | `MG-T14`; AST/call-order plus behavioral spy. |
| `RH-MG-MAP-008` | Non-stageable, active-attempt, terminal, and active chunked requests receive no RH match or issue. | Adopt `RH-ANTI-001`, `RH-MATCH-IMP-007`. | `MG-T10`, `MG-T12`. |
| `RH-MG-MAP-009` | A retracted request cannot reuse its prior host anchor or ticket. | Adapt `RH-MATCH-IMP-006`; bug `RH-MATCH-BUG-002`. | `MG-T9`, `MG-T11`; `retraction_count` fence. |
| `RH-MG-MAP-010` | Admission always performs its separate match/COW; no ticket reaches `PrefillAdder`. | Adopt `RH-MATCH-IMP-007`; reject `RH-MATCH-ANTI-008`. | `MG-T8`, `MG-T10`, `MG-T11`. |
| `RH-MG-MAP-011` | RH owns no allocator/eviction; Mamba host victims retain flush-before-evict. | Adopt `RH-IMP-005/006`, `RH-MATCH-IMP-005`; reject `RH-MATCH-ANTI-007`. | `MG-T7`, `MG-T15`, `MG-T17`; unchanged event ordering. |
| `RH-MG-MAP-012` | Telemetry cannot validate an anchor, clear a negative, issue, wake HOST_ALLOC, or mark READY. | Adapt `RH-TST-005`; preserve `RH-MISS-003`. | `MG-T13`, `MG-T15`, `MG-T16`; logging on/off equivalence. |
| `RH-MG-MAP-013` | For an extant anchor, RH restore-potential eligibility and the existing prefetch gate agree that backuped, root, or L3-durable material is potentially restorable; all other anchors remain ineligible. | Adapt `RH-MATCH-IMP-003`; reject predicate drift between policy and issue. | `MG-T18`; positive and negative parity matrix over root/backuped/L3-durable/non-durable/missing anchors. |

## 7. Required test and evidence contract

The implementation gate must bind changed symbols to these atomic cases:

1. `MG-T1` fresh request prepares before restore-potential evaluation.
2. `MG-T2` prepared result is consumed once from refill through issue.
3. `MG-T3` no causal refill event means zero match and zero issue.
4. `MG-T4` current matched root is known only when the existing gate permits;
   default/uninitialized root-like state is unknown.
5. `MG-T5` token/session/retraction/key/salt/anchor identity changes each cause
   exactly one fallback rematch and no stale issue.
6. `MG-T6` deleted later-candidate anchor rematches or holds safely.
7. `MG-T7` non-COW preparation causes no Mamba alloc/evict/COW delta.
8. `MG-T8` admission still performs normal Mamba COW and cleanup.
9. `MG-T9` retracted request discards stale host anchor.
10. `MG-T10` active chunked request is never prepared.
11. `MG-T11` retracted chunked requeue gets a fresh match.
12. `MG-T12` RESTORING, active attempt, READY, HOST_ALLOC, REVALIDATE,
    FRONTIER, BACKUP_PENDING, and terminal cases produce zero RH match/issue.
13. `MG-T13` preparation failure fails closed with no stale/default issue.
14. `MG-T14` RH-OFF call order/match count is unchanged.
15. `MG-T15` the 54,976-required/21,057-free/zero-evictable hybrid fixture
    preserves HOST_ALLOC all-domain generation and FIFO/full-span behavior.
16. `MG-T16` existing claim, stale-terminal, discard, auxiliary readiness,
    negative-cache, causal-event, and telemetry-join suites remain green.
17. `MG-T17` existing Mamba flush-before-evict tests retain event order in
    RH-OFF and RH-ON fixtures.
18. `MG-T18` `has_restore_potential` and `prefetch_gate_ok` agree for extant
    backuped, root, and L3-durable anchors, reject an extant non-durable anchor,
    and reject a missing anchor. The test must execute the real two methods;
    source-text/AST matching alone is insufficient.

Post-implementation bounded evidence must pin the descendant revision and run
paired RH-OFF/RH-ON fresh processes under the same five-request 55K protocol.
Acceptance requires one preparation per normal ON initial issue, a second match
only with an invalidation record, no default-field `no_restore_potential`, no
preparation-time Mamba allocation/COW, unchanged OFF behavior, complete
attempt-correlated finalize/readiness/admission joins, and missing data reported
as missing. HTTP completion and latency are observations, not substitutes.

## 8. Ownership, dependencies, and allowed scope

| Concern | Owner/invariant |
| --- | --- |
| Causal timing and ephemeral proof | Scheduler `_ready_horizon_pass`; proof lives for one pass only. |
| Match geometry and mutations | Existing `Req.init_next_round_input` and cache `match_prefix`; no parallel walker. |
| Policy eligibility | Existing `ReadyHorizonView`/policy, after preparation. |
| Issue claim and storage gate | Existing `_prefetch_kvcache` path; consumption cannot bypass claim or `prefetch_gate_ok`. |
| Allocation/finalization/HOST_ALLOC | Existing cache, allocator, finalizer, restore arbiter; unchanged. |
| Mamba COW and admission | Existing admission-time owner; unchanged and never suppressed. |
| Durability | Existing Mamba flush-before-evict; unchanged. |
| Telemetry | Observational only. |

The pinned implementation was authorized only in:

- `python/sglang/srt/managers/scheduler.py`, for the one-pass preparation,
  validation/consumption, fail-closed fallback, and telemetry contract;
- `python/sglang/srt/mem_cache/unified_radix_cache.py`, only in
  `UnifiedRadixCache.has_restore_potential`, and only to add L3-durable parity
  with the existing `prefetch_gate_ok` extant-anchor disjunction;
- focused tests under `3090-dev/` and existing registered scheduler/cache test
  locations, without production fixture or harness authority changes.

Changes to any other cache symbol, cache traversal/component, `schedule_batch.py`,
allocator/finalizer, persistence, HOST_ALLOC, remote/deployment file, or durable
format exceed this intake and require a fresh Task ID and gate chain.

## 9. Risks, reversibility, and handoff

Primary risks are mutable cache effects before issue claim, an earlier
candidate invalidating a later anchor, duplicate match cost, false root
provenance, and accidental suppression of admission-time COW. The causal
placement, one-pass lifetime, identity and extance validation, one-rematch
fallback, match counters, and Mamba negative oracles contain and expose them.

No persistent data, wire format, storage key, or mixed-version migration is
proposed. Rollout is drain/restart. Rollback is drain/restart with RH disabled
or revert the bounded scheduler-plus-predicate descendant. Removal deletes the
ephemeral ticket, preparation/consumption branch, exact L3 parity clause, and
its telemetry/tests; the accepted
exclusive-issuer, RH-OFF, cache, HOST_ALLOC, and durability contracts remain.

Verdict: **ARCHITECT ACCEPT** for the exact scope above, including the single
`has_restore_potential` parity clause. The orchestrator accepted this design
chain and pinned `implementation_revision` to
`9213ee01d90ba3925e7fe928e80cc41354ee4fff`. This artifact is not
self-approving implementation authority. Independent implementation review,
tester acceptance, deployment, performance, runtime value, and terminal
acceptance remain pending.

Extra corpus, research, design, implementation, test, deployment, or review
work requires a fresh Task ID.
