# Pattern Intake — Ready Horizon pre-admission

```yaml
schema_version: project-contract-full-intake-1
schema_basis: AGENTS.md Pattern Intake and Novel Mechanism Gate
artifact_id: PI-RH-PREADMISSION-20260909-01
task_id: ARCH3060-RH-PATTERN-20260909
orchestration_epoch: 20260909-rh-ab18
role: architect
target_repository: /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt
target_branch: 3060-12g-qwen35-4b
corpus_revision: 82ab235606233160701b15f657a71794cfd29a30
implementation_revision: f629d4e2c19eb74571b4154438fd651ce24ff53b
classification: FULL_INTAKE_REQUIRED
disposition: ACCEPTED_FOR_FINAL_IMPLEMENTATION_REVISION
gate_verdict: ACCEPT
implementation_admission_recommendation: IMPLEMENTATION_AUTHORIZED_FOR_INDEPENDENT_REVIEW
novel_mechanism_trigger: RH_HOST_ALLOC_AUTHORITY_OR_FAILURE_BOUNDARY_COMPOSITION
decision_authority: orchestrator_and_existing_gate_owners
```

## 1. Decision, assumptions, and authority

This intake inventories the bounded repository evidence for Ready Horizon
(RH) pre-admission. It recommends the known-pattern path only for work that
preserves RH's existing READY_HOST staging, causal refill, and READY-first
admission ownership. It does not approve a design, implementation, test result,
or gate verdict; those decisions remain with the orchestrator and existing gate
owners.

Observed facts from the supplied corpus report:

- RH owns READY_HOST staging, per-request negative caching, causal refill, and
  READY-first queue partitioning.
- Restore/scheduler code owns `HOST_ALLOC`, `WAIT_CAPACITY`, allocation retry,
  and FIFO retry admission.
- RH release epochs and host-allocability generations have different owners
  and semantics.
- Known local patterns cover an RH-only change, but no accepted RH-specific
  Novel Mechanism/design-authority ID or proof that RH may wake `HOST_ALLOC`
  exists.

Explicit assumptions and limits:

- “RH” means the repository's Ready Horizon mechanism.
- No concrete implementation proposal, symbol manifest, or changed interface
  was supplied to this intake. The recommendation is therefore boundary-based,
  not an approval of unspecified code.
- Source and test claims below are inherited from the supplied scout report and
  were not independently broadened into a new corpus search.
- Intake-local IDs are stable within this artifact and its pinned revision;
  they are evidence identifiers, not design authority.
- No canonical full-intake template was found. This artifact follows every
  required field in the project contract while explicitly recording that
  schema limitation.

Pre-admission recommendation:

1. **Known-pattern path:** eligible for orchestrator/gate-owner consideration
   only when the proposed change stays inside existing RH ownership, adopts the
   positive patterns, preserves all negative boundaries, and binds every
   changed invariant to the mapped test oracle.
2. **Novel path:** blocked from G1/G2 whenever the proposal lets RH wake, rank,
   fit, retry, or otherwise govern `HOST_ALLOC`; merges telemetry with decision
   authority; creates a cross-process generation mechanism; or changes another
   authority/failure boundary. Such work requires a separately accepted Novel
   Mechanism declaration and architecture/system/technology/algorithm gates.
3. **Terminal acceptance:** not established here. It still requires the chain
   from authority invariant to accepted pattern or Novel Mechanism, accepted
   implementation shape, changed symbol, test case/oracle, immutable evidence,
   and independent review.

## 2. Corpus pin, scope, and exact searches

Authoritative supplied corpus input:

- Report:
  `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/SCOUT-20260909-RH-PATTERN-CORPUS.md`
- Report SHA-256:
  `51fa53261a4c656b741cef40fae4270b43eb4d3d21fd95e9e5b97781e6c2e155`
- Corpus revision: `82ab235606233160701b15f657a71794cfd29a30`
- Branch: `3060-12g-qwen35-4b`

