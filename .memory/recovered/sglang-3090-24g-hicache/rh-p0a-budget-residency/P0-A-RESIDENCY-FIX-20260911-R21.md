status: done

artifacts:
- `3090-dev/test_prefetch_budget_split_unit.py`
- This report: `.memory/phase2-hicache-design/work/P0-A-RESIDENCY-FIX-20260911-R21.md`

evidence:
- Added exactly one fixture initialization immediately after `_t38c_residency_lock = threading.RLock()`:
  `cache._t38c_residency_queue_blocked = set()`.
- No product files or other test files were edited by this invocation.
- Existing assertions were preserved.
- `python3 -m py_compile 3090-dev/test_prefetch_budget_split_unit.py`: passed.
- `git diff --check -- 3090-dev/test_prefetch_budget_split_unit.py`: passed.
- Targeted `PYTHONPATH=python:3090-dev /usr/bin/python3 3090-dev/test_prefetch_budget_split_unit.py`: 19 passed, 1 skipped, 4 errors; the errors are pre-existing harness import failures (`ModuleNotFoundError: No module named 'sglang.srt.managers.scheduler'`) in scheduler wiring tests.
- No formatter or typechecker executable is available in the local environment; the one-line initialization is formatting-neutral and `py_compile` provides syntax validation.

summary:
- Applied the exact R20 one-line test-fixture correction for the residency queue blocked state.

followups:
- None for this scoped correction.

open_issues:
- Pre-existing unrelated working-tree changes remain untouched.
- Targeted unittest execution remains partially blocked by the local torch-free harness not providing `sglang.srt.managers.scheduler`; no product or unrelated test changes were made to address it.
