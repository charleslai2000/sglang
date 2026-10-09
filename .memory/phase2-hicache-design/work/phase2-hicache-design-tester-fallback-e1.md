# phase2-hicache-design-tester-fallback-e1

## status
done

## artifacts

Independent verification of the P2-Mamba partial-restore fallback patch
(`hicache_partial_restore_fallback` flag, default off). Performed on branch
`3090-24g-hicache`, repo
`/home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache`, venv
`/home/charles/sglang-venv/bin/python`. No trust of coder self-tests; all
re-run independently.

- `python/sglang/srt/mem_cache/unified_radix_cache.py`
  - `_check_hybrid_prefetch_result` (line 2893) now returns `tuple[bool, int]`.
    Fallback branch (line 2951-2997): gated on
    `hicache_partial_restore_fallback and host_memory_mode != "buffer_only"`;
    `resume_len = min(completed_tokens, operation.storage_hit_count)` (line
    2972); `resume_len > 0` -> `(True, resume_len)` (no invalidate_beyond, no
    host release); `resume_len <= 0` -> falls through to the all-or-nothing
    discard cleanup (no early-return leak).
  - `_handle_prefetch_result` (line 2742): single clamp
    `completed_tokens = min(completed_tokens, usable_tokens)` (line 2803),
    flows to fetched_key / insert_host / host_indices / hash_value / commit /
    `prefetch_loaded_tokens_by_reqid` (C2/C4). Off path & success path no-op.
- `python/sglang/srt/server_args.py` line 2866: the flag (default off).
- `python/sglang/srt/managers/scheduler.py` (comment-only, C7) + `ready_horizon.py`
  (comment-only): resume_len marker > 0 is READY-pool material.
- `3090-dev/test_partial_restore_fallback_unit.py` — NEW, 6 tests, all pass
  (off all-or-nothing / on resume at storage_hit / storage_hit>completed clamp /
  zero-boundary full-recompute no-leak / buffer_only all-or-nothing / rank-consensus
  zero-per-rank-fetched-pages still resumes).
- `3090-dev/test_storage_regression.py` — `_make_cache` sets
  `hicache_partial_restore_fallback = False` (off-path byte-for-byte preserved).
- `test/registered/unit/mem_cache/test_unified_radix_cache_unittest.py` — two mock
  fixes for the new `(bool, int)` return + int `stats_requested_tokens`
  (lines 7612-7613, 7628).

No in-scope code fixes required beyond what coder already shipped (the mock-test
adaptation and the zero-boundary fallthrough-leak fix were both verified correct;
I found no additional patch-introduced defect).

## evidence

All exit codes captured directly (no pipeline swallowing).

1. Fallback unit suite (independent re-run):
   `PYTHONPATH=.../python:.../3090-dev python 3090-dev/test_partial_restore_fallback_unit.py`
   -> `Ran 6 tests ... OK`, EXIT=0.
2. Six regression suites:
   `python -m unittest 3090-dev/test_storage_regression.py
   3090-dev/test_prefetch_budget_split_unit.py 3090-dev/test_hicache_restore.py
   3090-dev/test_hicache_restore_scheduler_feed.py
   3090-dev/test_ready_horizon_unit.py 3090-dev/test_ready_horizon_partition.py`
   -> `Ran 272 tests in 0.084s OK`, EXIT=0.
3. Extent backend (TRAILING reverse-scan):
   `PYTHONPATH=.../python python test/registered/unit/mem_cache/test_extent_file_backend_unit.py`
   -> `Ran 77 tests OK`, EXIT=0. (First attempt EXIT=1 was a missing-PYTHONPATH
   ModuleNotFoundError, an environment invocation issue, corrected.)
4. Coder-fixed mock test in isolation:
   `test_unified_radix_cache_unittest.TestPrefetchCommitOrdering.test_prefetch_commit_applies_host_insert_actions_before_transfers`
   -> `Ran 1 test OK`, EXIT=0.
5. Full shared unittest file (to independently reproduce the aggregate):
   `python -m unittest test_unified_radix_cache_unittest`
   -> `Ran 2288 tests in 9.806s FAILED (errors=468, skipped=1149)` EXIT=1.
   Classification: 1401 occurrences of `Not enough host memory available ...
   only have -0.7x GB free` (all at fixture setup, before reaching code under
   test) + 2 `RuntimeError: Failed to load HiCache native hash extension`
   (Ninja/build env, pre-existing). Matches coder's 469->468 claim; the
   coder-fixed mock test is confirmed green.

