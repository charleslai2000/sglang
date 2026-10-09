# Phase2 HiCache — partial fallback policy patch (Mamba/KV granularity) — scout survey

## 1. status

done

## 2. artifacts

Read (verified, absolute paths):

- `/home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache/python/sglang/srt/mem_cache/unified_cache/components/mamba_component.py` (937 lines, full read)
- `/home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache/python/sglang/srt/mem_cache/unified_radix_cache.py` (selective: 2390-2444, 2462-2683, 2685-2871, 2872-2966, 3060-3209, 3455-3547, 4000-4052)
- `/home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache/python/sglang/srt/mem_cache/storage/extent/extent_file_backend.py` (full read)
- `/home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache/python/sglang/srt/mem_cache/storage/extent/extent_allocator.py` (method list)
- `/home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache/python/sglang/srt/mem_cache/buffer_mode/storage_existence_cache.py` (89 lines, full read)
- `/home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache/python/sglang/srt/mem_cache/hicache_storage.py` (PoolHitPolicy / PoolTransfer / PoolTransferResult / count_pool_hits)
- `/home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache/python/sglang/srt/mem_cache/hybrid_cache/hybrid_cache_controller.py` (selective: 60-99, 563-579, 601-637, 639-723, 724-783, 802-874, 876+)
- `/home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache/python/sglang/srt/managers/cache_controller.py` (selective: 1140-1185, 1186-1235, 1291-1351)
- `/home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache/python/sglang/srt/managers/scheduler.py` (selective: 2943-3053, 3058-3182, 3184-3210, 3698-3724, 4328-4492)
- `/home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache/python/sglang/srt/managers/scheduler_components/hicache_restore.py` (363 lines, full read)
- `/home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache/python/sglang/srt/managers/scheduler_components/ready_horizon.py` (538 lines, full read)
- `/home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache/python/sglang/srt/managers/schedule_batch.py` (selective: 962-972, 1028-1035, 1269-1276, 1420-1431, 2535-2562, 2702-2795)
- `/home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache/python/sglang/srt/managers/schedule_policy.py` (selective: 185-213, 1400-1459)
- `/home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache/python/sglang/srt/mem_cache/unified_cache/components/swa_component.py` (selective: 870-907, 980-1045)
- `/home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache/python/sglang/srt/mem_cache/unified_cache/unified_tree_core.py` (selective: 108-230, 519-578)
- `/home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache/python/sglang/srt/mem_cache/buffer_mode/pipeline.py` (selective: 340-400, 690-810)
- `/home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache/python/sglang/srt/mem_cache/mamba_radix_cache.py` (selective: 1140-1207)
- `/home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache/python/sglang/srt/runtime_context.py` (selective: 1633-1652)
- `/home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache/python/sglang/srt/hardware_backend/mlx/model_runner.py` (selective: 375-392)
- `/home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache/python/sglang/srt/mem_cache/hiradix_cache.py` (selective: 1475-1540)
- `/home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache/python/sglang/srt/mem_cache/unified_cache/components/README.md` (fragment)
- Tests: `test/registered/unit/mem_cache/test_extent_file_backend_unit.py` (selective: 590-760), `test/registered/unit/mem_cache/test_unified_radix_cache_unittest.py`, `test_mamba_unittest.py`, `test_summary` for the directory
- Desk probes: `3090-dev/p2io_e28_boundary_trace.py` (full), `p2io_e24_mamba_probe.py` (method list), `p2io_e7p_recompute_quant.py`/`p2io_e7p_three_cases.py` (method list), `metric_compare.py`
- Memory: `ledger.md` (selective 439-530), `fetched-hicache-upstream.md` (fragment)

grep/glob search scopes: `grep -rn` over `python/`, `rust/`, `test/`, `3090-dev/` for tokens: TRAILING_PAGES, batch_exists_v2, _sync_trailing_keys, invalidate_beyond, mamba_branching_seqlen, mamba_checkpoint_grid, mamba_host_hit_length, full_kv_hit_length, _check_hybrid_prefetch_result, storage_hit_length, _page_transfer, _storage_hit_query, extra_pool_hit_pages, _build_sidecar_transfers, init_load_back.

