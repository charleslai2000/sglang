status: done
artifacts:
- `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/python/sglang/srt/managers/cache_controller.py`
- `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/python/sglang/srt/mem_cache/unified_radix_cache.py`
- `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/python/sglang/srt/managers/scheduler.py`
- `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/python/sglang/srt/managers/scheduler_components/ready_horizon.py`
- `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/test_ready_horizon_unit.py`
- `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/test_prefetch_budget_split_unit.py`
evidence:
- `python3 -m py_compile` passed for all six modified source/test files.
- `git diff --check` passed.
- `msgspec` and `pytest` are unavailable in the local interpreter; dependency-backed unit execution was not possible without installation.
- Strict level semantics remain `current < cursor`; a new monotonic `speculative_release_epoch` increments exactly once for each SPECULATIVE reservation release and is included in RH causal snapshots. A parked entry stores the release epoch cursor and clears on a later release event, including a complete 0->N->0 cycle missed by level snapshots.
summary:
Implemented the smallest justified monotonic release-event mechanism for the unsampled SPEC_BUDGET ABA gap. The cache controller owns the monotonic release counter; UnifiedRadixCache increments it in the existing exactly-once release helper; Scheduler snapshots and records it only for SPEC_BUDGET parks; Ready Horizon uses it as an additional causal wake signal while preserving strict level comparison and physical limiter separation. Added literal 0/0 strictness and unsampled ABA regressions plus updated controller fixtures.
followups:
- Run focused RH tests in an already available dependency-complete environment containing msgspec, torch, pytest, and local sglang.
- Existing full-file RH failures documented in prior reports remain outside this bounded change.
open_issues:
- Local focused tests could not run because required dependencies are absent; no package installation was performed.
- Live 3060 RH acceptance remains a downstream operational gate and was not run.
- No commit, remote operation, deployment, reset, merge, rebase, push, or file deletion was performed.
exact_diff_summary:
- Added `HiCacheController.speculative_release_epoch` initialization.
- Incremented that counter in `UnifiedRadixCache.release_prefetch` only for SPECULATIVE reservations.
- Added `CausalEpochs.spec_budget_release_epoch` and `NegativeCacheEntry.release_epoch_cursor`; RH epoch-event and entry-clear logic now recognize monotonic release events.
- Scheduler snapshots the controller event count and records it for SPEC_BUDGET negative-cache entries; NO_L3, NO_HEADROOM, physical limiter, storage, allocator, and admission ownership remain unchanged.
- Added tests for strict cursor zero behavior and a complete unsampled level ABA release; retained existing post-issue and physical-only regressions.
test_commands:
- `python3 -m py_compile python/sglang/srt/managers/scheduler_components/ready_horizon.py python/sglang/srt/managers/scheduler.py python/sglang/srt/managers/cache_controller.py python/sglang/srt/mem_cache/unified_radix_cache.py 3090-dev/test_ready_horizon_unit.py 3090-dev/test_prefetch_budget_split_unit.py` — passed.
- `git diff --check` — passed.
- `PYTHONPATH=python python3 -m pytest -q 3090-dev/test_ready_horizon_unit.py -k "spec_budget"` — not run: pytest/msgspec unavailable.
# End report
open_issues:
- Dependency-backed focused tests remain pending in an existing complete environment.
- Downstream live/runtime acceptance remains separate.
