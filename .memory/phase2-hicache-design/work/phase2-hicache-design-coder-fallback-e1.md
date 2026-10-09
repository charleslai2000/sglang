# phase2-hicache-design-coder-fallback-e1

## status
done

## artifacts

- `python/sglang/srt/server_args.py` — added `hicache_partial_restore_fallback: bool = False` (NS("memory")) with full help text. Off = byte-for-byte upstream all-or-nothing discard.
- `python/sglang/srt/mem_cache/unified_radix_cache.py`
  - `init_hicache`: `self.hicache_partial_restore_fallback = server_args.hicache_partial_restore_fallback` (read once at init).
  - `_check_hybrid_prefetch_result`: return type changed `bool` -> `tuple[bool, int]`. On `pool_transfers and not all_succeeded`, if fallback on AND `host_memory_mode != "buffer_only"` (C8 out of scope), resume_len = `min(completed_tokens, operation.storage_hit_count)` (C1, the rank-synced folded boundary); resume_len > 0 -> `(True, resume_len)` (no invalidate_beyond, no host-mem release — C3); resume_len <= 0 -> fall through to the all-or-nothing discard cleanup (previously a `return False, 0` early-return would have LEAKED the prefetch — fixed). Off -> original discard path unchanged.
  - `_handle_prefetch_result`: caller unpacks `check_ok, usable_tokens`; on fail returns; else `completed_tokens = min(completed_tokens, usable_tokens)` (C2), which flows to fetched_key / insert_host / host_indices / hash_value / commit / `prefetch_loaded_tokens_by_reqid = loaded_from_storage` (C4). On success usable_tokens == completed_tokens so it is a no-op.
- `python/sglang/srt/managers/scheduler.py` — comment-only: `_ready_horizon_views` docstring and `full_prefix = staged > 0` note reflect that a positive resume_len marker is READY material under the fallback (C7; no behavior change — truthiness already admits it).
- `python/sglang/srt/managers/scheduler_components/ready_horizon.py` — comment-only: M6 membership docstring + `ReadyHorizonView.full_prefix` comment.
- `3090-dev/test_storage_regression.py` — `_make_cache` sets `hicache_partial_restore_fallback = False`; `_make_operation` added `extra_pool_hit_pages={}` to pool_storage_result.
- `3090-dev/test_partial_restore_fallback_unit.py` — NEW. 6 tests, all pass:
  1. off shortfall is all-or-nothing (invalidate fired keep=2, host released, entry dropped, marker 0)
  2. on shortfall resumes at storage_hit_count (inserted_key_len 2, marked, no invalidate, marker 2)
  3. storage_hit > completed clamped to fetched
  4. sidecar missing key / zero checkpoint -> full recompute (cleanup runs, no leak)
  5. buffer_only shortfall is all-or-nothing (C8)
  6. rank-consensus: zero per-rank fetched sidecar pages still resumes (boundary from storage_hit_count)
- `test/registered/unit/mem_cache/test_unified_radix_cache_unittest.py` — two mock tests updated for the new `(bool, int)` return and int `stats_requested_tokens` (the `8 < MagicMock` TypeError).

## evidence

All run from the repo, `PYTHONPATH=.../python`, venv `/home/charles/sglang-venv/bin/python`.

- Combined regression (storage_regression + prefetch_budget_split + hicache_restore + hicache_restore_scheduler_feed + ready_horizon_unit + ready_horizon_partition + partial_restore_fallback + extent_file_backend): **355 passed, 22 warnings in 10.23s**.
- `test_partial_restore_fallback_unit.py`: **6 passed**.
- `test_extent_file_backend_unit.py` (TRAILING reverse-scan): **77 passed**.
- `test_ready_horizon_unit.py` + `test_hicache_restore.py` + `test_hicache_restore_scheduler_feed.py` + `test_ready_horizon_partition.py`: **149 passed**.
- `test_unified_radix_cache_unittest.py::TestPrefetchCommitOrdering::test_prefetch_commit_applies_host_insert_actions_before_transfers`: **1 passed** (fixed).
- Syntax: `ast.parse` OK on unified_radix_cache.py and server_args.py; import `UnifiedRadixCache` OK.

The only failures I caused in the full unified_radix_cache_unittest file (469 failed / 670 passed / 1149 skipped) were the two mock tests, both now fixed. The rest of that file's failures are pre-existing environment issues: `ValueError: Not enough host memory available ... only have -X GB free` from shared-memory budget math in this dev container (affects TestReturnedValuesDrain and TestUnifiedRadixPrefetchCorruption at fixture setup, before reaching the code under test). Not caused by this change.

## summary

Implemented the Mamba/KV-granularity partial-restore fallback under the new `hicache_partial_restore_fallback` server arg. The core decision change is in `_check_hybrid_prefetch_result`: instead of all-or-nothing discard (usable=0) on a Mamba/SWA sidecar shortfall, a cache-mode fallback resumes at the rank-synced `operation.storage_hit_count` (the nearest node-tail checkpoint the extent backend's TRAILING reverse-scan already returned) and only the missing suffix is recomputed. The single clamp `completed_tokens = min(completed_tokens, usable_tokens)` in `_handle_prefetch_result` keeps the insert, host-node chain, sidecar commit and loaded-token marker on the SAME resume_len (C2/C4). The fallback path skips `invalidate_beyond` and the host-mem release (C3), so the KV beyond the boundary stays valid in L3. Off, and buffer_only mode (C8), stay byte-for-byte identical to upstream. The no-checkpoint sub-case was made to fall through to the shared discard cleanup rather than early-return, closing a prefetch-leak I caught while writing the tests.

## followups

- Integration/perf requirements for tester: (1) a live multi-rank hybrid stack where a Mamba shortfall fires, asserting the request resumes from the synced node-tail boundary and only the suffix is recomputed; (2) verify the KV beyond the boundary is NOT re-fetched/re-written (L3 hit on the next pass); (3) a ready-horizon pass confirming a resume_len partial restore is admitted to READY.
- The 469 "failures" in the full unified_radix_cache_unittest file under this container should be triaged by devops as a pre-existing environment/host-memory-budget issue, not a code regression.

## open_issues

- None blocking. The negative-host-memory environment failure is pre-existing and unrelated to this patch.
