status: done

artifacts:
- Reviewed coder report: `.memory/phase2-hicache-design/work/P0-A-FIX-FIXTURES-20260911.md`
- Reviewed R3 failure report: `.memory/phase2-hicache-design/work/P0-A-RH-REGRESSION-RECONCILED-20260911-R3.md`
- Reviewed current git diff for the three fixture files and the pre-existing dirty product diff.
- This report: `.memory/phase2-hicache-design/work/P0-A-FIX-FIXTURES-REVIEW-20260911.md`

evidence:
- The fixture changes are confined to `3090-dev/test_ready_horizon_unit.py`, `3090-dev/test_prefetch_budget_split_unit.py`, and `3090-dev/test_hicache_restore_scheduler_feed.py` in the reviewed task report. The current worktree also contains modifications under `python/`, but those are the separately observed pre-existing product diff described by the coder and are not included among this task's artifacts.
- The `PrefetchIssueResult` assertions were not weakened: the current API returns a dataclass, and the tests now assert both the result type and the concrete `HiCachePrefetchIssueStatus` (`ISSUED` or `SKIPPED_ACTIVE`). This is stronger and avoids relying on compatibility aliases.
- The updated doubles accept the current keyword-only `origin` argument. The production scheduler invokes `_prefetch_kvcache(..., origin=...)`, so the previous lambdas were stale and could fail before testing the intended behavior.
- The durable-trace fixture now initializes `_t38c_node_context_index`, matching the product code's access path; the scheduler-feed fixture now supplies `pop_host_alloc_failure`, matching the current fixture protocol. These changes repair setup/API compatibility rather than bypassing assertions.
- The HOST_ALLOC expectation is justified by the current implementation at `python/sglang/srt/managers/scheduler.py:5206-5215`: after rate-limit and basic-input checks, the wake predicate intentionally returns true without requiring the full span to be free because authoritative retry is `alloc -> evict_host -> alloc`. The test still checks the complete request geometry and retains the true result after the available amount is increased; it does not remove the wake assertion.
- The ready-stage log assertion was updated from the obsolete `evt=ready_stage.v2` token to the emitted `evt=ready_stage schema=rh_stage.v2` form, preserving request/result matching.
- `git diff --check` passed. No remote tests were run and no P0-A pass is claimed.

summary:
- Within the reviewed fixture task, the changes reconcile stale test doubles, result-shape assertions, initialization, and telemetry schema with the current API. The substantive assertions were preserved or made more explicit. The HOST_ALLOC semantic change is consistent with the implementation's documented permissive retry contract, not an unexplained failure suppression.
- No fixture change was found that weakens the tested behavior or modifies product code as part of the reported task. Independently, the worktree is dirty in four product files (plus other product files according to status); attribution to this fixture task is based on the coder's pre-existing-diff statement and task artifact list, not on Git history alone.

followups:
- Rerun the authorized regression suite separately to determine whether the reconciled fixtures pass; this review does not establish runtime or remote P0-A success.
- Before final acceptance, preserve the boundary between this fixture-only change and the separately tracked product diff (for example, review/stage them independently).

open_issues:
- The current worktree alone cannot prove when the product-file modifications were introduced; it only shows that they are present. If strict provenance of the fixture patch is required, obtain the coder's patch/commit or a clean baseline comparison.
- Local pytest execution remains unavailable per the coder report.

verdict: APPROVE