Searched scope reported by the scout: the target repository, gate directories,
Python source, `3090-dev`, and `test`; Git history only for gate, RH, and
host-allocation names. External repositories, remote hosts, storage contents,
and unrelated private data were excluded. Presence/absence claims are bounded
to that scope.

Exact discovery/search commands recorded by the supplied report:

```text
git -C /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt status --short --branch
git -C /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt rev-parse HEAD
git -C /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt branch --show-current
rg --files review/gates storage/review/gates
git ls-files review/gates storage/review/gates/pattern-intake
git log --all --oneline -- review/gates storage/review/gates/pattern-intake
git log --all --name-only --pretty=format: | rg -i 'pattern.intake|novel.mechanism|ready.horizon|host.alloc'
rg -n -i 'ready[_ -]?horizon|prefetch|restore|budget[_ -]?wait|admission|host[_ -]?ready|request[-_ ]correl|telemetry|residency|frontier|horizon' python 3090-dev test review/gates storage/review/gates
rg -n '^class |^def |^    def test_|CausalEpochs|RestoreState|RestoreWaitReason|WAIT_CAPACITY|HOST_ALLOC|prefetch_budget|admission|telemetry|request_id|trace_id|assert' <targeted source/test files>
```

## 3. Gate/context evidence manifest

These artifacts constrain interpretation; they are not reusable implementation
patterns and do not approve the RH proposal.

| ID | Evidence | Disposition |
| --- | --- | --- |
| `RH-GATE-001` | `review/gates/ARCH-20260909-HOST-ALLOC-EPOCH.md` distinguishes RH release epoch from HOST_ALLOC generation and specifies restore/admission/telemetry boundaries. | **USE AS PROPOSED BOUNDARY EVIDENCE**; pending authority, not implementation approval. |
| `RH-GATE-002` | `review/gates/PATTERN-INTAKE-20260909-HOST-ALLOC-EPOCH.md` is the closest prior intake shape, pinned to an older revision and self-described as blocked. | **ADAPT DOCUMENT SHAPE ONLY**; do not inherit revision or verdict. |
| `RH-GATE-003` | `review/gates/NOVEL-MECHANISM-20260909-HOST-ALLOC-EPOCH.md` describes a cross-boundary host-mutation/generation/cursor/FIFO/allocator/finalizer composition. | **NOT ADOPTED AS AUTHORITY**; proposed evidence only. |
| `RH-GATE-004` | `storage/review/gates/pattern-intake/EXEMPT-3060-RUNTIME-COMPAT.md` is the sole prior canonical-directory artifact and is a narrow maintenance EXEMPT. | **NOT ADOPTED**; RH semantic work requires full intake. |
| `RH-GATE-005` | `review/gates/REVIEW-20260909-HYBRID-FRONTIER-GUARD.md` supports no arbitrary sidecar crop, KV-only compatibility, all-or-nothing hybrid discard, and scheduler prefetch wake. | **ADOPT AS REVIEW EVIDENCE**, not canonical pattern authority. |
| `RH-GATE-006` | `review/gates/REVIEW-20260909-CAPACITY-SEMANTICS.md` records allocation failure misclassified as a genuine miss. | **ADOPT AS NEGATIVE EVIDENCE**; verdict was REJECT. |
| `RH-GATE-007` | `review/gates/REVIEW-20260909-ALLOC-FAILED-TERMINAL.md` supports terminal mapping among `revoked_alloc_failed`, `DENIED_ALLOC`, `HOST_ALLOC`, and `WAIT_CAPACITY`. | **ADOPT AS CURRENT SOURCE/TEST EVIDENCE** only. |
| `RH-GATE-008` | `review/gates/REVIEW-DEEP-20260909-HOST-ALLOC-EPOCH-TELEMETRY-FINAL.md` accepts current-HEAD telemetry fixes with a bounded-sampling trade-off and live prerequisites. | **ADOPT AS COMMIT REVIEW EVIDENCE**; not canonical pattern authority. |

## 4. Complete relevant pattern corpus and dispositions

### 4.1 Stable implementation patterns

