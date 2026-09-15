# Independent review — RH current-match preparation R2

```yaml
status: done
task_id: T3060-RH-MATCH-PREP-REVIEW-R2-20260909
orchestration_epoch: 20260909-rh-ab51
role: reviewer
source_repository: /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt
requested_candidate_repository: /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache
branch: 3060-12g-qwen35-4b
reviewed_revision: c4ad01ef5d7578bb542fe3e514a71cdbccb6c07a
base_revision: f629d4e2c19eb74571b4154438fd651ce24ff53b
verdict: BLOCK
code_gate: BLOCK
runtime_rh_value: UNPROVEN
```

## Artifacts

- Accepted architecture: `review/gates/ARCH-20260909-RH-MATCH-PREP.md`.
- Revised Pattern Intake: `storage/review/gates/pattern-intake/PATTERN-INTAKE-20260909-RH-MATCH-PREP.md`.
- Novel Mechanism R2: `review/gates/NOVEL-MECHANISM-20260909-RH-MATCH-PREP-R2.md`.
- Coder close report: `.memory/phase2-hicache-design/work/CODER3060-RH-MATCH-PREP-CLOSE-20260909.md`.
- Earlier tester report: `.memory/phase2-hicache-design/work/TEST3060-RH-MATCH-PREP-VERIFY-20260909.md`; no R2 tester report tied to `c4ad01e…` was available.
- This independent gate artifact.

## Evidence

- `git show c4ad01ef5d7578bb542fe3e514a71cdbccb6c07` verifies parent `f629d4e2c19eb74571b4154438fd651ce24ff53b` and exactly five changed tracked files: the two authorized product files and three focused tests.
- Independently ran at the immutable commit in the `sglang-3090-24g-opt` worktree with `PYTHONDONTWRITEBYTECODE=1`:
  - `python3 3090-dev/test_rh_contract_dependency_free.py`: **15/15 passed**.
  - `python3 3090-dev/test_prefetch_gate_skip_regression.py`: **2/2 passed**.
  - `git diff --check c4ad01e^ c4ad01e`: passed.
- Package-backed `PYTHONPATH=python python3 3090-dev/test_ready_horizon_unit.py` cannot collect: `ModuleNotFoundError: No module named 'orjson'`; the environment also has no `torch`. No live load, deployment, or remote load was run.
- Source inspection confirms the intended structural boundaries: preparation is after `should_refill` and before view construction (`scheduler.py:4658-4684`); the issue wrapper claims before consuming the ticket (`scheduler.py:3125-3148`); preparation and fallback call `init_next_round_input(..., cow_mamba=False)` (`scheduler.py:3230-3232`, `4522-4527`); RH-OFF keeps eager issue before queue append (`scheduler.py:5527-5531`); and L3 parity matches `prefetch_gate_ok` (`unified_radix_cache.py:4944-4955`, `6061-6100`).

## Findings

### BLOCKER-1 — `rh_match_prepare.v1` decision join is stale on later passes, and nullable `session_generation` is not emitted as `null`

Locations: committed `python/sglang/srt/managers/scheduler.py:4192-4195,4438-4463`.

`_emit_rh_match_prepare` reads `req.hicache_last_rh_decision_id` before the current pass emits its RH decision, and only synthesizes an ID when that field is absent. `_emit_rh_decision` assigns the current `rid:rh:<pass_seq>` afterward. Therefore, after the first pass, a later preparation event can carry the previous pass’s decision ID while the downstream `rh_preadmission.v1` event carries the current pass’s ID. This violates the required same-value `decision_id` join. In addition, `session_generation` is passed directly to `%s`; a missing value is logged as `None`, not the contract’s explicit `null`.

Acceptance impact: the required preparation → preadmission → stage telemetry join is not reliable, and the exact schema contract is not met. This blocks code-gate acceptance even though the matching control path is directionally correct.

### BLOCKER-2 — Mandatory real valid-ticket, fallback, no-COW, lifecycle, and admission oracles are not present or runnable

Locations: architecture gate `ARCH-20260909-RH-MATCH-PREP.md:122-159`; committed tests `3090-dev/test_rh_contract_dependency_free.py:65-87,196-290,319-391`; `3090-dev/test_ready_horizon_unit.py:866-924`.

