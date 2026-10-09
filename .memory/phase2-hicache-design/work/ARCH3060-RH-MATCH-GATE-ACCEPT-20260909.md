ENTRY: ACCEPT

status: done
task_id: T3060-RH-MATCH-GATE-ACCEPT-20260909
orchestration_epoch: 20260909-rh-ab49
role: architect/gate owner

## Artifacts

- Revised Pattern Intake:
  `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/storage/review/gates/pattern-intake/PATTERN-INTAKE-20260909-RH-MATCH-PREP.md`
  - artifact ID: `PI-RH-MATCH-PREP-20260909-02`
  - SHA-256: `a9bb2520e757bf4426c34206239ea3a6df7a41688e3f6410c3bc80dbb085414e`
- Revised Novel Mechanism:
  `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/review/gates/NOVEL-MECHANISM-20260909-RH-MATCH-PREP-R2.md`
  - artifact ID: `NM-RH-MATCH-PREP-20260909-02`
  - SHA-256: `1587ed5b44b30b2c198707a1a9a79b3e6b76a76c5218f06336533f1a682cd526`
- Architecture gate:
  `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/review/gates/ARCH-20260909-RH-MATCH-PREP.md`
  - artifact ID: `ARCH-RH-MATCH-PREP-20260909-02`
  - SHA-256: `09f673f42b5e6ac5bde2f6d7a6e8ed2926ff24deafaed7f583f505596c267822`
- This report:
  `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/ARCH3060-RH-MATCH-GATE-ACCEPT-20260909.md`

No product source, test source, deployment state, or runtime process was
modified by this invocation.

## Evidence

### Observed facts

- Reviewer `REVIEW-20260909-RH-MATCH-PREP.md` blocked on four items: pending
  design authority, unauthorized `has_restore_potential` scope, absent real
  one-shot/fallback/no-COW integration oracles, and incomplete telemetry.
- The reviewed source worktree remains at
  `f629d4e2c19eb74571b4154438fd651ce24ff53b` with an uncommitted five-file
  product/test diff. Its SHA-256 remains
  `5a0d210512b1eddb9dde8206b6e340879568b42c3d579ee5f672f5f6b51109c2`.
- The current diff adds only one cache semantic clause:
  `UnifiedRadixCache.has_restore_potential` recognizes an extant anchor when
  `tree_core.is_l3_durable(anchor_node_id)` is true.
- Existing `prefetch_gate_ok` already recognizes the corresponding extant
  L3-durable anchor. Thus the current change aligns policy-side potential with
  issue-side gate eligibility; it does not create durability or issue
  authority.
- Current dependency-free tests pass, but the valid-ticket test does not run
  through the real issue implementation, the pass test stubs preparation, and
  no real component-backed oracle proves unchanged Mamba COW/allocator state.
- Current telemetry lacks required duration, explicit Mamba field/counter
  deltas, buffer-device-fallback classification, and complete candidate
  disposition/join fields.

### Assumptions retained for implementation review

- Scheduler ownership serializes preparation, planning, and immediate issue.
- Every relevant request identity change is fenced by the prepared-match value.
- The existing cache predicates use the same L3 durability truth source at the
  immutable descendant. If any assumption fails, this design is insufficient
  and requires fresh architecture authority.

### Gate decision

**ARCHITECT ACCEPT** the Pattern Intake, Novel Mechanism R2, and Architecture
gate as a coherent design recommendation, including the exact
`UnifiedRadixCache.has_restore_potential` L3-durable disjunct in the same narrow
eligibility-alignment boundary.

The alternative requiring removal/separate task is rejected for this exact
clause: removing it retains the observed policy/issue predicate mismatch, while
splitting a side-effect-free parity clause adds no useful ownership boundary.
This does not authorize general cache-layer edits. Any other cache symbol or
change to traversal, mutation, allocation, eviction, finalization, durability,
persistence, or interfaces requires a fresh Task ID.

The design chain is pinned to source/design baseline
`f629d4e2c19eb74571b4154438fd651ce24ff53b` and scope revision
`20260909-rh-ab49`. `implementation_revision` is intentionally `null` and the
current uncommitted diff is not accepted. A fresh coder must produce the next
immutable descendant commit; the orchestrator must accept this recommendation
and repin that full SHA before independent implementation review.

### Reviewer-PASS contract

The architecture gate specifies the exact mandatory `rh_match_prepare.v1`
schema, including stable identity/join fields, complete result/anchor enums,
duration/count/fallback fields, the three Mamba request-field deltas, and Mamba
alloc/evict counter deltas. Gate evidence requires unsampled capture and
explicit nulls.

Minimum executable evidence is eight groups: real valid-ticket path; real
invalidation/fallback path; fail-closed path; component-backed no-COW field and
allocator/evict counters; separate admission COW; retraction/chunk/nonstageable
lifecycle matrix; real-method L3 eligibility parity matrix; and unchanged
RH-OFF plus telemetry-failure independence. AST/source-extraction and stubbed
issue/preparation tests cannot substitute for the real integration oracles.

Artifact checksum and consistency checks passed. The product/test diff checksum
was recomputed read-only and matches the reviewer's pin.

## Summary

The reviewer’s design/scope blockers are resolved at the architect gate. The
L3-durable `has_restore_potential` adjustment is explicitly in scope as a
single predicate-parity exception within the RH current-match boundary. The
accepted implementation surface is `scheduler.py`, that exact cache method,
and focused tests. The telemetry and minimum integration/no-COW acceptance
oracles are now exact.

This is evidence-backed architect acceptance for orchestrator consideration,
not self-approval of implementation. Product implementation, immutable
revision pinning, tester acceptance, reviewer PASS, deployment, and runtime RH
value remain pending.

## Followups

- Orchestrator: accept or reject this architect recommendation and dispatch a
  fresh coder task constrained to the exact authorized symbols.
- Fresh coder: implement/correct the exact telemetry and testable interfaces,
  commit an immutable descendant, and provide a complete changed-symbol
  manifest. Do not broaden the cache exception.
- Fresh tester: run the package-backed mandatory real-path oracles and existing
  neighboring suites at that full SHA.
- Fresh reviewer: read this chain, the committed diff/manifest, and tester
  evidence; issue independent PASS/BLOCK. Only then may a separate runtime
  dispatch perform a hash-pinned RH-OFF/RH-ON replay.

## Open issues

- Orchestrator final acceptance is pending; architect artifacts are not
  self-approving authority.
- No immutable implementation revision exists yet; current worktree diff is
  evidence only.
- The current implementation does not satisfy the exact telemetry schema or
  mandatory real-path/no-COW integration evidence.
- Package-backed execution remains unavailable in the reported local
  environment because dependencies including `orjson`/`torch` are absent.
- Scheduler serialization, post-fix runtime value, performance, and fairness
  remain unproven.
- Any extra design, implementation, test, review, deployment, or runtime work
  requires a fresh Task ID.