| ID | Path / symbol and observed role | Disposition |
| --- | --- | --- |
| `RH-IMP-001` | `ready_horizon.py:101-187`: `CausalEpochs`, `NegativeCacheEntry`, `ReadyHorizonView`, `RefillPlan`; typed cursor/event inputs, request identity, decline reasons, immutable policy inputs. | **ADAPT** cursor/event concepts only. RH must not become HOST_ALLOC authority. |
| `RH-IMP-002` | `ready_horizon.py:546-578`: `epoch_event`, `should_refill`; event-driven refill via release counter, budget release, frontier changes, and periodic safety reconciliation. | **ADOPT FOR RH** event-gated refill; **DO NOT ADOPT** as proof of host-allocation fit. |
| `RH-IMP-003` | `ready_horizon.py:581-660`: `partition_ready_first`; resident-marker READY membership and stable READY-first ordering with priority boundaries. | **ADOPT** for RH admission ordering; preserve OFF-mode no-op. |
| `RH-IMP-004` | `scheduler.py:1421-1462, 3804-4106, 5028-5093`; initializes RH, builds views/epochs, invokes RH pass, conditionally partitions waiting queue. | **ADOPT AS EXISTING INTEGRATION BOUNDARY**; keep RH delegated and out of scheduler-wide allocation ownership. |
| `RH-IMP-005` | `hicache_restore.py`: `RestoreState`, `RestoreWaitReason`, `HostAllocWakeArbiter`; typed restore reasons/state and scheduler-owned FIFO retry helper. | **ADAPT/KEEP SEPARATE**; RH may consume read-only state/reason views, while HOST_ALLOC wake remains restore/scheduler-owned. |
| `RH-IMP-006` | `unified_radix_cache.py` storage-hit/prefetch allocation path; full-span alloc/reclaim and hybrid finalization. | **ADOPT AS LOWER-LAYER AUTHORITY**; RH must not infer lower checkpoints, crop, or declare fit. |

### 4.2 Anti-patterns and bug-derived patterns

| ID | Evidence | Disposition |
| --- | --- | --- |
| `RH-ANTI-001` | RH contract/tests exclude `HOST_ALLOC` and `REVALIDATE` from staging. | **ADOPT AS BOUNDARY/NEGATIVE PATTERN**: HOST_ALLOC is not RH-stageable. |
| `RH-ANTI-002` | RH documentation/tests identify per-pass polling/retry spin; `epoch_event` rejects unchanged epochs. | **REJECT** generic per-pass wake or polling. |
| `RH-ANTI-003` | Capacity/hybrid reviews record miss conflation, arbitrary crop, and scalar-only auxiliary wake risks. | **REJECT** miss conflation, arbitrary crop, and scalar-only auxiliary wake. |
| `RH-BUG-001` | Positive KV+Mamba q/x/w hits parked until T13 after allocation failure. | **ADOPT AS FAILURE ORACLE ONLY**; do not infer physical capacity impossibility. |
| `RH-BUG-002` | Prior deterministic miss retry spin was approximately 141/s and 1,289 issues in 9.04 seconds. | **ADOPT AS RETRY-STORM ORACLE**; a safety fuse is a bound, not normal wake authority. |

### 4.3 Harness and test patterns

| ID | Evidence | Disposition |
| --- | --- | --- |
| `RH-TST-001` | `3090-dev/test_ready_horizon_unit.py:241-1204`; frontier, strict markers, filtering, per-RID cache, headroom, event gating, no-op, release wake, logging, deterministic miss parking. | **ADOPT/EXTEND** as RH oracle corpus. |
| `RH-TST-002` | `3090-dev/test_ready_horizon_partition.py:74-404`; stable partition, priority, OFF/idle no-op, order preservation, head-of-line skip, gate wiring. | **ADOPT** for admission-order invariants. |
| `RH-TST-003` | `3090-dev/test_prefetch_budget_split_unit.py` and registered restore-prefetch-budget tests. | **ADAPT** for RH `SPEC_BUDGET`; not evidence that HOST_ALLOC fits. |
| `RH-TST-004` | Restore scheduler-feed and host-allocability harnesses. | **ADAPT AS NEIGHBORING ORACLES** while keeping HOST_ALLOC outside RH ownership. |
| `RH-TST-005` | `3090-dev/test_storage_regression.py:2489+`; request-correlated telemetry and hybrid finalize assertions. | **ADAPT** for observational joins; not a complete RH authority oracle. |

