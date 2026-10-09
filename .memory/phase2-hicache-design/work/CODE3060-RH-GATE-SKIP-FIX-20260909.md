ENTRY: ACCEPT

status: done
task_id: CODE3060-RH-GATE-SKIP-FIX-20260909
orchestration_epoch: 20260909-rh-ab22
role: coder
repository: /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt
branch: 3060-12g-qwen35-4b
commit: 3785c99759d4026ebc4364ee46edb07987ed3b1a

## Artifacts

- Commit `3785c99759d4026ebc4364ee46edb07987ed3b1a`.
- `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/python/sglang/srt/managers/scheduler.py`
- `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/test_prefetch_gate_skip_regression.py`
- This implementation report only:
  `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/CODE3060-RH-GATE-SKIP-FIX-20260909.md`

## Change manifest and semantics

- `python/sglang/srt/managers/scheduler.py`
  - Replaced the gate-skip frontier-wait return that read the gate-pass-only
    local `outcome` with `PrefetchIssueResult.DECLINED`.
  - Preserved the existing gate-skip sequence: qualifying prompt check,
    `_no_material_fast_forward_for` decision, `GATE_SKIP_FRONTIER` state event,
    frontier-wait registration, and telemetry log.
  - Preserved the gate-pass storage prefetch path and its existing outcome/state
    handling. No RH ownership, claim, reservation, allocator, or I/O authority
    was changed.

- `3090-dev/test_prefetch_gate_skip_regression.py`
  - Added a dependency-free AST-extracted regression harness for the exact
    `enable_hicache_storage=True`, `prefetch_gate_ok=False`, qualifying prompt,
    `_no_material_fast_forward_for=False` condition.
  - The gate-skip case asserts no exception, frontier-wait registration, typed
    `DECLINED`, `GATE_SKIP_FRONTIER`, and zero `prefetch_from_storage` calls.
  - A companion gate-pass case asserts storage issue execution and preserves its
    existing typed return behavior.

Before the fix, the qualifying non-fast-forward gate-skip path registered its
frontier wait and then evaluated `outcome`, which was assigned only in the
gate-pass branch, raising `UnboundLocalError`. After the fix, that path returns
the existing typed non-issued result and leaves all prior wait/state/telemetry
behavior intact.

## Evidence

Passed:

- `python3 3090-dev/test_prefetch_gate_skip_regression.py`
  - `Ran 2 tests ... OK`.
- In-memory `compile(source)` for both changed Python files: PASS.
- Dependency-free AST check: `outcome` has one store in the gate-pass storage
  call and loads only in gate-pass outcome handling; no return expression reads
  `outcome`.
- `git diff --check`: PASS.
- Post-commit `git show --stat` and `git diff --name-status HEAD^ HEAD`: exactly
  the two authorized product source/test files.

Attempted but unavailable or environment-blocked:

- `ruff format --check ...`: `ruff` is not installed.
- Typecheck: neither `mypy` nor `pyright` is installed.
- `PYTHONPATH=python python3 3090-dev/test_hicache_restore_scheduler_feed.py`:
  collection stops at missing `orjson`.
- `PYTHONPATH=python python3 3090-dev/test_ready_horizon_unit.py`: collection
  stops at missing `orjson`.

No packages were installed, no remote service or storage was accessed, and no
unrelated pre-existing untracked `.memory/`, `review/gates/`, or `storage/`
artifacts were modified.

## Summary

Done. The reproduced HiCache gate-skip `UnboundLocalError` is fixed with a
single semantic return correction, and the exact frontier-wait/no-I/O condition
has a dependency-free regression oracle. The RH ownership contract and gate-pass
behavior remain unchanged.

## Followups

- Fresh tester Task ID: rerun the dependency-backed focused harnesses when the
  project environment provides `orjson` and perform independent post-fix
  acceptance.

## Open issues

- Formatter, typechecker, and dependency-backed unit evidence remain unavailable
  in this environment; this is implementation evidence, not independent final
  acceptance.
- No live or remote runtime evidence was authorized or collected.
