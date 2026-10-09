ENTRY: ACCEPT

status: done
task_id: TEST3060-RH-VIEW-TYPE-20260909
orchestration_epoch: 20260909-rh-ab38
role: tester
repository: /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt
branch: 3060-12g-qwen35-4b
revision: f629d4e2c19eb74571b4154438fd651ce24ff53b
verdict: ACCEPT

## Artifacts

- This independent verification report.
- Verified target commit `f629d4e2c1`, `fix(hicache): join RH frontier requests to policy views`.
- Input crash report: `OPS3060-RH-FINAL-ON-RESTART.md`.
- Coder report: `CODE3060-RH-VIEW-TYPE-20260909.md`.
- Accepted review evidence: `REVIEW3060-RH-FINAL-JOIN-20260909.md` and
  `review/gates/REVIEW-20260909-RH-PREADMISSION.md`.
- No product source, gate, remote, or protected-storage resource was modified.

## Evidence

### Target and scope

- `git rev-parse HEAD` is
  `f629d4e2c19eb74571b4154438fd651ce24ff53b` on the requested branch.
- The target is a direct descendant of accepted review revision
  `6edf69ce29fe2598fba51c94a99315239cf1a8c8` and accepted architecture/intake
  pin `67b39b5aca6aaacbf410d21efda9b7059eaa8d2c`.
- `git diff --name-status f629d4e2c1^ f629d4e2c1` contains exactly:
  `python/sglang/srt/managers/scheduler.py` and
  `3090-dev/test_rh_contract_dependency_free.py`.
- `git diff --check f629d4e2c1^ f629d4e2c1` passed. The two target files have
  no uncommitted tracked changes; unrelated pre-existing untracked memory,
  gate, and storage artifacts were preserved.

### Crash-fix regression

- `env PYTHONDONTWRITEBYTECODE=1 python3 -m unittest
  3090-dev/test_rh_contract_dependency_free.py -v` passed **6/6**.
- The new `test_ready_pass_joins_raw_frontier_req_to_policy_view` executes the
  extracted real `_ready_horizon_pass` with a raw `Req` exposing only `rid` and
  a separate policy view exposing `staging_eligible`/`state`. It passed with
  the expected `exclude/no_restore_potential`, rank `1`, frontier size `1`,
  and the exact policy-view identity. No `AttributeError` occurred.
- Independent AST/source check confirms the mapping is at scheduler lines
  4192-4194: `frontier_views = {view.rid: view for view in views}`, iteration
  over raw `req`, then `view = frontier_views[req.rid]` before policy fields
  are read. This directly covers the observed startup failure
  `AttributeError: 'Req' object has no attribute 'staging_eligible'`.
- The same six-test run passed the existing claim fencing, event-field/order,
  finalizer auxiliary completion, and discarded-finalization-no-ready-host
  checks.

### Contract and regression checks

- `env PYTHONDONTWRITEBYTECODE=1 python3 -m unittest
  3090-dev/test_prefetch_gate_skip_regression.py -v` passed **2/2**.
- `env PYTHONDONTWRITEBYTECODE=1 python3 3090-dev/test_hicache_restore.py`
  passed **92/92**.
- Focused storage regressions passed: `RestoreDurabilityMarkingTests` **4/4**
  and `FrontierWaiterRegistryTests.test_release_aborted_request_cleans_waiter_and_terminal`
  **1/1**.
- AST parse and in-memory `compile()` passed for both changed Python files.
- Static RH-OFF check confirms `EAGER_RH_OFF` remains before
  `waiting_queue.append(req)` at scheduler lines 4995 and 4998, inside the
  `not self.enable_ready_horizon` branch.
- The commit diff changes no claim lifecycle, telemetry emitter, prefetch
  implementation, hybrid finalizer, allocator, Mamba, or HOST_ALLOC code.

### Package-backed attempts and limits

- `PYTHONPATH=python` attempts for `test_hicache_restore_scheduler_feed.py`,
  `test_ready_horizon_unit.py`, and `test_ready_horizon_partition.py` stop at
  package import with `ModuleNotFoundError: No module named 'orjson'`.
- `test_prefetch_budget_split_unit.py` was attempted without installing
  packages: 24 tests ran, 11 passed, 12 errored, and 1 skipped. The errors are
  existing harness/environment failures (`_t38c_request_contexts` absent and
  scheduler import unavailable in the fixture), outside this two-file commit.
- The full storage regression attempt ran 126 tests with 21 skips and 5
  fixture errors on missing `_host_allocability_telemetry_seq`/`components`;
  the focused durability and waiter tests above passed. These failures are in
  pre-existing test doubles and unrelated to the target diff.
- `pytest`, formatter/typechecker tools, and package installation were not
  used; no dependency was installed. No remote restart or live RH-ON replay
  was attempted because that is outside this invocation's authorized scope.

## Summary

ACCEPT. The final descendant fixes the RH-ON startup crash by joining raw
frontier requests to their `ReadyHorizonView` policy objects before reading
policy-only fields. The exact new regression passes, and focused accepted RH
contract, prefetch gate-skip, restore, claim, telemetry, hybrid, and RH-OFF
ordering checks pass. The narrow diff introduces no observed regression to the
accepted RH contract.

## Followups

- Fresh Task ID: rerun the package-backed scheduler/Ready Horizon suites when
  `orjson` and the required test environment are available.
- Fresh Task ID: perform final revision/hash-pinned RH-ON startup and bounded
  RH-OFF/RH-ON runtime/performance verification if live evidence is required.

## Open issues

- Final live RH-ON startup evidence was not collected in this read-only local
  verification; the dependency-free harness covers the reported failing code
  path.
- Package-backed tests remain uncomputable in this environment because
  `orjson` is missing; no package installation was authorized.
- Broader prefetch-budget and storage-suite fixture errors remain separate
  test/infrastructure evidence gaps, not findings against `f629d4e2c1`.
