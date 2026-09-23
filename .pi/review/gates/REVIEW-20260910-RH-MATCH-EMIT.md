# Independent implementation review — RH match telemetry emission hardening

```yaml
status: done
entry: ACCEPT
task_id: R3060-RH-MATCH-EMIT-20260910
invocation_id: 20260910T-FRESH-REVIEW-COMPLIANT-01
orchestration_epoch: E3060-RH-MATCH-EMIT-20260910
role: reviewer
capability_level: L3
branch: 3060-12g-qwen35-4b
repository: /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt
observed_root: /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt
reviewed_revision: 03a170ef4f35fe1d87d80a7b6f09e83261aef94e
parent_revision: 9213ee01d90ba3925e7fe928e80cc41354ee4fff
verdict: PASS
code_gate: PASS
deployment_acceptance: UNPROVEN
runtime_rh_value: UNPROVEN
```

## Scope and decision

The reviewed commit is accepted for the narrow implementation/code gate. It
hardens the observational `rh_match_prepare.v1` logger call against nullable
values without changing RH policy, match, issue, admission, allocator,
Mamba, storage, HOST_ALLOC, or RH-OFF behavior. This PASS is not a live
deployment, performance, or runtime RH-value acceptance.

## Independent evidence

- Startup checks observed `pwd` and Git root as
  `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt`.
- `git rev-parse HEAD` resolved to
  `03a170ef4f35fe1d87d80a7b6f09e83261aef94e`; its direct parent is
  `9213ee01d90ba3925e7fe928e80cc41354ee4fff`.
- The parent-to-reviewed-commit diff changes exactly:
  `python/sglang/srt/managers/scheduler.py` and
  `test/registered/unit/mem_cache/test_rh_contract_dependency_free.py`.
- The product diff is confined to `Scheduler._emit_rh_match_prepare` at
  `python/sglang/srt/managers/scheduler.py:4443-4467`. The event field set and
  order remain unchanged from the parent: timestamp, identity/join fields,
  result/reason, fill/hit fields, anchor/gate fields, `cow_mamba=false`,
  duration/match-count/fallback fields, and all five Mamba delta fields.
- The existing `field(...)` normalization still emits literal `null` for
  nullable enqueue, attempt, session, anchor, and duration values. The new
  eager construction means the logger receives one fully rendered string, so
  `%d` interpolation cannot reject `None` inside logging. Missing or `None`
  `retraction_count` is rendered as the contract's numeric default `0`.
- No control-flow call, request mutation, cache call, issue call, admission
  call, allocator/eviction call, or RH-OFF path is changed by the product
  diff. The added test only exercises the emitter through the dependency-free
  extracted method harness.
- `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest
  test/registered/unit/mem_cache/test_rh_contract_dependency_free.py
  test/registered/unit/mem_cache/test_prefetch_gate_skip_regression.py`: **19/19 passed**.
- `PYTHONDONTWRITEBYTECODE=1 python3 -m py_compile
  python/sglang/srt/managers/scheduler.py
  test/registered/unit/mem_cache/test_rh_contract_dependency_free.py`: **passed**.
- `git diff 03a170ef4f35fe1d87d80a7b6f09e83261aef94e^ 03a170ef4f35fe1d87d80a7b6f09e83261aef94e --check`: **passed**.
- The coder evidence report and prior R2 gate were read. The prior gate's
  six broad-suite residual categories remain outside this two-file telemetry
  descendant and are not silently reclassified as green.

## Findings

### Blocking findings

None. No correctness, security, compatibility, scope, or regression finding
attributable to commit `03a170ef4f35fe1d87d80a7b6f09e83261aef94e` blocks the
narrow code gate.

### Non-blocking findings and acceptance impact

1. **P2 — Broad-suite/runtime evidence remains incomplete.** The prior R2
   gate records six fixture/API/expectation mismatch categories in broader
   Ready Horizon/restore suites, and the supplied evidence does not establish
   live RH value, load, or deployment behavior. This does not block this exact
   telemetry-only code gate because the focused nullable-emission regression
   and neighboring contract tests pass; it blocks any claim that the broad
   suites are fully green or that runtime RH deployment value is proven.
   Location/evidence: prior gate
   `review/gates/REVIEW-20260909-RH-MATCH-FINAL-R2.md`, residual
   classification and runtime limitations.

2. **P2 — Design-chain revision is older than the reviewed descendant.** The
   ARCH/NM/Pattern Intake chain and prior final gate identify
   `9213ee01d90ba3925e7fe928e80cc41354ee4fff`, while this review accepts its
   telemetry-only descendant `03a170ef...`. The diff is within the already
   accepted telemetry symbol and does not introduce a new authority boundary,
   but the orchestrator should repin or explicitly record descendant coverage
   before claiming terminal gate-chain acceptance.
   Location/evidence: prior gate YAML revision fields versus the reviewed
   commit manifest.

3. **P3 — Eager message construction has a small potential logging-overhead
   cost.** At `scheduler.py:4443-4467`, the full f-string is built before the
   logger can filter by level. The parent already evaluated all field
   expressions, so this is a bounded telemetry/performance consideration, not
   a semantic regression. If high-frequency INFO-disabled performance is a
   release criterion, measure it or add a fresh optimization task; no such
   performance acceptance is claimed here.

## Summary

**PASS for the implementation/code gate at
`03a170ef4f35fe1d87d80a7b6f09e83261aef94e`.** The change preserves the
`rh_match_prepare.v1` schema and joins, makes nullable telemetry robust, and
keeps telemetry failure observational. Deployment/runtime acceptance remains
unproven.

## Followups

- Fresh test/runtime task: reconcile the six broad-suite residual categories
  and run hash-pinned RH-OFF/RH-ON runtime evidence if deployment acceptance is
  required.
- Orchestrator/gate-owner task: repin or explicitly cover this telemetry-only
  descendant in the design-chain acceptance records.
- Any implementation, test, performance, deployment, or runtime expansion
  requires a fresh Task ID.

## Open issues

- Broad Ready Horizon/restore suites are not claimed fully green.
- Runtime RH value, live paired replay, load, deployment, and performance are
  unproven.
- Formatter/type-check tools unavailable in the supplied workspace were not
  claimed as passing.