## 3. evidence

### 3.1 Write-side mamba checkpoint (BACKUP_STORAGE) — frozen baseline

- `mamba_component.py:752-763` `build_hicache_transfers(BACKUP_STORAGE)`: returns
  `PoolTransfer(name=MAMBA, host_indices=cd.host_value, keys=[node.hash_value[-1]], hit_policy=TRAILING_PAGES)`.
  Condition `cd.host_value is None or not node.hash_value` -> None.
- `node.hash_value[-1]` = the node's last *page* hash, which — because the radix node is the checkpoint boundary (node lengths land on `mamba_cache_chunk_size` / the DCP-widened tree page, runtime_context.py:1639-1644 `mamba_checkpoint_grid = lcm(mamba_cache_chunk_size(), tree_page)`) — is the "node-tail checkpoint page".
- PREFETCH side: `mamba_component.py:765-774`: `PoolTransfer(name=MAMBA, host_indices=host_indices, keys=["__placeholder__"], hit_policy=TRAILING_PAGES)` — keys are placeholders; the real trailing hashes are filled only post-query by `_sync_trailing_keys`.
- `mamba_component.py:160-184` `finalize_match_result_in_tree_core`: computes
  `mamba_boundary_len = len(device_indices) + host_hit_length`;
  `aligned_seqlen = (full_kv_hit_length // mamba_checkpoint_grid) * mamba_checkpoint_grid`;
  `branching_seqlen = aligned_seqlen if aligned_seqlen > mamba_boundary_len else None`.
  This is the upstream-admitted "Full KV may extend beyond the latest reusable Mamba state" (device-side match; not the L3 prefetch path).
- `mamba_component.py:179-183`: if `has_host_value_only(last_node)` forces `mamba_host_hit_length = max(...,1)` so `load_back` triggers. This is a *device* load-back, distinct from the L3 restore path.

### 3.2 Read-side: TRAILING boundary scan (the resume_len mechanism already exists)

- `hicache_storage.py:88-96`: `PoolHitPolicy.TRAILING_PAGES = "trailing_pages"` — "only the last N pages must exist (e.g. Mamba/SWA states)".
- `extent_file_backend.py:618-673` `batch_exists_v2`:
  - `kv_pages` = longest contiguous KV prefix via `present(self._storage_key(keys[i]))` (single-key allocator lookup, line 626-632).
  - TRAILING branch (lines 660-669): `trailing = max(1, len(transfer.keys))`;
    `for prefix_len in range(kv_pages, 0, -1)`: checks `all(present(component_key(name, keys[i])) for i in range(prefix_len-trailing, prefix_len))`; returns the *largest* `prefix_len` whose trailing window is fully present, else 0.
    For mamba with `trailing=1` this **is exactly a reverse scan from kv_pages for the nearest present `.mamba` tail-key** — i.e. the read-side "nearest ≤ kv_hit_len node-tail checkpoint" mechanism is *already implemented* at the backend.
  - `_component_key(name, key)` = `_storage_key(f"{key}.{pool_name}")` (lines 286-289), so MAMBA keys are namespaced by pool — the KV chain hash itself is reused as the mamba key namespace (no new query primitive needed for single-key existence; allocator.lookup is per-key).
- `extent_allocator.py:76` `lookup(key) -> Optional[ExtentRef]` — single-key existence, O(1); reverse-scan worst case = `kv_pages` single-key lookups = bounded by the node-size cap.
- The scan is already validated by tests:
  - `test_extent_file_backend_unit.py:611-653` `test_v2_trailing_pages_reverse_scan_narrow_cases`: query0..20 with checkpoint at page15 -> boundary=16 (kv_hit_pages=16). Confirms reverse-scan-over-farther-checkpoint semantics.
  - `test_extent_file_backend_unit.py:655-704` `test_v2_trailing_pages_live_shape_storage_hit_positive`: live 2048-page node, mamba key at last page, longer query chain -> `extra_pool_hit_pages[MAMBA]=2048`, kv_hit>0.
  - `test_extent_file_backend_unit.py:706-747` `test_v2_placeholder_keys_never_interpreted_as_all_pages`: placeholder keys routed to TRAILING even if policy defaults to ALL_PAGES.
