ENTRY: ACCEPT

status: done
task_id: T3060-RH-MATCH-PREP-VERIFY-20260909
orchestration_epoch: 20260909-rh-ab48
role: tester
source_repository: /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt
source_branch: 3060-12g-qwen35-4b
source_revision: f629d4e2c19eb74571b4154438fd651ce24ff53b
source_state: uncommitted changes present; product source not modified by this invocation

artifacts:
- /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/TEST3060-RH-MATCH-PREP-VERIFY-20260909.md
- source diff inspected in python/sglang/srt/managers/scheduler.py and python/sglang/srt/mem_cache/unified_radix_cache.py
- dependency-free test output from 3090-dev/test_rh_contract_dependency_free.py and 3090-dev/test_prefetch_gate_skip_regression.py

evidence:

- Required inputs were read: coder report `CODER3060-RH-MATCH-PREP-IMPLEMENT-20260909.md`,
  `ARCH3060-RH-MATCH-GATE-DESIGN-20260909.md`, revised match-prep Pattern Intake and
  Novel Mechanism artifacts, and accepted RH pre-admission Pattern Intake, Novel
  Mechanism, Architecture, and independent review gates. The revised match-prep
  Pattern Intake and Novel Mechanism artifacts are proposal-stage (`gate_verdict:
  PENDING`, implementation revision null). The prior RH pre-admission gates are
  accepted for the surrounding RH-ON/RH-OFF authority boundaries, not for the new
  match-preparation contract.

- Environment and identity:

  ```text
  python3 --version
  Python 3.12.3
  git rev-parse --abbrev-ref HEAD
  3060-12g-qwen35-4b
  git rev-parse HEAD
  f629d4e2c19eb74571b4154438fd651ce24ff53b
  orjson: False
  black: False
  mypy: False
  torch: False
  ```

- `python3 -m py_compile python/sglang/srt/managers/scheduler.py
  python/sglang/srt/mem_cache/unified_radix_cache.py
  3090-dev/test_ready_horizon_unit.py 3090-dev/test_rh_contract_dependency_free.py
  3090-dev/test_prefetch_gate_skip_regression.py`: PASS, exit 0.

- `python3 3090-dev/test_rh_contract_dependency_free.py`: PASS, 10/10 tests.
  Covered one-shot/non-COW preparation, deleted-anchor/retraction/fill identity
  invalidation, non-stageable state exclusion, request/view join, typed issue
  ordering, finalizer-owned auxiliary fields, discarded finalization, stale claim
  release, required event fields, and L3-durable-only restore-potential alignment.

- `python3 3090-dev/test_prefetch_gate_skip_regression.py`: PASS, 2/2 tests.
  Gate-pass storage issue and gate-skip wait/decline behavior remained intact.

- `PYTHONPATH=python python3 3090-dev/test_ready_horizon_unit.py`: BLOCKED by
  environment dependency, before test collection/import completed:
  `ModuleNotFoundError: No module named 'orjson'`.

- `PYTHONPATH=python python3 -m unittest 3090-dev/test_ready_horizon_partition.py`:
  BLOCKED at import by the same missing `orjson` dependency.

- `PYTHONPATH=python python3 -m unittest 3090-dev/test_hicache_restore_scheduler_feed.py`:
  BLOCKED at import by the same missing `orjson` dependency.

- `git diff --check`: PASS, exit 0.
  `git diff --name-only` showed the expected five modified files only:
  `scheduler.py`, `unified_radix_cache.py`, and the three focused 3090-dev tests.
  Untracked gate/memory artifacts were pre-existing workspace state and were not
  modified except for this report.

- Ownership/order source inspection:

  - `Scheduler._add_request_to_queue` calls `EAGER_RH_OFF` only when RH is off,
    and the call precedes `waiting_queue.append(req)` (scheduler.py:5313-5328).
  - `_ready_horizon_pass` increments `_rh_pass_seq`, computes the causal epochs and
    `should_refill`, then prepares candidates and only afterward calls
    `_ready_horizon_views` (scheduler.py:4453-4481).
  - The RH issue path passes the request-local prepared ticket to
    `_prefetch_kvcache`; valid tickets suppress the normal match, while an invalid
    or missing ticket performs one non-COW fallback rematch and fails closed if
    matching or anchor validation fails (scheduler.py:3197-3258, 4571-4578).
  - Candidate filtering excludes active/ongoing attempts, terminal requests,
    active chunked requests, RESTORING/READY, HOST_ALLOC, REVALIDATE,
    FRONTIER, BACKUP_PENDING, and other non-stageable states; dependency-free
    tests exercised the non-stageable subset.
  - No added scheduler diff line calls a Mamba allocator, eviction API, or
    HOST_ALLOC generation/FIFO operation. Preparation invokes only
    `req.init_next_round_input(self.tree_cache, cow_mamba=False)`; the existing
    Mamba finalizer's allocation/eviction branch is guarded by `cow_mamba`.
  - `UnifiedRadixCache.has_restore_potential` now accepts an extant
    `is_l3_durable` anchor, matching `prefetch_gate_ok`'s existing
    backuped/root/L3-durable predicate. The focused test passed for both the
    positive and negative L3-durable cases.

- Diff scope: `git diff --stat` reported 526 insertions and 17 deletions across
  the five modified files. No product implementation file outside the authorized
  scheduler/unified-cache surface was changed by the dispatch.

summary:

The available dependency-free behavior and syntax checks pass. The changed code
preserves RH-OFF eager-before-append ordering, places RH current matching after
the causal refill gate, uses an ephemeral one-shot ticket, keeps preparation
non-COW, and leaves allocator/HOST_ALLOC authority in the existing owners. No
functional failure was reproduced in the runnable focused harnesses.

The package-backed RH tests could not run because the environment lacks `orjson`
(and also lacks `torch`), so package/runtime integration behavior is not accepted
by this report. No deployment, remote load, or live RH-ON/RH-OFF replay was run.

followups:

- Fresh Task ID: run the package-backed RH unit/scheduler-feed suite in an
  environment containing the project dependencies, then collect eligible
  current-revision RH-ON and RH-OFF runtime joins if runtime acceptance is needed.
- Fresh Task ID: have the match-prep gate owner reconcile the revised Pattern
  Intake and Novel Mechanism artifacts, which remain pending, and independently
  review the open telemetry contract gap below.

open_issues:

- Match-prep telemetry does not implement the full `rh_match_prepare.v1` schema
  required by the design. `_emit_rh_match_prepare` logs neither
  `restore_state_before`, `match_duration_us`, `mamba_pool_idx_changed`,
  `mamba_cow_src_changed`, nor `mamba_needs_clear_changed`; it also does not
  distinguish `buffer_device_fallback` and emits no `skipped`/`ineligible` record
  for candidates rejected before preparation. This is an observability/evidence
  contract gap, not a reproduced core matching failure, but it prevents the
  specified telemetry oracle from proving all Mamba/no-match invariants.
- Full package-backed RH tests are blocked by missing `orjson`; `torch`, `black`,
  and `mypy` are also unavailable. These are infrastructure/dependency limits,
  not test failures.
- The revised match-prep Pattern Intake and Novel Mechanism gates are still
  marked pending; accepted prior RH gates do not by themselves accept this new
  one-shot mutating-match boundary.
