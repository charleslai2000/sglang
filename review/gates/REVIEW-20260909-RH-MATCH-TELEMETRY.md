# Independent review — RH match telemetry join fix

```yaml
status: done
task_id: T3060-RH-MATCH-TELEMETRY-REVIEW-20260909
orchestration_epoch: 20260909-rh-ab53
role: reviewer
repository: /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt
branch: 3060-12g-qwen35-4b
reviewed_revision: 9213ee01d90ba3925e7fe928e80cc41354ee4fff
parent_revision: c4ad01ef5d7578bb542fe3e514a71cdbccb6c07
verdict: PASS
code_gate: PASS
runtime_rh_value: UNPROVEN
```

## Artifacts

- Reviewed immutable commit `9213ee01d9` and its direct parent
  `c4ad01ef5d`.
- Accepted design evidence: `review/gates/ARCH-20260909-RH-MATCH-PREP.md`,
  `review/gates/NOVEL-MECHANISM-20260909-RH-MATCH-PREP-R2.md`, and the
  revised Pattern Intake in the sibling gate workspace. No current-SHA
  re-pinned design artifacts were available; this report does not substitute
  for that control-plane repin.
- Coder report:
  `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/CODER3060-RH-MATCH-TELEMETRY-FIX-20260909.md`.
- Tester report:
  `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/TEST3060-RH-MATCH-PREP-VERIFY-R2-20260909.md`.
- Prior independent review:
  `review/gates/REVIEW-20260909-RH-MATCH-PREP-R2.md`.
- This independent review artifact only; no product, test, deployment, or
  remote-load files were modified.

## Evidence

### Revision and exact scope

- `git rev-list --parents -n 1 9213ee01d9` confirms the direct parent is
  `c4ad01ef5d7578bb542fe3e514a71cdbccb6c07`.
- The commit changes exactly two authorized files:
  `python/sglang/srt/managers/scheduler.py` and
  `3090-dev/test_rh_contract_dependency_free.py`.
- The product diff is limited to `_emit_rh_match_prepare`; it changes no
  cache, allocator, admission, HOST_ALLOC, Mamba, persistence, or runtime
  code. `git diff --check` passes.

### Telemetry join and null encoding

- `_emit_rh_decision` assigns the current `rid:rh:<pass_seq>` at
  `scheduler.py:4192-4195`.
- `_emit_rh_match_prepare` now derives the same current-pass ID directly at
  `scheduler.py:4440`, so it cannot reuse the prior request-cached ID.
- The emitter uses the existing `field(...)` null-normalization helper for
  `session_generation` at `scheduler.py:4419,4460`. The nullable case is
  therefore serialized as literal `session_generation=null`.
- The new regression at
  `3090-dev/test_rh_contract_dependency_free.py:370-427` sets a stale
  `r1:rh:1`, exercises pass 2, and independently asserts that both preparation
  and preadmission records use `r1:rh:2`, omit the stale ID, and encode the
  absent session generation as `null`.
- Source inspection confirms the complete existing preparation schema remains
  emitted: stable identity/join fields, result/reason, anchor classification,
  gate status, duration, match count/fallback, and all three Mamba deltas plus
  allocation/eviction deltas. The focused required-field test passes.

### One-shot, fallback, no-COW, and boundary evidence

- The current 16-test dependency-free contract suite passes the valid-ticket
  no-rematch, exactly-one invalidation fallback, deleted/unknown-anchor
  fail-closed, one-shot non-COW preparation, lifecycle, required telemetry,
  and L3 parity cases.
- The prior tester report supplies bounded method-path evidence through the
  committed preparation/issue implementation for valid-ticket, fallback, and
  no-COW field/counter behavior. This descendant does not touch those paths;
  the current diff only repairs telemetry joining and adds its regression.
- Source inspection confirms RH-OFF still issues eagerly before queue append,
  RH-ON remains queue-first, and the reviewed diff grants no RH authority over
  HOST_ALLOC generation/FIFO, allocation/eviction, or Mamba COW.
- Admission retains its separate normal match/COW path. The current telemetry
  change does not suppress or alter it.

### Independent execution

- `PYTHONDONTWRITEBYTECODE=1 python3 3090-dev/test_rh_contract_dependency_free.py -v`:
  **16/16 passed**.
- `PYTHONDONTWRITEBYTECODE=1 python3 3090-dev/test_prefetch_gate_skip_regression.py -v`:
  **2/2 passed**.
- `PYTHONDONTWRITEBYTECODE=1 python3 3090-dev/test_hicache_restore.py -v`:
  **92/92 passed**.
- `PYTHONDONTWRITEBYTECODE=1 python3 -m py_compile` over the changed product
  and focused test files: **PASS**.
- `git diff --check 9213ee01d9^ 9213ee01d9`: **PASS**.
- Package-backed Ready Horizon, partition, and scheduler-feed tests remain
  unavailable in this environment: all stop at
  `ModuleNotFoundError: No module named 'orjson'`. No dependency was
  installed, and no deployment or remote load was attempted.

## Findings

No blocking correctness, security, compatibility, regression, or scope
finding remains in the reviewed telemetry fix. The prior R2 blockers for the
stale cross-pass `decision_id` and non-contract `session_generation=None` are
closed by the committed change and its regression.

## Summary

**PASS for code acceptance at `9213ee01d9`.** The exact two-file descendant
repairs current-pass preparation-to-preadmission decision joins and explicit
nullable session encoding without changing RH matching, issue, admission,
allocator, Mamba, HOST_ALLOC, or RH-OFF behavior. Independent focused,
restore-state, compile, and diff checks pass.

Runtime RH value is **UNPROVEN**. No live RH-OFF/RH-ON replay, deployment, or
performance claim was made, and package-backed scheduler collection is blocked
by the missing environment dependency.

## Followups

- Fresh gate-owner/orchestrator task: repin the ARCH/Pattern/NM chain to the
  full implementation SHA and record final control-plane acceptance if
  terminal gate-chain acceptance is required.
- Fresh tester/runtime task: run package-backed scheduler/Ready Horizon
  coverage and a hash-pinned paired RH-OFF/RH-ON replay when the approved
  dependencies and runtime environment are available.

## Open issues

- Current-SHA ARCH/Pattern/NM repin and orchestrator acceptance are not
  present in the reviewed workspace; this review does not claim them.
- Package-backed scheduler evidence is not computable because `orjson` is
  unavailable; runtime RH value, performance, and live telemetry coverage
  remain unproven.
- Extra implementation, gate, test, deployment, or runtime work requires a
  fresh Task ID.