### 4.4 Benchmark, deferred, and missing corpus items

| ID | Evidence | Disposition |
| --- | --- | --- |
| `RH-BENCH-001` | Live 3060 causal bundle summarized by the older HOST_ALLOC intake; no current-HEAD live RH benchmark/runtime pass in bounded scope. | **DIAGNOSTIC ONLY**; cannot substitute for deterministic or post-change acceptance. |
| `RH-DEF-001` | Lower sidecar-complete checkpoint discovery. | **DEFER**; outside RH admission and requires a fresh Task ID. |
| `RH-DEF-002` | Cross-process generation propagation. | **DEFER**; current evidence is same-process/cache-instance only and new work requires a fresh Task ID. |
| `RH-DEF-003` | Performance/fairness tuning beyond one FIFO grant. | **DEFER**; no accepted benchmark oracle, fresh Task ID required. |
| `RH-MISS-001` | Canonical full Pattern Intake template and stable repository corpus. | **RECORDED GOVERNANCE GAP**; this artifact uses contract-required fields without claiming a pre-existing full schema. |
| `RH-MISS-002` | Accepted RH-specific Novel Mechanism/design-authority ID. | **BLOCKING IF NOVEL TRIGGER FIRES**; no accepted ID found. |
| `RH-MISS-003` | Test proving RH and HOST_ALLOC share authority or that RH release epochs may wake HOST_ALLOC. | **NEGATIVE BOUNDARY**; no such proof found, and architecture evidence separates ownership. |
| `RH-MISS-004` | Current-HEAD live 3060 RH acceptance evidence. | **BLOCKING FOR LIVE/TERMINAL CLAIMS**, not for completion of this intake. |

No other relevant stable implementation, anti-pattern, bug-derived,
harness/test, benchmark, deferred, or missing ID was reported in the pinned
bounded scope. This is not a claim about external or unavailable corpora.

## 5. Atomic invariant → pattern → test mapping

Each mapping is atomic and independently reviewable. Named tests are candidate
or existing oracles from the supplied report; this intake does not claim they
were executed or that they cover an unspecified future diff.

| Mapping ID | Atomic invariant | Pattern evidence/disposition | Required test oracle |
| --- | --- | --- | --- |
| `RH-MAP-001` | READY means required host material is physically resident and full-prefix compatible; consumed/dropped markers are not READY. | Adopt `RH-IMP-003`; extend `RH-TST-001/002`. | `test_ready_requires_resident_marker`, `test_dropped_insert_is_not_pool_material`, `test_consumed_marker_not_counted`, `test_partial_prefix_not_pool_material`. |
| `RH-MAP-002` | Only stageable restore reasons enter RH candidates; `HOST_ALLOC`, `REVALIDATE`, frontier, and backup-pending states do not. | Adopt boundary `RH-ANTI-001`; keep `RH-IMP-005` separate. | `test_ack_driven_and_untestable_reasons_excluded`, `test_non_stageable_states_excluded`, plus an explicit HOST_ALLOC exclusion case. |
| `RH-MAP-003` | Headroom and speculative-budget declines never evict; retry occurs only on the subscribed causal signal or safety bound. | Adopt `RH-IMP-002`; use `RH-BUG-002` as failure oracle; adapt `RH-TST-003`. | `test_headroom_shortfall_never_evicts`, `test_no_headroom_park_wakes_on_release_epoch_not_level`, `test_spec_budget_cleared_only_by_budget_release`, `test_fuse_expiry_is_only_a_safety_bound`. |
| `RH-MAP-004` | Unchanged epochs and RH refill self-traffic produce no repeated issue. | Reject `RH-ANTI-002`; adopt `RH-IMP-002`. | `test_identical_epochs_no_event`, `test_refill_own_issue_traffic_no_event`, `test_no_event_epoch_no_refill`. |
| `RH-MAP-005` | READY-first partition preserves explicit-priority groups and relative order; OFF mode is behavior-preserving. | Adopt `RH-IMP-003/004` and `RH-TST-002`. | Stable-partition, priority-boundary, order-preservation, idle/OFF no-op, and scheduler gate-wiring tests. |
| `RH-MAP-006` | Positive allocation pressure remains a restore/HOST_ALLOC decision; RH never converts it to a genuine miss, infers a lower frontier, crops, or declares fit. | Adopt `RH-IMP-005/006`, `RH-ANTI-001`, `RH-BUG-001`; reject `RH-ANTI-003`; account for `RH-MISS-003`. | Neighboring scheduler-feed/host-allocability cases plus negative RH HOST_ALLOC-staging, no-miss-conflation, and no-crop assertions. |
| `RH-MAP-007` | Request-correlated telemetry is observational; absence or sampling of telemetry cannot alter wake, fit, staging, partition, or retry decisions. | Adapt `RH-TST-005`; apply boundary evidence `RH-GATE-001/008`. | RID/attempt join fixture where available, paired with an assertion that telemetry enabled/disabled/sampled yields identical RH and restore decisions. |

