ENTRY: ACCEPT

status: done
task_id: T3060-RH-MATCH-PREP-VERIFY-R2-20260909
orchestration_epoch: 20260909-rh-ab51
role: tester
repository: /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt
branch: 3060-12g-qwen35-4b
revision: c4ad01ef5d7578bb542fe3e514a71cdbccb6c07a
code_gate: BLOCK
runtime: BLOCKED_SEPARATE

## Artifacts

- This independent verification report.
- No product, test, gate, commit, deployment, or remote-host files were
  modified by this invocation.
- The target worktree had pre-existing untracked `.memory/`, `review/gates/`,
  and `storage/` artifacts; they were preserved.

## Evidence

### Immutable revision and scope

- `git rev-parse HEAD` matched
  `c4ad01ef5d7578bb542fe3e514a71cdbccb6c07a` on the requested branch.
- The commit is a direct child of
  `f629d4e2c19eb74571b4154438fd651ce24ff53b`.
- The commit changes exactly five files: `scheduler.py`,
  `unified_radix_cache.py`, `test_rh_contract_dependency_free.py`,
  `test_prefetch_gate_skip_regression.py`, and `test_ready_horizon_unit.py`.
- `git diff --check c4ad01ef^ c4ad01ef` passed.
- `python3 -m py_compile` and `python3 -m compileall -q` passed for both
  changed product files and the three changed focused tests, using a temporary
  bytecode prefix outside the repository.

### Focused contract suites

- `PYTHONDONTWRITEBYTECODE=1 python3 3090-dev/test_rh_contract_dependency_free.py -v`
  passed **15/15**.
- `PYTHONDONTWRITEBYTECODE=1 python3 3090-dev/test_prefetch_gate_skip_regression.py -v`
  passed **2/2**.
- `PYTHONDONTWRITEBYTECODE=1 python3 3090-dev/test_hicache_restore.py -v`
  passed **92/92**. This is the dependency-free restore state-machine suite,
  not package-backed scheduler execution.

The 15-test suite independently passed the committed valid-ticket,
invalidation/fallback, deleted/unknown-anchor fail-closed, no-COW counter,
lifecycle exclusion, claim fencing, telemetry-field presence, L3-only parity,
and discarded-finalization oracles.

### Real committed scheduler method-path harness

An additional no-package harness executed the committed method bodies through
`_ready_horizon_pass` -> `_prefetch_kvcache` -> `_prefetch_kvcache_impl`, with
synthetic request/cache collaborators. Preparation and issue were not replaced
with stubs; the collaborators were bounded test doubles because the package
environment is unavailable.

- Valid ticket: one `init_next_round_input(..., cow_mamba=False)` call, one
  active claim (`rh-real:prefetch:1`), one storage query, RESTORING result, and
  no issue-time rematch. Mamba fields and allocation/eviction counters were
  unchanged.
- Invalidation between policy preparation and consumption: two calls, both
  with `cow_mamba=False`; one `result=invalidated` event, one
  `reason=fallback_rematch` event, one storage query after fallback, and one
  active attempt. No stale-anchor query occurred; Mamba fields and counters
  were unchanged.
- The harness emitted joinable `decision_id=rh-real:rh:1` and the same ID in
  `rh_stage.v2`; the issue attempt ID was present in stage telemetry.
- The first harness run stopped because its fake cache controller omitted the
  two rate-limit methods. That was a harness defect, corrected before the
  reported run; the corrected run passed.

### L3 predicate parity

The committed `has_restore_potential` and `prefetch_gate_ok` methods were
executed for backuped, root, L3-durable-only, extant non-durable, and missing
anchors. All five cases agreed: true for the first three and false for the
last two.

### Static RH-OFF/admission checks

- Source inspection shows RH-OFF calls `EAGER_RH_OFF` before
  `waiting_queue.append(req)` at `scheduler.py:5527-5530`.
- RH-ON has no eager call in that branch; `_ready_horizon_pass` calls the
  issue path with `READY_HORIZON` at `scheduler.py:4777-4780`.
- The normal admission path still calls
  `req.init_next_round_input(self.tree_cache)` without an RH ticket at
  `scheduler.py:6243`.
- These ordering/separation checks are static only because package-backed
  scheduler collection is blocked below.

### Telemetry schema finding

The architecture gate requires every nullable field to be serialized as the
literal `null` (`ARCH-20260909-RH-MATCH-PREP.md:82-105`). The emitter defines
the null-normalizing `field` helper at `scheduler.py:4419`, and uses it for
`enqueue_seq`, `decision_id`, `attempt_id`, `anchor_id`, and
`match_duration_us`, but passes `session_generation` directly at
`scheduler.py:4462`.

Independent reproduction with `req.session_generation = None` produced:

```text
evt=rh_match_prepare schema=rh_match_prepare.v1 ... attempt_id=null session_generation=None ... match_duration_us=null ...
```

This violates the exact gate schema, which requires `session_generation=null`
for the nullable case. It is a product code-gate finding, not a test or
infrastructure failure. The implementation owner must correct the emitter and
rerun the focused and package-backed verification under a fresh Task ID.

### Package-backed and runtime attempts

The following immutable-commit attempts were blocked during package import:

- `PYTHONPATH=python python3 3090-dev/test_ready_horizon_unit.py -v`
- `PYTHONPATH=python python3 3090-dev/test_ready_horizon_partition.py -v`
- `PYTHONPATH=python python3 3090-dev/test_hicache_restore_scheduler_feed.py -v`

All stopped at `ModuleNotFoundError: No module named 'orjson'`. Environment
inspection also found `msgspec`, `torch`, and `pytest` unavailable. No package
was installed. No live runtime, deployment, remote load, or performance test
was run.

## Summary

The immutable commit passes the requested 15-test dependency-free RH contract
suite, both gate-skip tests, the pure 92-test restore suite, compile checks,
diff checks, L3 parity, and bounded real-method valid/fallback/no-COW evidence.
The code gate is **BLOCKED** by the exact telemetry-schema defect where a
nullable `session_generation` is emitted as `None` instead of `null`.

Runtime acceptance remains separate and **BLOCKED/UNCOMPUTED**: package-backed
Ready Horizon and scheduler-feed tests cannot collect without `orjson` (with
additional missing `msgspec`, `torch`, and `pytest`), and no live runtime was
authorized.

## Followups

- Fresh implementation Task ID: normalize `session_generation` through the
  emitter's existing `field(...)` helper, then rerun this verification.
- Fresh tester Task ID: provide the required package environment and execute
  the real package-backed valid-ticket, fallback, fail-closed, admission,
  lifecycle, RH-OFF, and telemetry-independence oracles.
- Fresh gate-owner/orchestrator Task ID: revision-pin the implementation in
  the revised Pattern/NM chain and resolve its currently pending
  orchestrator-acceptance fields.

## Open issues

- Product defect: `scheduler.py:4462` serializes nullable
  `session_generation` as `None`, violating the exact `rh_match_prepare.v1`
  contract.
- Infrastructure/evidence gap: `orjson` blocks package-backed scheduler
  collection; `msgspec`, `torch`, and `pytest` are also unavailable.
- Missing runtime/performance evidence is intentionally separate from the
  code-gate verdict; no remote load or deployment was attempted.
- Revised Pattern Intake and Novel Mechanism artifacts are architect-accepted
  design inputs but still show `orchestrator_acceptance: PENDING` and
  `implementation_revision: null`; terminal gate-chain acceptance is not
  established by this tester report.
