ENTRY: ACCEPT

status: done
task_id: CODE3060-RH-ISSUE-TELEMETRY-JOIN-20260909
orchestration_epoch: 20260909-rh-ab32
role: coder
repository: /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt
branch: 3060-12g-qwen35-4b
base_revision: 67b39b5aca6aaacbf410d21efda9b7059eaa8d2c
commit: 6edf69ce29

## Artifacts

- `python/sglang/srt/managers/scheduler.py`
- `3090-dev/test_ready_horizon_unit.py`
- `3090-dev/test_rh_contract_dependency_free.py`
- Commit `6edf69ce29` (`fix(hicache): correlate RH issue telemetry attempts`)

## Evidence

- `_ready_horizon_pass` now defers the authoritative `decision=issue`
  `rh_preadmission.v1` event until the sole RH `_prefetch_kvcache` call
  returns. Successful issue events use the returned
  `PrefetchIssueResult.attempt_id`; a missing ID cannot produce
  `decision=issue`.
- The prefetch result is emitted before `rh_stage.v2`, preserving the join
  order. Synchronous held/skipped results emit non-issue decision/reason
  classifications and retain the actual stage result/reason; no false issue
  is emitted.
- Captured RH policy inputs remain the pre-issue snapshot. Existing
  fingerprint suppression remains for non-issues, while attempted RH issue
  outcomes remain forced records; no second prefetch path was added.
- Added a dependency-free `(rid, attempt_id)` join/order test for
  `rh_preadmission.v1 -> rh_stage.v2 -> rh_ready_host.v1 -> rh_admission.v2`.
- Added RH pass tests for successful attempt correlation and held issue
  failure/no-false-issue behavior.

## Tests/results

- `python3 -m py_compile ...` — PASS for changed Python source/tests.
- `python3 -m compileall -q ...` — PASS.
- `git diff --check` — PASS.
- `python3 3090-dev/test_rh_contract_dependency_free.py` — 5 tests PASS.
- `python3 3090-dev/test_prefetch_gate_skip_regression.py` — 2 tests PASS.
- `python3 3090-dev/test_hicache_restore.py` — 92 tests PASS.
- AST deterministic check — PASS; one RH prefetch call and post-result
  decision emit using `result_attempt_id`.
- RH unit execution was attempted with `PYTHONPATH=python` but is blocked by
  missing environment dependency `orjson`.
- Formatting/typecheck commands were attempted; `black` and `mypy` are not
  installed in the environment.

## Summary

The final reviewer blocker is implemented: every successful RH issue decision
is emitted after claim creation with its actual attempt ID, and the stage,
ready-host, and admission events can join on the same `(rid, attempt_id)`.

## Followups

- Reviewer: independently inspect commit `6edf69ce29` and rerun the RH unit
  test in an environment containing the project dependencies.
- Runtime/deployment validation remains outside this implementation task.

## Open issues

- Missing `orjson` prevented execution of the import-dependent RH unit suite.
- Missing `black` and `mypy` prevented formatter/typechecker execution.
- Pre-existing unrelated untracked `.memory/`, `review/gates/`, and `storage/`
  artifacts were not modified or staged.
