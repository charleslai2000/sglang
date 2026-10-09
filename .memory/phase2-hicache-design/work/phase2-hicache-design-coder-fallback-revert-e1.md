# phase2-hicache-design-coder-fallback-revert-e1

## status

done

## artifacts

P2-Mamba partial-fallback patch (`hicache_partial_restore_fallback`) fully reverted to pre-patch (upstream-style all-or-nothing). Exact per-file changes:

1. `python/sglang/srt/server_args.py` — removed `hicache_partial_restore_fallback: A[bool, Arg(...NS("memory"))] = False` field + full help text (was at line 2866).
2. `python/sglang/srt/mem_cache/unified_radix_cache.py`
   - `init_hicache` (~:549-557): removed `self.hicache_partial_restore_fallback = server_args.hicache_partial_restore_fallback` + its P2-Mamba comment block.
   - `_handle_prefetch_result` (~:2773-2803): caller restored to single-bool form `if not self._check_hybrid_prefetch_result(...)`; removed the `check_ok, usable_tokens` unpack and the C2 clamp `completed_tokens = min(completed_tokens, usable_tokens)` + C2 comment block. The downstream insert/commit/loaded-marker now uses the un-clamped `completed_tokens` exactly as pre-patch.
   - `_check_hybrid_prefetch_result` (~:2893): return type restored `tuple[bool,int]` -> `bool`; docstring restored to pre-patch text ("all-or-nothing", "Returns true if prefetch success..."); re-inserted the "Hybrid cache state is all-or-nothing" comment before `expected_tokens`; removed the entire fallback branch (`if self.hicache_partial_restore_fallback and ...`: resume_len computation, storage_hit_count clamp, info/warning logs; the no-checkpoint fallthrough comment block); tail returns restored `return False` / `return True`.
3. `python/sglang/srt/managers/scheduler.py` (~:3452-3458, :3475-3477) — comment-only: `_ready_horizon_views` docstring restored to P3 original ("full-prefix gate is resident-material-present (marker > 0)"); removed the `hicache_partial_restore_fallback`/`resume_len` clause. `full_prefix = staged > 0` note restored to single-line P3 original ("the finalize writes the marker (> 0) on a full restore").
4. `python/sglang/srt/managers/scheduler_components/ready_horizon.py` (:19, :124-127, :239-244, :489-490) — comment-only: M6 membership docstring restored to v0 conservative ("the resident span must be the FULL requested prefix"); `ReadyHorizonView.full_prefix` comment restored; `_is_ready_resident` comment restored to full-prefix gate ("a partial restore is not pool material"); `_req_is_ready_resident` docstring restored (removed "A positive marker covers a partial-restore fallback resume as well as a full restore").
5. `3090-dev/test_storage_regression.py` — `_make_cache` removed `cache.hicache_partial_restore_fallback = False` + its comment; `_make_operation` removed `extra_pool_hit_pages={},` from `pool_storage_result` (restored single-line `update_extra_pool_hit_pages=...` without trailing comma). The `_RestoreMarkTree` test's `extra_pool_hit_pages={}` is pre-existing P3 and kept.
6. `3090-dev/test_partial_restore_fallback_unit.py` — **deleted** (patch-specific unit test; removed via `python3 -c os.remove()` on the exact path, per no-rm discipline; file was untracked, no other file references it).
7. `test/registered/unit/mem_cache/test_unified_radix_cache_unittest.py` — restored 2 mock tests to pre-patch: removed `operation.completed_tokens = 8`/`operation.stats_requested_tokens = 8` additions; `_check_hybrid_prefetch_result.return_value` restored `(True, 8)` -> `8` and `(True, completed_tokens)` -> `completed_tokens`. `git diff HEAD` for this file is now **empty** (byte-identical to HEAD).

Preserved (P3/P2-IO existing work, NOT touched): Ready Horizon flags & machinery, prefetch reservations (`release_prefetch`/`_demand_restore_rids`) in the discard/finalize paths, `hicache_restore_backup_park`, extent-file changes, all P3 tests. Name-collision note: `usable_tokens` in `scheduler.py`/`metrics_reporter.py`/`metrics_collector.py` is the P3 capacity-model gauge (S3), unrelated to the patch's `usable_tokens` — left intact.

## evidence

All commands run from repo root with venv `/home/charles/sglang-venv/bin/python`; exit codes captured raw (no pipeline swallowing).

1. **Trace cleanup greps** (zero matches, exit=1 on every one):
   - `grep -rn "hicache_partial_restore_fallback" python/ 3090-dev/ test/` -> 0 matches.
   - `grep -rn "resume_len" python/ 3090-dev/ test/` -> 0 matches.
   - `grep -n "check_ok\|usable_tokens\|partial fallback" python/sglang/srt/mem_cache/unified_radix_cache.py` -> 0 matches.
   - `test_partial_restore_fallback_unit.py` confirmed deleted on disk; `git ls-files` confirms it was never tracked; no references in test/run infra.
   - `test_unified_radix_cache_unittest.py` `git diff HEAD` empty (byte-identical).

