ENTRY: ACCEPT

status: done
task_id: T3060-RH-MATCH-PREP-IMPLEMENT-20260909
orchestration_epoch: 20260909-rh-ab47
role: coder
source_repository: /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt
source_branch: 3060-12g-qwen35-4b
source_revision_before: f629d4e2c19eb74571b4154438fd651ce24ff53b
source_revision_after: f629d4e2c19eb74571b4154438fd651ce24ff53b
commit_hash: not committed

artifacts:
- python/sglang/srt/managers/scheduler.py
- python/sglang/srt/mem_cache/unified_radix_cache.py
- 3090-dev/test_ready_horizon_unit.py
- 3090-dev/test_rh_contract_dependency_free.py
- 3090-dev/test_prefetch_gate_skip_regression.py

summary:
Implemented the accepted narrow RH current-match preparation fix on the 3060
worktree only. RH now performs one causal-gated current
Req.init_next_round_input(self.tree_cache, cow_mamba=False) for each eligible
frontier request, builds views from the resulting current fields, and passes a
scheduler-local immutable one-shot ticket to the immediate RH issue path.
Valid tickets suppress the duplicate issue-time match. Missing/stale/deleted
tickets perform one non-COW fallback rematch and fail closed if preparation or
anchor validation fails. RH-OFF eager-before-append ordering and admission-time
matching/COW were left in place.

The lower eligibility defect from DBG was also corrected: UnifiedRadixCache
has_restore_potential now accepts an extant non-root anchor when
tree_core.is_l3_durable(anchor_node_id) is true, aligning RH staging eligibility
with prefetch_gate_ok without changing allocator, eviction, HOST_ALLOC, or
Mamba ownership.

exact_changed_symbols:
- scheduler.py:_ReadyHorizonPreparedMatch
- scheduler.py:Scheduler._prefetch_kvcache
- scheduler.py:Scheduler._prefetch_kvcache_impl
- scheduler.py:Scheduler._rh_match_candidate
- scheduler.py:Scheduler._emit_rh_match_prepare
- scheduler.py:Scheduler._rh_current_match_anchors_valid
- scheduler.py:Scheduler._prepare_ready_horizon_match
- scheduler.py:Scheduler._rh_prepared_match_valid
- scheduler.py:Scheduler._rh_match_candidate_without_active_attempt
- scheduler.py:Scheduler._ready_horizon_pass
- scheduler.py:Scheduler._ready_horizon_views
- unified_radix_cache.py:UnifiedRadixCache.has_restore_potential

evidence:
- `python3 -m py_compile` passed for scheduler.py, unified_radix_cache.py,
  test_ready_horizon_unit.py, test_rh_contract_dependency_free.py, and
  test_prefetch_gate_skip_regression.py.
- `python3 3090-dev/test_rh_contract_dependency_free.py` passed: 10 tests,
  including one-shot/non-COW preparation, non-stageable-state exclusion,
  deleted-anchor/retraction/fill-identity invalidation, and L3-durable-only
  prefetch-gate/restore-potential alignment.
- `python3 3090-dev/test_prefetch_gate_skip_regression.py` passed: 2 tests.
- `git diff --check` passed.
- `python3 3090-dev/test_ready_horizon_unit.py` was attempted with
  `PYTHONPATH=python` and is unavailable because the environment lacks
  `orjson`.
- `python3 -m black --check ...` was unavailable because `black` is not
  installed; `python3 -m mypy ...` was unavailable because `mypy` is not
  installed.
- Optional neighboring `test_p0_residency_barrier_emitter.py` reached its
  existing source-backed probe and failed on missing `_bump_host_allocability`
  in its `_SchedulerCache` fixture; no unrelated fix was made.
- No live load, deployment, remote host, launch-script, or 3090 worktree
  operation was performed.

followups:
- Independent tester/reviewer should run the package-backed RH suite in an
  environment with its declared dependencies and verify the full runtime
  gates at the descendant revision.
- A fresh dispatch is required for any additional implementation, review,
  deployment, or live-load work.

open_issues:
- No commit hash is available because this invocation did not commit.
- Full package-backed RH tests, formatter, and typechecker remain unverified
  locally due missing tools/dependencies.
- Independent review and live RH-ON/RH-OFF acceptance remain outstanding and
  are outside this coder invocation.
