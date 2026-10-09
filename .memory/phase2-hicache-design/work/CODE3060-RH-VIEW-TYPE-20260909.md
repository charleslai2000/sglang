ENTRY: ACCEPT

status: done
task_id: CODE3060-RH-VIEW-TYPE-20260909
orchestration_epoch: 20260909-rh-ab37
role: coder

## Artifacts

- `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/python/sglang/srt/managers/scheduler.py:4192-4195`
- `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/test_rh_contract_dependency_free.py:197-271`
- Commit `f629d4e2c1` (`fix(hicache): join RH frontier requests to policy views`)
- This report: `CODE3060-RH-VIEW-TYPE-20260909.md`

## Evidence

- The RH decision loop now builds `frontier_views` by RID, iterates raw `frontier_reqs` as `req`, and resolves `view = frontier_views[req.rid]` before accessing `staging_eligible`, `state`, or other policy fields. Issue execution remains on `plan.to_issue` views and raw request identity remains available through `view.req`.
- Added dependency-free regression `test_ready_pass_joins_raw_frontier_req_to_policy_view`. It executes the extracted real `_ready_horizon_pass` with a raw request that has no `staging_eligible`, a separate policy view, and asserts no `AttributeError`, the view identity, `exclude/no_restore_potential`, rank `1`, and frontier size `1`.
- `python3 -m unittest 3090-dev/test_rh_contract_dependency_free.py -v`: 6 tests passed.
- `python3 -m py_compile python/sglang/srt/managers/scheduler.py 3090-dev/test_rh_contract_dependency_free.py`: passed.
- `python3 -m compileall -q python/sglang/srt/managers/scheduler.py 3090-dev/test_rh_contract_dependency_free.py`: passed.
- AST parse and deterministic RH mapping check: passed.
- `git diff --check`: passed.
- Commit contains only the authorized source/test files; pre-existing unrelated untracked gate, memory, and storage artifacts were preserved.

## Summary

Fixed the RH-ON startup crash caused by treating raw `Req` objects from `frontier_reqs` as `ReadyHorizonView` instances. Policy-field decisions now use the corresponding view while RID/raw-request association and RH-OFF behavior remain unchanged.

## Followups

- A fresh Task ID is required for any remote/runtime restart or additional implementation work.

## Open issues

- Existing `3090-dev/test_ready_horizon_unit.py` could not import in this environment: with `PYTHONPATH=python`, import stops on missing dependency `orjson`.
- Repository formatter/typechecker executables (`pre-commit`/Black/Ruff and mypy/pyright) were unavailable; formatting evidence is `git diff --check`, and compile/AST checks passed.