## 6. Ownership, interfaces, and dependencies

| Boundary | Owner | Allowed dependency/interface | Forbidden dependency |
| --- | --- | --- | --- |
| READY_HOST staging and negative cache | RH policy | Typed read-only request, restore-state, resident-marker, budget, frontier, and causal-epoch views. | Mutation of restore allocator state or interpretation of HOST_ALLOC as RH-stageable. |
| READY-first admission ordering | RH policy, invoked by scheduler | Stable partition result preserving explicit priorities and relative order. | Scheduler-wide allocation ownership or hidden reorder across priority boundaries. |
| HOST_ALLOC wait/retry/fairness | Restore/scheduler | Typed reason/state views may be observed by RH only to exclude them. | RH wake, fit, retry, queue rank, or release-epoch authority. |
| Full-span allocation/reclaim/hybrid finalization | Unified cache/allocator layer | Existing complete-frontier allocation outcome and resident markers. | RH lower-frontier inference, arbitrary crop, or partial hybrid READY declaration. |
| Telemetry | Observability path | Request/attempt correlation emitted after decisions. | Telemetry presence, absence, or sampling as a decision input. |

The architectural invariant is one-way evidence flow into RH policy. RH may
consume typed snapshots but must not acquire mutation or retry authority from
the owners that produce them.

## 7. Structural trade-offs, risks, and reversibility

- Event-gated refill suppresses retry storms and creates deterministic causal
  tests, at the cost of relying on complete event attribution. The periodic
  safety reconciliation bounds missed-signal risk but must not become ordinary
  polling authority.
- Stable READY-first partition improves admission locality while preserving
  explicit priority and order. Extending it across priority groups would alter
  scheduler semantics and is outside the known-pattern path.
- Keeping HOST_ALLOC outside RH prevents wake/fit semantic conflation and
  preserves allocator ownership. A future cross-boundary optimization could
  reduce latency, but adds fairness, failure-domain, and causal-generation
  interfaces and is therefore a Novel Mechanism candidate.
- Strict resident/full-prefix markers can decline more candidates than looser
  heuristics, but make READY observable and prevent consumed, dropped, cropped,
  or partially finalized state from being admitted.
- Request-correlated telemetry aids diagnosis. Bounded sampling can lose some
  observations; because telemetry is non-authoritative, that loss must not
  affect behavior.

Known-pattern RH changes should preserve the existing OFF-mode no-op as the
rollback boundary. They introduce no durable format or cross-process migration
in this intake. Reversal is structurally local if the implementation remains
behind existing RH integration and removes only RH-owned fields/logic. Any
change that adds typed cross-owner state must define compatibility, mixed-
revision behavior, migration, rollback, and removal in its Novel Mechanism and
architecture contracts before implementation admission.

## 8. Handoff and open conditions