- Extent backend probes: `3090-dev/p2io_e28_boundary_trace.py` (instrumented exact reverse scan, live node19 3pg + node22 6pg chain).
- **Key nuance**: with the PREFETCH-side transfer built as `keys=["__placeholder__"], hit_policy=TRAILING_PAGES`, the *real* prefetch hit query runs `_sync_trailing_keys` only AFTER the query result — i.e. the boundary computed in `batch_exists_v2` during the *prefetch IO* (`_storage_hit_query` / `prefetch_thread_func`) uses `trailing=1` from the placeholder and already returns `kv_hit_pages` = the folded resume length. (See `hybrid_cache_controller.py:601-637`, `cache_controller.py:1291-1351`.)
- Caveat: `_check_hybrid_prefetch_result` (unified_radix_cache.py:2872-2965) reads only `operation.completed_tokens` + `extra_pool_hit_pages` (from ack), *not* `operation.storage_hit_count`; the folded MAMBA boundary *is* present in `hit_result.kv_hit_pages` (extent backend) and in the ack path, but the all-or-nothing check discards it. (See 3.3.)

### 3.3 all-or-nothing decision point (the code to change)

- `unified_radix_cache.py:2872-2965` `_check_hybrid_prefetch_result(req_id, operation, completed_tokens, hash_value, host_indices, last_host_node_id, anchor_lock_params, prefetch_key) -> bool`:
  - Lines 2903-2911: `pool_transfers` = non-KV-derived transfers; `hit_pages = operation.pool_storage_result.extra_pool_hit_pages`; `pool_hit_pages = [hit_pages.get(t.name,0)]`.
  - Line 2912: `completed_tokens = operation.completed_tokens`.
  - Lines 2916-2920: `all_succeeded = completed_tokens == expected_tokens and all(count == len(transfer.keys) ...)`.
  - Lines 2921-2936: if `pool_transfers and not all_succeeded`: compute `keep_pages`, then `self.storage_existence_cache.invalidate_beyond(PoolName.KV, hash_value, keep_pages)` (line 2934), `append_host_mem_release(host_indices[:completed_tokens], ...)` (2939-2942), dec lock, release prefetch, `self.prefetch_loaded_tokens_by_reqid[req_id] = 0` (2954), `record_storage_prefetch_terminal(req_id, "finalized")` (2960~), return False.
  - **This is the single point where partial mamba -> usable=0 is forced.**
- Caller: `_handle_prefetch_result` `unified_radix_cache.py:2764-2782`: on False logs `_log_restore_disposition(req_id, "RECOMPUTE", ..., "hybrid_discard")` and returns; on True goes to disposition RESTORE/PARTIAL and finalize/insert (lines 2803-2870).
- Return value is `bool` only: usable length is *not* forwarded as a number. The length is embedded in `completed_tokens` (KV IO completed). **To transmit resume_len, either (a) change `_check_hybrid_prefetch_result` to return the usable length, or (b) stash it on the operation/prefetch entry and consume at `_handle_prefetch_result`.** — the return-path is the loosest change surface.

### 3.4 Scheduler consumption chain (storage_hit/usable -> restore decision)

