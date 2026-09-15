status: done

artifacts:
- `3090-dev/test_ready_horizon_unit.py`
- `3090-dev/test_prefetch_budget_split_unit.py`
- `3090-dev/test_hicache_restore_scheduler_feed.py`
- This report: `.memory/phase2-hicache-design/work/P0-A-FIX-FIXTURES-20260911.md`

evidence:
- Inspected the pre-existing dirty diff before editing. Product files under `python/` were not modified by this task.
- Updated typed `PrefetchIssueResult` checks to assert the dataclass and its `status` (`ISSUED` / `SKIPPED_ACTIVE`) rather than compatibility enum aliases.
- Updated all affected test doubles to accept the current keyword-only `origin=` contract, including deterministic-miss, scheduler-feed, and budget-split wake fixtures.
- Updated the ready-stage telemetry assertion from the obsolete `evt=ready_stage.v2` token to `evt=ready_stage schema=rh_stage.v2`.
- Initialized `_t38c_node_context_index` in the torch-free durable-trace cache fixture.
- Added `pop_host_alloc_failure` to the resident-tail scheduler fixture.
- Corrected HOST_ALLOC wake expectation to match the reviewed permissive retry contract: alloc -> evict_host -> alloc remains authoritative, so an incomplete currently-free span does not suppress the wake.
- `git diff --check`: passed.
- `/usr/bin/python3 -m py_compile 3090-dev/test_ready_horizon_unit.py 3090-dev/test_prefetch_budget_split_unit.py 3090-dev/test_hicache_restore_scheduler_feed.py`: passed.
- Attempted local pytest command with `PYTHONPATH=python:3090-dev`; unavailable because this environment has no `pytest` module. No remote test run was performed.

summary:
- Reconciled the 17 R3 failures identified as stale/incomplete fixtures or assertions without changing product implementation.
- Preserved test intent and strengthened assertions around the current typed result and telemetry schemas.
- The host-capacity test now exercises the complete request geometry while asserting the current retry admission semantics; it was not changed merely to bypass a failure.

followups:
- Rerun the authorized P0-A regression suite remotely on the 3060 checkout using the next task's procedure.
- Remote P0-A pass is not claimed by this task.

open_issues:
- Local unit execution is unverified because `pytest` is not installed in the available local Python environment.
- Any remaining remote failures should be classified independently; this report does not authorize product-code changes.
