ENTRY: ACCEPT

status: done
task_id: T3060-RH-MATCH-GATE-INTAKE-20260909
orchestration_epoch: 20260909-rh-ab46
role: architect

# ARCH3060 RH current-match gate intake report

## Artifacts

- `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/storage/review/gates/pattern-intake/PATTERN-INTAKE-20260909-RH-MATCH-PREP.md`
  - SHA-256: `47bbf94a8eeaa8f06844af1fdb0d27e2f919e8c46d491942b74327111f7bcc2f`
- `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/review/gates/NOVEL-MECHANISM-20260909-RH-MATCH-PREP.md`
  - SHA-256: `761951907e3aacd784e71901b2ed60d2a958a30edde8c4ad556c51f1dbf534e7`
- This report:
  `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/ARCH3060-RH-MATCH-GATE-INTAKE-20260909.md`

No product source was modified.

## Evidence

Observed inputs:

- `ARCH3060-RH-MATCH-GATE-DESIGN-20260909.md` supplied the narrow proposed
  scheduler-local contract and twelve atomic `RH-MG-I*` invariants.
- The accepted prior RH Pattern Intake, Novel Mechanism, and Architecture gate
  in `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt` establish the
  exclusive RH-ON initial-issue and RH-OFF eager-order baseline at
  `f629d4e2c19eb74571b4154438fd651ce24ff53b`.
- `DBG-20260909-RH-NO-STAGING.md`,
  `TEST3060-RH-FINAL-ON-TRACE-20260909.md`, and
  `TEST3060-RH-FINAL-OFF-TRACE-20260909.md` establish the causal/runtime
  evidence and its limits: final RH-ON requests all excluded as
  `no_restore_potential`; OFF had recoverable 54,976-token KV+Mamba material;
  neither result proves post-fix physical capacity or performance.
- Exact-revision source reads at `f629d4e2c1` confirmed the ordering and
  interfaces of `Scheduler._ready_horizon_pass`, `_ready_horizon_views`,
  `_restore_potential_for`, `_prefetch_kvcache_impl`,
  `_get_new_batch_prefill_raw`, `Req.init_next_round_input`,
  `Req.reset_for_retract`, Unified match/post-processing,
  `node_exists`/`prefetch_gate_ok`, Mamba non-COW finalization, and
  flush-before-evict.
- Exact-revision test search confirmed the existing RH policy, partition,
  exclusive-owner, active-claim, raw-request/view join, restore-budget,
  host-allocability, hybrid-finalization, and storage-regression harnesses.

Validation evidence:

- Pattern Intake contains the searched source revision/scope, inherited corpus
  pin, gate evidence, all relevant stable/anti/bug-derived/harness/test/
  benchmark/deferred/missing IDs, explicit dispositions, and atomic
  `RH-MG-MAP-001..012` bindings to `MG-T1..MG-T17`.
- Novel declaration records why the known patterns do not fully fit, the new
  capability/freshness boundary, owners and interfaces, twelve atomic
  invariants, failure containment, observable oracles, rejected/deferred
  alternatives, risks, and migration/rollback/removal.
- Both artifacts set `gate_verdict: PENDING`,
  `implementation_revision: null`, and
  `implementation_status: NOT_YET_ACCEPTED`. The design input is pinned to the
  full `f629d4e2c1` SHA.
- `git status --short -- ... python 3090-dev test` showed only the two new gate
  documents in their authorized paths plus pre-existing unrelated untracked
  `3090-dev` files; no tracked or untracked product-source change was created
  by this task.

## Summary

The revised intake and Novel Mechanism declaration are complete as proposed
gate inputs. They recommend one causally gated non-COW current match per
potentially stageable candidate, represented by an ephemeral scheduler-local
proof that can be consumed only by the immediate RH issue after full identity,
anchor-existence, and storage-gate validation. Invalidation permits one
fallback rematch. The proposal preserves exclusive initial-issue ownership,
RH-OFF order, admission-time Mamba COW, allocator/HOST_ALLOC authority, hybrid
finalization, and flush-before-evict.

These are evidence-backed architect recommendations for orchestrator and
existing gate-owner acceptance. They are not self-approving authority, and no
implementation has been accepted.

## Followups

- Orchestrator and existing G-ARCH/G-SYSTEM/G-TECH/G-ALGO owners: accept,
  amend, or reject the two proposed gate inputs and repin the architecture
  chain before any implementation dispatch.
- Fresh coder Task ID after gate acceptance: implement only the authorized
  scheduler-local shape and provide a descendant revision/change manifest.
- Fresh tester and reviewer Task IDs: bind `MG-T1..MG-T17`, exact-revision
  evidence, and independent acceptance.
- Fresh deployment/runtime Task IDs only after implementation review.

## Open issues

- Scheduler-owner serialization between preparation and immediate issue must
  be proved in implementation review; otherwise an atomic/cache-generation
  redesign requires a fresh architecture task.
- No post-fix implementation, deterministic test evidence, independent review,
  or hash-pinned live ON/OFF evidence exists.
- Package-backed RH tests previously lacked `orjson`; dependency completeness
  remains unverified.
- Match overhead, fairness, deployment, performance, and terminal acceptance
  remain open and are outside this invocation.

```text
status: done
artifacts: PATTERN-INTAKE-20260909-RH-MATCH-PREP.md; NOVEL-MECHANISM-20260909-RH-MATCH-PREP.md; ARCH3060-RH-MATCH-GATE-INTAKE-20260909.md
evidence: exact f629 source/test corpus; accepted prior RH gates; debugger report; final f629 RH-ON/RH-OFF reports; artifact hashes and scope audit
summary: complete proposed Pattern Intake and Novel Mechanism declaration for the one-shot RH current-match preparation boundary; implementation remains not accepted
followups: orchestrator/gate-owner decision; fresh implementation, test, review, and runtime Task IDs
open_issues: scheduler serialization proof; no post-fix implementation/tests/review/live evidence; package dependency availability; performance/fairness remain unproven
```