- `scheduler.py:4411`: `req.storage_hit_length = loaded_tokens` where `loaded_tokens = self.tree_cache.pop_prefetch_loaded_tokens(req.rid)` (line 4409) — non-buffer-mode admission consumes the finalize-written marker.
- `scheduler.py:4428-4446`: `req.init_next_round_input(...)` then buffer-mode branch sets `req.host_hit_length = staged_prefetch_tokens(req.rid)` and `req.swa_host_hit_length = staged_prefetch_swa_tokens(...)`; comment explicitly notes mamba needs the same charge via `mamba_host_hit_length`.
- Restore state machine feed: `scheduler.py:3184-3210` `_feed_restore_terminal`: `pop_storage_prefetch_terminal(req.rid)` -> RestoreEvent.FINALIZED / REVOKED_TERMINATED / BACKUP_PENDING / REVOKED_MISS.
- Restore computes: `scheduler.py:3698-3707` `_restore_potential_for(req)` -> `tree_cache.has_restore_potential(req.rid, req.last_host_node, req.host_hit_length, len(req.full_untruncated_fill_ids))` (unified_radix_cache.py:3080-3104).
- The restore *allocation* path (in-cache-mode): `scheduler.py:138-144/1460 (schedule_policy.py)`: `req.needs_host_load_back()` -> `self.tree_cache.init_load_back(InitLoadBackParams(...))` (schedule_policy.py:1438-1445; unified_radix_cache.py:4002-4051, hiradix_cache.py:1475-1495).
- **Where the KV L3->host IO is bounded**: `cache_controller.py:1140-1184` `_page_transfer` iterates `operation.hash_value` in `STORAGE_BATCH_SIZE` chunks, `completed_pages += hit_pages` — the L3->H read stops at `kv_hit_pages`. `operation.hash_value` is truncated at `cache_controller.py:1341-1343` to `hash_value[:storage_hit_count // self.page_size]`; then `prefetch_thread_func` writes `operation.storage_hit_count = storage_hit_count` (line 1344). The host-indices tail is released at `unified_radix_cache.py:3540-3547` (`append_host_mem_release(host_indices[completed_tokens:], ...)`).
- **Consequences for 红线① (no IO of kv_hit_len->resume_len)**: the IO fetch is bounded by `operation.storage_hit_count` (= kv_hit_pages from `batch_exists_v2`) — which *is* already the folded resume boundary for the mamba TRAILING path. That is, the L3->H KV IO already stops at the mamba boundary; the waste in the current code is *host residency* / admission-denied by the all-or-nothing discard (host_indices[:completed_tokens] released; the small released span is the current "搬进去再丢"). Under the patch, `completed_tokens` clamped to `resume_len` at `_handle_prefetch_result` and `_check_hybrid_prefetch_result` is sufficient to avoid any搬/丢. Note the *device* H->D promotion (`init_load_back` + `collect_full_device_indices` unified_tree_core.py:860-876) only walks the matched best node's device values — after the fallback the inserted host chain is `prefetch_key[:completed_tokens]` (unified_radix_cache.py:2803-2809), so device IO is bounded by whatever host node got inserted.
- **Buffer-mode restore path**: `prefetch_from_storage` (unified_radix_cache.py:2462-2683) builds the operation with `comp_xfers`; `_handle_prefetch_result` -> `buffer_pipeline.stage_completed_prefetch` (pipeline.py:696-750); the staged `_StagedPrefetch` gets `num_tokens` = the completed tokens; `prefetch_loaded_tokens_by_reqid[req_id] = num_tokens` (pipeline.py:749). Admission consumes via `schedule_batch` host_hit_length (scheduler.py:4440-4445). The SWA analog (pipeline.py:758-769 `staged_prefetch_swa_tokens`) is what the mamba counterpart must mirror.

### 3.5 Ready Horizon consumption (enable_ready_horizon)

