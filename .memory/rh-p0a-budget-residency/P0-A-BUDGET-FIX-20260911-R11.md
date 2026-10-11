status: done

artifacts:
- `3090-dev/test_prefetch_budget_split_unit.py`
- This report: `.memory/phase2-hicache-design/work/P0-A-BUDGET-FIX-20260911-R11.md`

evidence:
- Added `threading` import.
- Initialized `_t38c_request_contexts = {}` and `_t38c_residency_lock = threading.RLock()` in `_make_budget_cache()`.
- Added `trace_context=None` to `_BudgetController.prefetch()`.
- `python3 -m py_compile` and `git diff --check` passed.
- Local runtime was dependency-blocked; no remote or product changes.

summary:
- Applied only the R10 evidence-backed fixture initialization corrections.
- P0-A remains NOT_VERIFIED pending remote execution.

followups:
- Hash-gate and rerun focused/full budget tests remotely, then rerun complete P0-A.

open_issues:
- Local scheduler dependencies are unavailable.