The dependency-free tests execute AST-extracted methods against `SimpleNamespace` request/cache fakes. The test named `test_real_impl_consumes_valid_ticket_without_issue_rematch` does not execute the real Scheduler/cache components, claim wrapper, or real `match_prefix`; the unit harness replaces `_prefetch_kvcache` with a local `_issue` stub. Consequently there is no accepted evidence for the architecture-mandated real path through `_ready_horizon_pass` → `_prefetch_kvcache` → `_prefetch_kvcache_impl`, one real match/claim/query/attempt, real allocator and Mamba counters, real admission-time COW separation, or the complete lifecycle matrix.

The required package-backed suite could not collect because `orjson` is unavailable, and no R2 tester report supplies replacement evidence. AST/fake tests are explicitly supplementary under the architecture gate and cannot replace these oracles.

Acceptance impact: valid-ticket suppression, exactly-one fallback, fail-closed behavior, Mamba/HOST_ALLOC authority, and admission separation remain unaccepted at the implementation gate. The 15+2 passing tests are useful focused evidence but cannot support PASS.

## Requirement matrix

| Requirement | Independent result |
| --- | --- |
| Exact SHA and five-file scope | PASS; reviewed `c4ad01e…`, exact parent and changed-file set verified. |
| Current-match preparation and fallback source shape | Directionally PASS by source inspection; real integration acceptance is blocked by BLOCKER-2. |
| L3 durable parity | PASS structurally and in the focused positive/negative source-extracted test; real parity matrix remains unproven. |
| Complete `rh_match_prepare.v1` telemetry | BLOCK; BLOCKER-1 breaks decision joins and nullable-field encoding. |
| Valid-ticket/no-COW integration oracles | BLOCK; BLOCKER-2. |
| RH-OFF eager-before-append ordering | PASS structurally and by focused unit test; package-backed independence remains unverified. |
| Mamba/HOST_ALLOC authority | No changed call grants those owners to RH; real no-COW/allocator evidence is absent. |
| Tests | 15+2 dependency-free tests pass; mandatory package-backed/integration evidence is absent. |
| Runtime RH value/performance | UNPROVEN; no post-fix paired RH-OFF/RH-ON live replay was run. |

## Summary

The immutable commit has the intended narrow product scope and directionally
preserves current-match placement, one non-COW preparation, L3 eligibility
parity, RH-OFF ordering, and existing allocator/HOST_ALLOC ownership. It is
not acceptable for merge under the stated gate: the telemetry contract has a
real cross-pass decision-ID join defect and invalid nullable encoding, and the
mandatory real-component integration/no-COW oracles are neither supplied nor
runnable in the available environment.

Code acceptance is separate from runtime value: this review makes no claim
that RH improves runtime behavior. Runtime RH value remains unproven pending a
fresh hash-pinned paired replay with complete joins.

## Followups

- Fresh implementation task: make preparation telemetry derive the current-pass downstream decision ID and encode nullable fields explicitly as `null`; add a telemetry join regression.
- Fresh tester task: run the architecture-mandated real valid-ticket, invalidation/fallback, fail-closed, no-COW, admission-separation, lifecycle, L3 parity, and RH-OFF/telemetry-independence oracles with package dependencies available.
- Fresh orchestrator/gate task: repin the architecture/intake/novel chain’s `implementation_revision` to `c4ad01e…` and record final orchestrator acceptance before terminal acceptance.
- Fresh runtime task, only after code-gate PASS: run the hash-pinned paired RH-OFF/RH-ON replay; report missing joins as not computable and do not infer RH value from HTTP completion.

## Open issues

- The requested candidate directory `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache` is currently checked out at `0a725c6…` on `3090-24g-hicache`; the reviewed SHA and branch are present in the sibling `sglang-3090-24g-opt` worktree. No checkout or product mutation was performed.
- The architecture, Pattern Intake, and Novel Mechanism artifacts still record `implementation_revision: null` and orchestrator acceptance pending; this review records the exact descendant SHA but does not substitute for that control-plane repin.
- No R2 tester report tied to `c4ad01e…` was available.
- Missing `orjson` and `torch` prevent package-backed test collection; no formatter/type-checker or runtime value claim is made.
- Extra implementation, gate, test, deployment, or runtime work requires a fresh Task ID.