Recommendation to the orchestrator: accept this intake as evidence for an
RH-only known-pattern implementation dispatch only after the proposed change
is checked against sections 1, 5, and 6. If any novel trigger fires, require a
fresh, separately accepted Novel Mechanism declaration containing why known
patterns do not fit, atomic invariants, failure model, observable oracle,
corpus evidence, alternatives, and migration/rollback/removal path.

Open conditions:

- No concrete implementation shape or changed-symbol manifest was available
  to classify against the boundary.
- `RH-MISS-002` remains unresolved for any RH/HOST_ALLOC composition.
- `RH-MISS-004` prevents live or terminal acceptance claims.
- Gate owners must bind future changed symbols and immutable test evidence to
  `RH-MAP-001` through `RH-MAP-007`; this intake does not perform that review.

Extra corpus, research, design, implementation, test, deployment, remote, or
storage work requires a fresh Task ID.

Status: `done` for this authorized Pattern Intake artifact.

## 9. Final implementation reconciliation — 2026-09-09

This section supersedes the conditional implementation statements in sections
1 and 8 for the exact implementation revision below. It does not change the
original corpus pin: the searched corpus remains revision
`82ab235606233160701b15f657a71794cfd29a30`. The separately bound implementation
revision is `f629d4e2c19eb74571b4154438fd651ce24ff53b` on
`3060-12g-qwen35-4b`.

### Decision

**Pattern Intake verdict: ACCEPT.** The final implementation follows the
adopted/adapted RH patterns, contains the declared novel exclusive-owner
composition, and preserves the negative authority boundaries. It is admitted
to independent implementation review. This verdict accepts the design/intake
chain only; it is not a G-IMPL or reviewer acceptance and makes no live or
performance claim.

### Final change manifest

The implementation range `82ab235606..f629d4e2c1` consists of commits
`3ddc39c223`, `3785c99759`, `7831d45dd4`, `6881529acb`, `67b39b5aca`,
`6edf69ce29`, and `f629d4e2c1` and
changes exactly these nine files:

- `python/sglang/srt/managers/scheduler.py`: queue-first RH-ON routing, RH-OFF
  eager routing, explicit origins, active-attempt claim/release, typed issue
  result use, stale terminal fence, bounded RH event joins, and discarded
  hybrid recompute/no-ready handling. The final descendant joins each raw
  frontier `Req` to its `ReadyHorizonView` before reading policy-only fields.
- `python/sglang/srt/managers/schedule_batch.py`: ephemeral request-local
  attempt, origin, decision-fingerprint, and enqueue-sequence fields.
- `python/sglang/srt/managers/scheduler_components/hicache_restore.py`:
  `HiCachePrefetchOrigin`, `HiCachePrefetchIssueStatus`, and frozen
  `PrefetchIssueResult`.
- `python/sglang/srt/mem_cache/unified_radix_cache.py`: attempt-correlated
  terminal/completion handoff and finalizer-owned KV/auxiliary completion data.
- `3090-dev/test_ready_horizon_unit.py`,
  `3090-dev/test_hicache_restore_scheduler_feed.py`,
  `3090-dev/test_prefetch_gate_skip_regression.py`,
  `3090-dev/test_rh_contract_dependency_free.py`, and
  `3090-dev/test_storage_regression.py`: contract and regression oracles,
  including the raw-frontier-request to policy-view regression.

No allocator, HOST_ALLOC-generation, persistence-format, remote-runtime, or
3090-branch change is present in that range.

### Invariant → pattern → changed symbol → test evidence