2. **ast.parse OK** on `server_args.py`, `unified_radix_cache.py`, `scheduler.py`, `ready_horizon.py`, `test_storage_regression.py`, `test_unified_radix_cache_unittest.py` (all 6). `py_compile` OK on all modified files (`PY_COMPILE_OK`).

3. **Import OK**: `from sglang.srt.mem_cache.unified_radix_cache import UnifiedRadixCache` succeeds; `_check_hybrid_prefetch_result` return annotation is `bool`.

4. **Regression suites (all PASS, exit=0, one process at a time)**:
   - `3090-dev/test_storage_regression.py` — Ran 99 tests OK.
   - `3090-dev/test_prefetch_budget_split_unit.py` — Ran 24 tests OK.
   - `3090-dev/test_hicache_restore.py` — Ran 69 tests OK.
   - `3090-dev/test_hicache_restore_scheduler_feed.py` — Ran 7 tests OK.
   - `3090-dev/test_ready_horizon_unit.py` — Ran 55 tests OK.
   - `3090-dev/test_ready_horizon_partition.py` — Ran 18 tests OK.
   - Aggregate 272 tests, all green.

5. **Extent backend TRAILING folding regression**: `test/registered/unit/mem_cache/test_extent_file_backend_unit.py` — Ran 77 tests OK (this backend mechanism was untouched by the patch; run as required).

6. **2 restored mock tests in `test_unified_radix_cache_unittest.py`**: run in isolation from `test/registered/unit/mem_cache/` cwd they error with `TypeError: '<=' not supported between instances of 'MagicMock' and 'int'` (retry(3) exhausted). **Proven pre-existing at HEAD**, not a revert defect: reproduced byte-for-byte on a pristine `git worktree add HEAD` (detached e281df3635) — both `test_prefetch_commit_applies_host_insert_actions_before_transfers` and `test_dropped_prefetch_releases_all_host_resources` fail identically. The fallback coder's report explicitly says the patch "fixed" these 2 tests (by setting `operation.completed_tokens`/`operation.stats_requested_tokens`); the revert removes those adaptations, restoring the authentic pre-patch state where the tests fail in this container. The other `TestUnifiedRadixPrefetchCorruption` tests fail on `ValueError: Not enough host memory available ... only have -2.18 GB free` (the documented pre-existing 468-error container issue, unrelated to this revert).

7. **Byte-level function comparison**: my reverted `_handle_prefetch_result`/`_check_hybrid_prefetch_result` compared against HEAD source — the ONLY diffs are P3 additions (`release_prefetch` / `_demand_restore_rids` in the finalize/discard path), which are P3 work and correctly retained. All patch-relevant lines (bool call form, clamp removal, return statements, docstring) match HEAD byte-for-byte.

## summary

Reverted the P2-Mamba partial-fallback patch completely and precisely. The production logic in `_check_hybrid_prefetch_result` returns to the upstream-style all-or-nothing: a Mamba/SWA sidecar shortfall discards the whole prefetch (keep_pages computation + invalidate_beyond + host release + release_prefetch + marker=0 -> the scheduler recomputes ADMIT_RECOMPUTE). The flag, help text, init read, C2 clamp, fallback branch, patch-specific unit test, and the two mock-test adaptations are all removed. Verified the revert is byte-identical to HEAD for the test file, and functionally identical to HEAD for the reverted production regions (only P3 additions remain). Post-revert state = pre-patch state: all existing P3 regression suites green, TRAILING folding backend green, zero patch traces anywhere in python/ / 3090-dev/ / test/.

## followups

- Tester/verification on the 3090 head: none required beyond the standard post-revert greenbar (the 6 suites + extent backend already green here). The revert restores the same behavior the 3090 M4T test line already exercised pre-patch.
- The 2 reverted mock tests failing in this container (MagicMock <= int TypeError at pristine HEAD) could be scheduled as a separate task if a clean full-file run of `test_unified_radix_cache_unittest.py` is ever needed in this dev container — triage to devops as a pre-existing environment issue (same bucket as the 468 host-memory errors).

## open_issues

- None blocking. The two mock tests in `test_unified_radix_cache_unittest.py` fail in this container at pristine HEAD (pre-existing; see evidence item 6); this is not a revert defect — the revert restores exactly the pre-patch bytes.
- `ready_horizon.py` module docstring / comments are uncommitted P3 code (no git baseline); the pre-patch text was reconstructed from the P3-era test docstrings (`test_ready_horizon_unit.py`: "V0 conservative staging: the resident span must be the FULL requested prefix") and the scout-fallback-survey's quoted pre-patch `_is_ready_resident` description. The reconstruction carries zero behavior change (comment-only) and passes the ready_horizon unit suites.