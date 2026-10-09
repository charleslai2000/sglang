ENTRY: ACCEPT

status: done
task_id: CODE3060-RH-PREADMISSION-20260909
orchestration_epoch: 20260909-rh-ab20
role: coder
repository: /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt
branch: 3060-12g-qwen35-4b
commit: 3ddc39c223

## Artifacts

- Commit `3ddc39c223` — `Add RH pre-admission prefetch ownership`.
- Product/test changes are limited to the five files in the commit.
- This report is the only artifact written outside the authorized source
  repository, at the dispatch-specified path.

## Change manifest

- `python/sglang/srt/managers/scheduler.py`
  - Added `HiCachePrefetchOrigin`-tagged prefetch claims and
    `PrefetchIssueResult` handling at the existing `_prefetch_kvcache`
    boundary.
  - RH-ON normal `NULL` requests append to `waiting_queue` first; the
    existing `_ready_horizon_pass` is the only initial RH-ON issue owner.
  - RH-OFF normal enqueue retains eager prefetch before append with
    `EAGER_RH_OFF`.
  - Classified reconciliation/frontier/capacity retries as `DEMAND_RETRY`.
  - Added matching claim retirement on terminal outcomes and queued abort
    paths; HOST_ALLOC, allocator, Mamba, and full-span restore logic were not
    changed.
  - Added bounded `rh_preadmission`, `ready_stage.v2`, `ready_host`, and
    `admission.v2` records carrying request/attempt/origin joins where an
    attempt exists; absent attempt values are emitted as `none`, not zero.
- `python/sglang/srt/managers/schedule_batch.py`
  - Added ephemeral request-local prefetch sequence, active claim, last
    attempt, and origin fields beside existing restore-control state.
- `python/sglang/srt/managers/scheduler_components/hicache_restore.py`
  - Added the origin and issue-result enums without changing restore-state,
    HOST_ALLOC, or allocator transitions.
- `3090-dev/test_ready_horizon_unit.py`
  - Added RH-ON queue-first, RH-OFF eager-order/origin, active-claim
    duplicate suppression, demand-retry classification, and stage telemetry
    assertions; retained repeated-pass and OFF no-op coverage.
- `3090-dev/test_hicache_restore_scheduler_feed.py`
  - Updated the direct lower-path fixture to use `DEMAND_RETRY` explicitly.

## Invariant mapping

- `RH-PA-I1/I2/I3`: request-local active claim plus RH-ON queue-first
  enqueue makes `_ready_horizon_pass` the sole initial issue owner and blocks
  duplicate lower submissions.
- `RH-PA-I4`: RH-OFF normal enqueue still calls the prefetch path before queue
  append and is explicitly tagged `EAGER_RH_OFF`; RH pass remains a no-op.
- `RH-PA-I5/I10`: active claims are released only on non-issued outcomes,
  matching terminal outcomes, exceptions, and queued cancellation paths;
  stale active claims cannot be replaced by another origin.
- `RH-PA-I6/I7/I8/I9`: lower storage, hybrid finalization, Mamba flush/evict,
  positive-hit, HOST_ALLOC generation, FIFO retry, and allocator authority
  remain in their existing code paths; only origin plumbing and claim
  ownership were added.
- `RH-MAP-007`: stage/readiness/admission observations are request-correlated
  and observational; telemetry is not a scheduling guard.

## Evidence

Passed:

- `python3 -m py_compile` on all three changed source files and both changed
  test files.
- `python3 -m compileall -q` on the same files.
- `git diff --check`.
- Dependency-free AST parse of all five changed files.
- Dependency-free AST scan proving every scheduler `_prefetch_kvcache`
  caller supplies an explicit `origin`.
- Deterministic source checks proving all required origin classes and
  `rh_preadmission`, `ready_stage.v2`, `ready_host`, and `admission.v2`
  emitters are present.

Attempted but blocked:

- `ruff format --check ...`: `ruff` is not installed.
- Typecheck: neither `mypy` nor `pyright` is installed.
- `python3 3090-dev/test_ready_horizon_unit.py` and
  `python3 3090-dev/test_hicache_restore_scheduler_feed.py`: package import
  is unavailable without `PYTHONPATH`; with `PYTHONPATH=python`, collection
  stops at missing dependency `orjson`.
- `pytest`, `black`, and `uv` are not installed.

Continuation safety note:

- No long-running pytest/unittest process was present when checked.
- No runtime test was started during the bounded continuation after the user
  interruption; only the static/compile checks listed above were run.
- No additional source/test files were changed after commit `3ddc39c223`.

## Summary

Implemented the accepted RH pre-admission ownership contract with minimal
source/test changes. RH-ON direct requests now become visible to the RH
frontier before any initial prefetch, while RH-OFF retains its eager ordering.
The active attempt/origin claim prevents duplicate prefetch/I/O and keeps
demand retries distinct from RH staging. Existing HOST_ALLOC and Mamba
semantics remain delegated to their original owners.

## Followups

- Re-run the two focused unit harnesses in an environment containing the
  project runtime dependencies, especially `orjson`.
- Run repository formatter/typecheck gates in the project toolchain when
  available.

## Open issues

- Runtime-focused tests, formatter, and typecheck evidence are unavailable in
  this environment because required executables/dependencies are missing.
- The branch still contains unrelated pre-existing untracked gate, storage,
  and `.memory/` artifacts; they were not modified or staged.