| Invariant | Pattern binding | Final symbol(s) | Evidence and disposition |
| --- | --- | --- | --- |
| RH-ON has one queue-first initial owner; RH-OFF keeps eager-before-append | `RH-IMP-003/004`, `RH-TST-001/002`, Novel `RH-PA-I1..I4` | `Scheduler._add_request_to_queue`, `Scheduler._ready_horizon_pass` | `test_rh_on_enqueue_is_queue_first_and_rh_owned`, `test_rh_off_enqueue_preserves_eager_order_and_origin`, and final source inspection: **ACCEPT**. |
| RH decisions read policy-only eligibility and state from the typed view corresponding to each raw frontier request | `RH-IMP-001/004`, `RH-TST-001`, Novel `RH-PA-I2` | `Scheduler._ready_horizon_pass`, `ReadyHorizonView` | `test_ready_pass_joins_raw_frontier_req_to_policy_view` and independent tester report `TEST3060-RH-VIEW-TYPE-20260909.md`: **ACCEPT**. |
| A successful issue is `ISSUED` and retains one active attempt | `RH-IMP-004/006`, Novel `RH-PA-I1/I5/I10` | `_claim_prefetch`, `_prefetch_kvcache`, `_prefetch_kvcache_impl`, `PrefetchIssueResult` | Gate-pass regression plus dependency-free lifecycle evidence; corrected by `7831d45dd4`: **ACCEPT**. |
| A stale completion cannot clear or transition a newer attempt | `RH-IMP-005/006`, Novel `RH-PA-I5/I10` | `_release_prefetch_claim`, `_feed_restore_terminal`, `record_storage_prefetch_terminal` | `test_stale_release_cannot_clear_newer_claim` and tester stale-terminal harness: **ACCEPT**. |
| READY requires finalizer-authoritative complete KV+auxiliary material | `RH-MAP-001/006/007`, `RH-IMP-006`, `RH-ANTI-003`, Novel `RH-PA-I6/I7` | `_host_alloc_hybrid_completion`, `_handle_prefetch_result`, `_feed_restore_terminal` | `test_ready_host_aux_fields_come_from_finalizer_completion`, storage durability cases, and actual auxiliary values: **ACCEPT**. |
| Discarded/rejected hybrid material cannot become READY or emit `ready_host` | `RH-ANTI-003`, Novel `RH-PA-I7` | `_handle_prefetch_result`, `_feed_restore_terminal` | `test_discarded_finalization_cannot_be_ready_host`; final path applies `DENIED_SHORT`, state `NONE`, no event: **ACCEPT**. |
| HOST_ALLOC/Mamba/allocator authority remains separate | `RH-IMP-005/006`, `RH-ANTI-001`, `RH-MAP-006` | Existing host allocation arbiter/finalizer; RH additions consume only explicit outcomes | Seven-commit scope audit and focused restore/storage regressions found no authority transfer: **ACCEPT within design scope**. |
| Telemetry is correlated and observational | `RH-MAP-007`, `RH-TST-005` | `_emit_rh_decision`, `_ready_horizon_pass`, `_feed_restore_terminal`, admission logging | Required-field AST test and final source inspection cover decision/stage/ready/admission schemas: **ACCEPT for schema/design; live join unverified**. |

### Resolved blocks and remaining limits

- The earlier tester BLOCK at `7831d45dd4` identified null auxiliary readiness
  fields; `6881529acb` binds them to finalizer-owned actual KV/auxiliary data.
- The later tester BLOCK at `6881529acb` identified discarded hybrid material
  reaching READY; `67b39b5aca` fences discarded/rejected results to recompute
  and suppresses `rh_ready_host.v1`.
- The final descendant `f629d4e2c1` fixes the observed RH startup type mismatch
  by mapping raw frontier requests to their policy views before evaluating
  `staging_eligible` or `state`. Independent tester report
  `TEST3060-RH-VIEW-TYPE-20260909.md` (SHA-256
  `f85a535ddba7cf88760a7c157cc171041f140c1186a102501fb24af83d7996b7`)
  records ACCEPT and a passing 6/6 dependency-free contract run.
- Project-backed RH unit/scheduler-feed execution remains unavailable because
  `orjson` is missing. Dependency-free and focused source-loaded regressions
  passed as reported; this gate does not upgrade them into full runtime proof.
- The bounded RH-OFF/RH-ON traces were collected against the earlier corpus
  source, not `f629d4e2c1`; there is no final-revision live/deploy-hash evidence.
  RH-G11, performance, fairness, and deployment claims remain open.
- Independent implementation review remains required. Acceptance here is
  reversible by draining active requests and restarting with RH disabled; no
  persistent-data migration was introduced.
