status: done
artifacts:
- /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/test_ready_horizon_unit.py
- /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/test_prefetch_budget_split_unit.py
- /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/python/sglang/srt/managers/cache_controller.py
- /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/python/sglang/srt/managers/scheduler.py
- /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/python/sglang/srt/managers/scheduler_components/ready_horizon.py
- /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/python/sglang/srt/mem_cache/unified_radix_cache.py
evidence:
- VERIFIED: The corrected assertion block in `3090-dev/test_ready_horizon_unit.py:1186-1194` permits the legitimate later `r3` issue (`assertIn("r3", scheduler.issued)`), constrains the first two issues to `r1`, `r2`, and asserts `scheduler.issued.count("r2") == 1`.
- VERIFIED: The same block retains the release epoch, negative-entry absence, inflight-zero, and reservation-cleanup assertions; it therefore still checks that the ABA wake does not reissue `r2`.
- VERIFIED: The final test drives both release events through production `UnifiedRadixCache.reserve_prefetch`/`release_prefetch`, observes inflight return to zero, and observes `speculative_release_epoch == 2` before the wake pass.
- VERIFIED: Static AST parsing passed for all six changed Python files. `git diff --check` passed.
- VERIFIED: Release epoch invariants remain intact: the controller initializes the counter once; `release_prefetch` increments only after finding an active SPECULATIVE reservation; duplicate/missing releases and DEMAND reservations do not increment it; scheduler snapshots preserve it monotonically with `max`; SPEC_BUDGET parks capture the cursor; and policy clearing accepts either a strict level drop or a later release event.
- VERIFIED: The strict zero-to-zero case remains covered: no release event does not clear a zero cursor, while a later release epoch does.
- INFERRED: Production source hunks are unchanged by the assertion-fix task. The coder report states only the target assertion block was modified, and the current production hunks match the production set and invariants reviewed in `REVIEW-RH-RELEASE-FINAL-GATE-20260910.md`.
- UNVERIFIED: Dependency-complete focused unittest execution remains unavailable; the coder report records missing `orjson` (and the prior environment lacked pytest/msgspec/torch). No install or live trace was performed.
findings: []
summary:
The prior deterministic test defect is corrected: the test now allows the valid `r3` issue while proving `r2` is issued exactly once and remains absent from the negative cache. Static review finds no new production regression and confirms the release-epoch, strict-cursor, exactly-once-release, and cleanup invariants from the prior final review remain preserved.
open_issues:
- Focused runtime execution in an environment with the project dependencies is still required for runtime evidence; this is not a newly introduced static defect.
- Live 3060 acceptance remains a downstream gate and was not run.
verdict: APPROVE