- `ready_horizon.py:233-245` `_is_ready_resident`: `state is RestoreState.READY and staged_tokens > 0 and full_prefix` — the v0 conservative rule: only a FULL-requested-prefix restore is a READY member.
- `ready_horizon.py:480-493` `_req_is_ready_resident(req, tree, buffer_mode)`: same READY + `peek_prefetch_loaded_tokens / staged_prefetch_tokens > 0`.
- `ReadyHorizonView` fields (lines 114-127): `staged_tokens`, `full_prefix`, `host_hit_length`, `staging_eligible`.
- **For resume_len semantics**: `full_prefix` is the field that currently blocks partial restores from being READY. Under the fallback, the M6 definition must become "resume_len KV+Mamba staged" — i.e. `full_prefix` must be re-derived from the resume marker (or a new field `resume_len_tokens`), and the v0 conservative rule dropped for mamba-partial restores. No other READY logic needs changing (the M1/M2 budget, M3 epochs, M4 partition all read `staged_tokens` + `full_prefix`).
- `ready_horizon.py:154-158` `CausalEpochs` snapshot + `epoch_event` (449-464) — unaffected.
- The front-end view builder in scheduler ~scheduler.py:3476 (`staging_eligible=self._restore_potential_for(req)`) is where views are built; `full_prefix` is set there (not in ready_horizon.py).

### 3.6 红线②: invalidate_beyond call sites and existence-belief structure

- `storage_existence_cache.py:78-86` `invalidate_beyond(pool, hashes, keep_pages)`: pops `(pool, h)` for `h in hashes[keep_pages:]` — it removes KV beliefs beyond the keep cut.
- Call sites:
  - `unified_radix_cache.py:2934` (in `_check_hybrid_prefetch_result`) — the all-or-nothing path.
  - `unified_radix_cache.py:3182-3193` `_invalidate_absent_from_hit_query`: `invalidate_beyond(PoolName.KV, chain, keep_pages=operation.storage_hit_count // self.page_size)` — buffer-only mode, rank-synced, drops beliefs beyond the *KV* hit cut. This one is *not* mamba-specific and should stay.
- Structure: `_entries: OrderedDict[(pool, h), None]` (line 44) — flat per-(pool,page-hash) belief set, no per-chain/`beyond` EOV marker beyond per-hash membership. `add/contains/contains_all/covers_all` (49-76) are the belief surfaces.
- Under fallback: the `invalidate_beyond` at line 2934 must **not** run (the KV beyond the mamba boundary is real and remains valid in L3). In the fallback path, either skip it or keep only the *mamba-key* invalidation at the cut. Note the KV belief set is fed at `pipeline.py:734` (buffer delivery) and `unified_radix_cache.py:2803-2809` (cache insert), not by the query; so skipping 2934 simply leaves beliefs intact — the exact requirement.

### 3.7 mamba_branching_seqlen consumption status (question 7)

Already consumed in our branch:

- Producer: `mamba_radix_cache.py:1175-1179` (non-HiCache device match) and `mamba_component.py:170-184` (HiCache device match).
- Consumer: `schedule_policy.py:208-209` `req.mamba_branching_seqlen = match_result.mamba_branching_seqlen`.
- `schedule_batch.py:972` field; `schedule_batch.py:2772-2787` `_mamba_radix_cache_v2_req_prepare_for_extend` uses it to force the mamba track seqlen to the branching point (recompute/track tail within the batch); `schedule_batch.py:1421-1431` forward; `schedule_batch.py:1739` reset.
- `model_runner.py:382-388` (mlx) uses it to pick the aux track len.
- `base_prefix_cache.py:193-207` `MatchResult.mamba_branching_seqlen` doc: "the branching point, which is the longest ...".

**Interpretation for the patch (facts, not assessment)**: it is the *device match* boundary (the last aligned position ≥ the mamba boundary where a mamba state actually exists device-side). It contributes to how req extends/bands mamba tracking in the forward — it is *not* the L3 prefetch/restore boundary. It does not currently solve the partial-L3-mamba problem; it only handles the device-match miss-recompute branching. The patch's `resume_len` (L3 query boundary) is conceptually parallel but data from a different source (batch_exists_v2 folded boundary, not match_result.branching_seqlen).

### 3.8 Node-boundary knowledge on read side (question 1, node boundary / chain continuity)

