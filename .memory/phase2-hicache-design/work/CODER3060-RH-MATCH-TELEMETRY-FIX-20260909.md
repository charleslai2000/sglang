ENTRY: ACCEPT

status: done
task_id: T3060-RH-MATCH-TELEMETRY-FIX-20260909
orchestration_epoch: 20260909-rh-ab52
role: coder
repository: /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt
branch: 3060-12g-qwen35-4b
base_revision: c4ad01ef5d7578bb542fe3e514a71cdbccb6c07
implementation_revision: 9213ee01d9

## Artifacts

- Commit `9213ee01d9`: `fix(hicache): repair RH match telemetry joins`.
- Changed product symbol: `Scheduler._emit_rh_match_prepare` in
  `python/sglang/srt/managers/scheduler.py`.
- Regression: `RHContractDependencyFreeTests.test_later_pass_preparation_joins_current_decision_and_null_session` in
  `3090-dev/test_rh_contract_dependency_free.py`.

## Evidence

- Preparation telemetry now derives `decision_id` from the current positive
  `pass_seq` using the same `<rid>:rh:<pass_seq>` format as
  `_emit_rh_decision`; it no longer reads a prior cached request ID.
- Nullable `session_generation` now passes through the existing `field(...)`
  convention and emits literal `null`.
- Regression proves a later pass emits `r1:rh:2` in both preparation and
  preadmission telemetry, excludes stale `r1:rh:1`, and emits
  `session_generation=null`.
- `PYTHONDONTWRITEBYTECODE=1 python3 3090-dev/test_rh_contract_dependency_free.py -v`:
  16/16 passed.
- `PYTHONDONTWRITEBYTECODE=1 python3 3090-dev/test_prefetch_gate_skip_regression.py -v`:
  2/2 passed.
- `PYTHONDONTWRITEBYTECODE=1 python3 3090-dev/test_hicache_restore.py -v`:
  92/92 passed.
- `PYTHONPYCACHEPREFIX=/tmp/t3060-rh-telemetry-pycache python3 -m py_compile`
  passed for both changed product/test paths and the two unchanged focused
  test paths checked.
- `git diff --check` passed before commit; the committed diff contains only
  the two authorized files.

## Summary

Both concrete R2 telemetry defects are fixed with a scheduler-local, telemetry-only
change and a focused later-pass join regression. RH policy, allocator, Mamba,
cache, admission, deployment, and load behavior were not changed.

## Followups

- Fresh tester/reviewer task: rerun the independent R2/code-gate verification
  against commit `9213ee01d9`.
- Fresh environment task: run package-backed scheduler tests when required
  dependencies are available.

## Open issues

- Package-backed `3090-dev/test_ready_horizon_unit.py` remains uncollectable in
  this environment because `orjson` is unavailable; no package was installed.
- Formatter and typechecker executables/modules were unavailable:
  `black` and `mypy` are not installed. Syntax compilation and diff checks
  passed instead.
- Runtime/load/deployment evidence remains intentionally out of scope.
- Existing untracked `.memory/`, `review/gates/`, and `storage/` artifacts were
  preserved and are unrelated to this implementation commit.
