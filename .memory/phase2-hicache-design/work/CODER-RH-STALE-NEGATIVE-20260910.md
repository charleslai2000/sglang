status: done
artifacts:
- /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/python/sglang/srt/managers/scheduler.py
- /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/test_ready_horizon_unit.py
evidence:
- Inspected the final review finding and the production lifecycle. The successful RH issue path previously left an existing SPEC_BUDGET negative entry in place; this could be re-considered on a later unrelated causal pass when the request remained eligible.
- Implemented the smallest lifecycle fix in `_ready_horizon_pass`: after a successful issue, consume the prior negative entry. The production restore state machine and active attempt now own retries; no stale release history remains attached to the request.
- Extended the real-helper ABA regression to call `UnifiedRadixCache.reserve_prefetch`/`release_prefetch`, perform a complete 0 -> N -> 0 release cycle, then add a later unrelated frontier event and assert no duplicate issue. The test also asserts the request is RESTORING and the negative entry is consumed.
- `python3 -m py_compile /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/python/sglang/srt/managers/scheduler.py /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/test_ready_horizon_unit.py` passed.
- `git -C /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt diff --check` passed.
- Focused pytest/unittest execution was attempted but blocked before test execution: pytest is unavailable and importing the test module fails on missing `orjson`. No packages were installed.
summary:
The reviewed behavior exposed a real stale-negative lifecycle gap, so a bounded production fix was required rather than only reshaping the assertion. Successful issue now consumes the old negative cache entry while preserving strict `<` cursor semantics, release-epoch exactly-once accounting, physical/demand separation, and event-driven no-poll behavior. The ABA test now exercises production reservation/release and a later unrelated frontier event.
followups:
- Run the focused Ready Horizon tests in an existing dependency-complete environment.
- Independent tester should verify the full RH unit subset and downstream runtime gate.
open_issues:
- Local dependency-light test execution remains unavailable because pytest/orjson (and previously msgspec) are absent.
- No remote/live trace, package installation, Git history operation, commit, or deployment was performed.