- Read side knows the full L3 chain: `operation.hash_value` (page-level hash chain, cache_controller.py:1341-1343), `operation.all_hash_values` (base cache_controller.py:275). The chain *is* the position-addressed sequence of page hashes; node boundaries are *not* encoded in the chain (a node is just a run of pages). The mamba tail-key is `node.hash_value[-1]` written per node; existence query is per-page-hash-namespaced. The single-key allocator lookup (extent_allocator.py:76) enables the reverse scan without a new primitive.
- Worst-case reverse scan length: bounded by node-size cap. Node sizes are capped only by kv_len_to_handle / effective_cache_len truncation (unified_radix_cache.py:1100-1145) plus radix page-alignment; no hard maximum token cap is enforced in tree_core insert. In practice nodes are one append chunk (usually ≤ 2048 pages on live benches; the 3090 live node is 2048 pages). Each reverse step is one allocator lookup — cost is acceptable; a mid-chain partial-restore scan is bounded by kv_pages.

## 4. summary

### 4.1 The primary finding (resume_len mechanism already exists)

The read-side nearest-checkpoint mechanism **is already implemented** in `extent_file_backend.batch_exists_v2` TRAILING branch (extent_file_backend.py:660-669), producing `kv_hit_pages` = the folded resume boundary. The write side already writes the node-tail mamba key (mamba_component.py:752-763). The entire fallback problem reduces to:

1. The all-or-nothing discard at `unified_radix_cache.py:2921-2964` (and its `invalidate_beyond`, line 2934) — must be replaced by "use the mamba boundary (already in `kv_hit_pages`) as usable".
2. The usable length must be carried out of `_check_hybrid_prefetch_result` (currently bool-only) into `_handle_prefetch_result` (`completed_tokens` clamp) — and then to `prefetch_loaded_tokens` / staged-tokens marker.
3. Ready Horizon `full_prefix` (ready_horizon.py:241-244, 480-493) must accept resume_len staging as READY.
4. The IO cut already respects the mamba boundary (cache_controller.py:1341-1344 truncates `operation.hash_value` to `storage_hit_count`), so 红线① is satisfiable by clamping `completed_tokens` at `_handle_prefetch_result`.

### 4.2 Exact change-point list (precise files/functions/lines)

