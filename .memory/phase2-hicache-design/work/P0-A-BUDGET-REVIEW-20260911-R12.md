status: done

artifacts:
- Review of `3090-dev/test_prefetch_budget_split_unit.py` R11 patch.

evidence:
- Confirmed test-only changes: `threading` import, `_t38c_request_contexts = {}`, `_t38c_residency_lock = threading.RLock()`, and `trace_context=None` compatibility parameter.
- Assertions were preserved or strengthened.
- Compile and `git diff --check` passed.

summary:
- verdict: APPROVE
- Remote rerun may proceed in the dependency-complete 3060 environment.

followups:
- Hash-gate and run the focused/full budget suites, then the complete P0-A suite.

open_issues:
- Local scheduler-wiring tests remain unavailable because local dependencies are incomplete.
