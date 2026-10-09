ENTRY: ACCEPT

status: done
task_id: CODE3060-RH-HYBRID-DISCARD-READY-20260909
orchestration_epoch: 20260909-rh-ab29
role: coder
repository: /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt
branch: 3060-12g-qwen35-4b
base_revision: 6881529acbb55c9dc55745d08fca62b585ecdbad
commit: 67b39b5aca

## Artifacts

- Commit `67b39b5aca` — `fix(hicache): reject discarded hybrid readiness`.
- Required report: this file.
- Source result path: `Scheduler._feed_restore_terminal` in
  `python/sglang/srt/managers/scheduler.py:3765`.
- Finalizer result path: `UnifiedRadixCache._handle_prefetch_result` and
  `_check_hybrid_prefetch_result` in
  `python/sglang/srt/mem_cache/unified_radix_cache.py:5576` and `:5832`.

## Changed files

- `python/sglang/srt/managers/scheduler.py`
- `python/sglang/srt/mem_cache/unified_radix_cache.py`
- `3090-dev/test_rh_contract_dependency_free.py`
- `3090-dev/test_storage_regression.py`

## Summary

The scheduler now consumes the finalizer-owned `finalize_result` before applying
the terminal event. `accepted` retains `FINALIZED -> READY` and emits
`rh_ready_host.v1`. `discarded` and `rejected` retain the terminal handoff but
use the recompute transition (`DENIED_SHORT` with `short_tail_recompute=True`),
leaving the request in `NONE` and suppressing ready-host emission. The hybrid
discard telemetry now records `restore_state_after=NONE`. Mamba and
all-or-nothing finalizer behavior remain unchanged.

## Evidence

Passed:

- `PYTHONDONTWRITEBYTECODE=1 python3 3090-dev/test_rh_contract_dependency_free.py` — 4 tests OK, including accepted, discarded, and rejected terminal-to-state/ready-host coverage.
- `PYTHONDONTWRITEBYTECODE=1 python3 3090-dev/test_hicache_restore.py` — 92 tests OK.
- `PYTHONDONTWRITEBYTECODE=1 python3 3090-dev/test_storage_regression.py RestoreDurabilityMarkingTests FrontierWaiterRegistryTests.test_release_aborted_request_cleans_waiter_and_terminal` — 5 tests OK.
- `PYTHONDONTWRITEBYTECODE=1 python3 3090-dev/test_prefetch_budget_split_unit.py PrefetchReservationExactlyOnceTests.test_hybrid_discard_path_releases_speculative_reservation` — OK.
- `python3 -m py_compile` for changed Python files — PASS.
- Independent `ast.parse` for changed Python files — PASS.
- `git diff --check` and post-commit `git diff HEAD^ HEAD --check` — PASS.
- Post-commit scope audit — exactly the four changed files listed above; existing untracked `.memory/`, `review/gates/`, and `storage/` content was not staged.

Unavailable or unrelated evidence:

- `ruff format --check` and `mypy` were unavailable because the tools are not installed.
- Package-backed `PYTHONPATH=python python3 3090-dev/test_hicache_restore_scheduler_feed.py` could not import because `orjson` is unavailable.
- The broader `test_prefetch_budget_split_unit.py` run had 12 fixture/import errors; its direct hybrid-discard reservation test passed. No unrelated failures were changed.

## Followups

- Fresh tester task: rerun dependency-backed scheduler-feed and bounded runtime checks when `orjson` and the target environment are available.
- Fresh independent reviewer task for gate acceptance; this implementation report is not an acceptance verdict.

## Open issues

- Formatter/typecheck tooling and package-backed scheduler integration remain uncomputed in this environment.
- Architecture/Pattern Intake/Novel Mechanism gate acceptance and remote runtime evidence remain outside this implementation task.