| # | File:lines | Function | Change |
|---|---|---|---|
| C1 | unified_radix_cache.py:2872-2965 | `_check_hybrid_prefetch_result` | Replace the all-or-nothing failure block (2921-2964): compute `resume_len_pages = min(kv_hit_pages, mamba_folded_boundary)` from `operation.storage_hit_count`/`extra_pool_hit_pages` (or extend the backend to return the per-pool boundary in the result); do not discard; return the usable length (change signature or stash on operation). |
| C2 | unified_radix_cache.py:2764-2782 | `_handle_prefetch_result` | Consume the resume length; clamp `completed_tokens` (and `hash_value[:completed_tokens]`) to `resume_len`; the insert at 2804-2809 then spans exactly the resumed chain. |
| C3 | unified_radix_cache.py:2934 | `invalidate_beyond` (all-or-nothing leg) | Do NOT run for the fallback path (红线②). Only the `_invalidate_absent_from_hit_query` (3182-3193) leg stays. |
| C4 | unified_radix_cache.py:2855-2858 / 2949-2955 / 2954 | prefetch_loaded_tokens_by_reqid | Set to `resume_len` instead of 0 in the fallback path. |
| C5 | scheduler.py:4411 | admission marker | `storage_hit_length` already consumes `pop_prefetch_loaded_tokens`; with C4 it carries resume_len. No change unless a gap is found. |
| C6 | hybrid_cache_controller.py:601-637 | `_storage_hit_query` | (verification only) confirm `kv_hit_pages` from `batch_exists_v2` already = resume boundary; optionally expose `extra_pool_hit_pages[MAMBA]` (= boundary) to the decision. |
| C7 | ready_horizon.py:233-245 / 480-493 | `_is_ready_resident` / `_req_is_ready_resident` | READY accepts partial (resume_len) staging: replace `full_prefix` v0-conservative with a resume-marker check. (scheduler's view builder ~scheduler.py:3476 sets full_prefix; align there.) |
| C8 | buffer_mode/pipeline.py:696-750 `stage_completed_prefetch`, + `staged_prefetch_swa_tokens` (758-769) | mirror mamba charge analog | If buffer mode also needs mamba-resume staging, add the mamba token field + `staged_prefetch_mamba_tokens`. |
| C9 | (optional, read-only design) extent_file_backend.py:660-669 | TRAILING scan | If a distinct "resume boundary, not trailing window" semantic is wanted per-pool, add a hit_policy variant; otherwise reuse the existing folded boundary. |

### 4.3 红线① IO-truncation point

`cache_controller.py:1140-1184` `_page_transfer` + `prefetch_thread_func` (1291-1351) already bound L3->H KV IO to `operation.storage_hit_count` (= the mamba-folded kv_pages). The currently-discarded-too-late span (`host_indices[:completed_tokens]` released at unified_radix_cache.py:2939-2942) is exactly the `kv_hit_len - resume_len` span; clamping `completed_tokens` at C2 removes the "搬进去再丢" behavior at the admission/finalize level. L3 keeps the intact KV (no deletion). 红线②: skip line 2934.

### 4.4 红线② exact code

`storage_existence_cache.py:78-86` (definition) + 2 call sites (unified_radix_cache.py:2934 and 3191). Only 2934 is mamba-mode; 3191 (`_invalidate_absent_from_hit_query`) is KV-cut-only and stays.

### 4.5 Dependency order

1. C6 (confirm boundary flows) -> 2. C1 (fallback decides + returns resume_len) -> 3. C2 (finalize clamps) -> 4. C4 (marker = resume_len) -> 5. C5 (scheduler admission) -> 6. C7 (Ready Horizon READY). Buffer mode C8 independent of C5/C7 cache-mode paths.

### 4.6 Regression test list

Test anchors (verified paths):

- `test/registered/unit/mem_cache/test_extent_file_backend_unit.py`:
  - `test_v2_trailing_pages_reverse_scan_narrow_cases` (611) — boundary=16 regression (must keep passing; the fallback boundary source).
  - `test_v2_trailing_pages_live_shape_storage_hit_positive` (655).
  - `test_v2_placeholder_keys_never_interpreted_as_all_pages` (706).
  - `test_v2_placeholder_keys_all_pages_explicit_still_all_pages` (749).
  - `test_v2_prefix_semantics` (565), `test_v2_sidecar_component_keys_do_not_share_index` (541), `test_v1_write_then_v2_sidecar_query_hits` (834).
- `test/registered/unit/mem_cache/test_unified_radix_cache_unittest.py` — the core unittest (mamba match + host commit; no lexical TRAILING anchor found, but mamba tests inside).
- `test/registered/unit/mem_cache/test_mamba_unittest.py` — full mamba device/cache loop.
- `test/registered/unit/mem_cache/test_retraction_mamba_backup.py`, `test_mamba_path_state_cap.py`, `test_mamba_donated_alloc_ratio.py`, `test_mamba_state_transfer_buffers.py`, `test_unified_mamba_views.py`.
- `test/registered/unit/mem_cache/test_hicache_staged_write_back_dispatch.py`, `test_session_unified_radix_cache.py`, `test_unified_radix_hicache_dispatch.py`, `test_hicache_dcp_host_pool.py`.
- `3090-dev/` desk probes to re-run for the new policy:
  - `p2io_e28_boundary_trace.py` (boundary calc trace) — will change if C9 touches the scan.
  - `p2io_e7p_three_cases.py`, `p2io_e7p_recompute_quant.py` (effective_cache_ratio validation — the acceptance metric).
  - `p2io_e24_mamba_probe.py`, `p2io_e25_narrow_cases.py`, `p2io_e25_live_shape.py` (behavior probes).
- `3090-dev/test_hicache_restore.py`, `test_hicache_restore_scheduler_feed.py`, `test_ready_horizon_unit.py`, `test_prefetch_budget_split_unit.py` — the restore state-machine + Ready Horizon unit anchors; C7 must keep them green.

### 4.7 Open design questions (non-blocking, for the coder/architect)

None found that require new primitives. Unresolved nuances:

1. `extra_pool_hit_pages[MAMBA]` in the ack path (unified_radix_cache.py:3528-3532) equals the *fetched* trailing pages, not the folded boundary; the true boundary is `operation.storage_hit_count` (= kv_hit_pages) from the query. C1 must read the right field per-mode.
2. Buffer mode + mamba (was never wired for `mamba_host_hit_length` — scheduler.py:4439 comment; C8 only if buffer mode is in scope for the patch).
3. `full_kv_hit_length`/`mamba_branching_seqlen` device-match relationship to L3 resume (frozen ruling says not in scope; only note it exists).

## 5. followups

1. (C1) `unified_radix_cache.py:2872-2965` — redesign `_check_hybrid_prefetch_result` to return `(success: bool, resume_len: int)` and drop the all-or-nothing discard + `invalidate_beyond`.
2. (C2) `unified_radix_cache.py:2764-2782` — clamp `completed_tokens`/`hash_value` to resume_len at finalize.
3. (C4) `unified_radix_cache.py:2954` — set `prefetch_loaded_tokens_by_reqid[req_id] = resume_len` in the fallback leg.
4. (C7) `ready_horizon.py:233-245` + scheduler view builder (~scheduler.py:3476) — READY accepts resume_len staging (replace v0 full_prefix).
5. (C6, verification) `hybrid_cache_controller.py:601-637` — instrument/log that `kv_hit_pages` = the mamba boundary in the live M4 shape; confirm the boundary carries through the ack path.
6. (C8, gate on scope) `buffer_mode/pipeline.py:696-750` + scheduler.py:4439 — decide whether buffer mode needs the mamba-resume staging charge.
7. (C9, optional) `extent_file_backend.py:660-669` — if the coder wants a distinct semantic than the trailing-window scan, add a `RESUME_NEAREST_CHECKPOINT` policy; else reuse.
8. External-scout recommendation: for `issue #36935` upstream sync (agentic traffic KV-present/mamba-missing clamp) — but this is local-only; WebFetch ban means external-scout is the only channel. Recommended invocation: `external-scout: fetch sglang issue 36935 + latest upstream mamba_component.py / _check_hybrid_prefetch_result diff for any upstream partial-restore work`.

## 6. open_issues

- None blocking. Layered-existence verdicts:
  - "`batch_exists_v2` TRAILING reverse-scan returns the nearest mamba node-tail boundary" — confirmed (extent_file_backend.py:660-669 + two dedicated tests). layering: code (verified), test (verified), live probe (3090-dev/e28_boundary_trace.py, code-only).
  - "all-or-nothing discard is the sole gate forcing usable=0 on partial mamba" — confirmed (unified_radix_cache.py:2916-2964; the ack/IO path already clamps KV IO to the folded boundary). layers: code (verified), runtime behavior (frozen ledger e7p evidence — external evidence layer).
  - "`invalidate_beyond` must not run in the fallback" — confirmed from code semantics (storage_existence_cache.py:78-86, call-site 2934) but the behavioral consequence is not yet established (no fallback exists yet). Reported as "not yet established", needing the patch's test.
  - "IO already truncated at resume_len by storage_hit_count" — confirmed in code (cache_controller.py:1341-1344), not yet verified at runtime (would need the patch + metrics; do not conflate).
- The two live "no references" searches with scopes: `invalidate_beyond` only in 2 files (unified_radix_cache.py + storage_existence_cache.py, searched python/); `mamba_branching_seqlen` consumers enumerated (schedule_policy.py:208-209, schedule_batch.py:2772-2787, model_runner.py:382-388, streaming_session.py:65-121, mamba_radix_cache.py:1175-1206, mamba_component.py:170-184).
- Concern to carry into the patch: `_check_hybrid_prefetch_result` is cross-rank `@rank_consensus`-adjacent (same_params/same_results); changing the return type must keep all ranks agreeing on `resume_len` (already guaranteed because it comes from the rank-synced `storage_hit_count`).