Aggregate: 6 + 272 + 77 + 1 = 356 tests green in the in-scope suites; the
unittest-file errors are confirmed environment/pre-existing, not patch-caused.

## summary

The patch is verified correct and 3090-verification ready. Diff review and
semantic review per the frozen adjudication:

- C1: resume_len comes from rank-synced `operation.storage_hit_count`
  (confirmed: prefetch_thread_func all-reduces MIN across ATTN groups at
  cache_controller.py:1332-1337; `_try_alloc_storage_hit` truncates hash_value
  and sets storage_hit_count=alloc_len at line 3515-3516), not per-rank
  extra_pool_hit_pages. The extra_pool_hit_pages test (rank zero-fetched still
  resumes) guards this.
- C2: single clamp `min(completed, usable)` (line 2803) flows to fetched_key/
  insert_host/host_indices/hash_value/commit/`prefetch_loaded_tokens_by_reqid`
  -- all same resume_len, no fork.
- C3: fallback success path returns before the discard block; no
  invalidate_beyond, no host release of fetched KV (L3 beliefs preserved).
- C4: `prefetch_loaded_tokens_by_reqid[req_id] = loaded_from_storage` = resume_len
  after insert; consumed at scheduler admission.
- C5: scheduler admission pop (no change needed).
- C6: host-memory safety on fallback path — no leak:
  (a) runtime invariant completed_tokens <= storage_hit_count (hash_value
  truncated at enqueue by storage_hit_count); (b) `_drain_ack_prefetch`
  releases `host_indices[completed_tokens:]` after finalize
  (line 3616-3623); (c) inserted prefix [0:resume_len] becomes tree-owned
  (cloned via commit, freed via prefix_len / dropped branch). The
  storage_hit_exceeds_completed unit case covers the clamp.
- C7 Ready Horizon: `full_prefix = staged > 0` (scheduler.py:3477); ready_horizon
  `_is_ready_resident` requires staged_tokens > 0 and full_prefix, so a positive
  resume_len marker is admitted to READY. Scheduler consumes resume_len prefix via
  match_prefix + recomputes the missing tail.
- C8: buffer_only keeps all-or-nothing — fallback gated `host_memory_mode !=
  "buffer_only"` (line 2953). Independently confirmed buffer_pipeline is only
  instantiated in buffer_only mode (line 623/628), so on the fallback path
  self.buffer_pipeline is None and the line-2816 staging branch is unreachable.
- Off path byte-for-byte: the diff is additive; off reaches the same discard
  block as pre-change (the removed early-return was a coder-fixed leak). Diff
  stat (552 lines on unified_radix_cache.py) includes pre-existing phase2
  uncommitted work, not this patch.

No patch-introduced defects found. Residual risks below are verification
(3090-live) items, not code defects.

## followups

Number + location + suggestion for 3090 verification (all live-only items the
unit/stub suites cannot cover):
1. `_drain_ack_prefetch` (unified_radix_cache.py:3616) tail-release — verify live
   that on a fired fallback the `[resume_len : ack_completed]` host bounce is
   actually returned to the pool (single + dual rank).
2. Multi-rank readiness with a Mamba shortfall — a real Mamba sidecar shortfall
   fires, request resumes from the synced node-tail boundary, only suffix
   recomputed.
3. KV beyond the resume boundary is NOT re-fetched/re-written on the next pass
   (L3 hit) — the acceptance effective_cache_ratio >= 95% measurement.
4. Ready-horizon admission of a resume_len partial restore (a positive marker
   admitted to READY).
5. Mamba state at the resume boundary actually present in the restored node
   (node.hash_value[-1] on the checkpoint grid) when the fallback fires live.
6. Acceptance: correctness == cold baseline on 3090.

## open_issues

- The 468 failures in test_unified_radix_cache_unittest are pre-existing
  environment failures (negative host-memory budget in this dev container +
  native hash extension build). Not patch-caused; triage to devops if a clean
  full-file run is ever needed.
- No blocking code defects. Design-level residual (K<node-boundary first-turn
  shape falls back to full recompute by design) is per the frozen adjudication.
