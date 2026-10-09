# p2io-coder-e27.md — UnifiedRadix logical prefix -> storage hash-chain

## Status
done

## Artifacts
- `test/registered/unit/mem_cache/test_storage_hash_chain_invariant.py` (NEW, untracked): permanent unit test for the storage hash-chain invariant. Guards that the query-side rebuilt hash chain equals the write-side `node.hash_value` chain page-by-page, across the STORAGE_BATCH_SIZE(1024) boundary and across a radix split, for 2048/4096-page prefixes. Uses the e7k oracle (`p2io_refhash`, native-verified 20/20) patched over `get_native_hash` so the test is deterministic on CPU-only CI (no C++ toolchain needed).
- No production code changed this epoch. Zero edits to `python/`. The `M` files in `git status` are prior-epoch (e25/e26) instrumentation already in the working tree (t38c probes in cache_controller/scheduler/hybrid_cache/extent/unified_tree_core/etc.) — not mine.

## Evidence (real commands + output)

### 1. Page-by-page compare: write chain vs query chain (the coordinator's directive)
Run `3090-dev/p2io_e27_chain_compare.py` (real CPU UnifiedRadixCache, page_size=1, storage enabled):
- **Single 2048-page node**: `FIRST DIVERGENCE page=None` (all 2048 equal). page 1023/1024/1025 write==query. recomputed page1024 from write seed == from query seed == `ca65bc61...`.
- **Split scenario (500-share split)**: `split path chain vs fresh query: FIRST DIVERGENCE = None` — split hash redistribution is correct.
- **Growth scenario (1024->2048)**: probe showed `FIRST DIVERGENCE = 1024` BUT this is a **probe artifact** (self-inconsistent seed: it used page-2047's hash `c2dc411a` to seed a continuation starting at page 1024).

### 2. The artifact proof (faithful live model)
The real scheduler anchors at the deepest matched node and seeds the continuation from **that anchor's last hash**. Faithful model (anchor=node34, seed=node34 last hash = page-1023 hash, continuation=node35 content):
- `query_chain == node35.hash_value`, `FIRST DIVERGENCE = None`.
- `node35.hash_value == oracle(g_toks[1024:], node34_last)` = True.
The growth probe's 1024-divergence was my probe using node35's page-2047 hash as seed for a 1024-continuation — self-inconsistent, not a real bug.

### 3. Production native hash end-to-end (NOT oracle)
With the compiled native `hicache_hash_cpp.so` loaded, real `get_hash_str` over a real 4096-page tree node:
- `PRODUCTION NATIVE: first divergence page = None` (all 4096 equal)
- page1023 write==query `ea2f1443...`; page1024 write==query `ca65bc61...`
Live growth shape with native hash (anchor=node34, seed=node34.last_hash `24defa4c...`, continuation=node35 content): `FIRST DIVERGENCE = None`, ALL EQUAL.

### 4. No cross-batch seed mechanism exists (code reading)
- `cache_controller.py::_storage_hit_query` (1298-1314): computes `page_hashes = self.get_hash_str(tokens_to_fetch, last_hash, page_size)` ONCE over the entire suffix; the 1024-batch loop only windows the backend scan (`batch_exists`), never re-seeds.
- `_page_backup` (1385-1405): `operation.hash_value` is precomputed `node.hash_value`; batching only slices it.
=> A "cross-batch seed reset" (the coordinator's case a hypothesis) is **structurally impossible** in the chain generation. The chained SHA256 is position-continuous; page 1024's seed is page 1023's hash by construction.

### 5. TDD RED->GREEN
- RED probe: simulated cross-batch seed-reset (batch2 seeded from stale `deadbeef...` instead of page-1023 hash) diverges at exactly page 1024 (correct `ca65bc61...` vs buggy `7d51e39c...`), 0..1023 equal. The invariant test WOULD be red at page 1024 under such a bug.
- GREEN: production code never applies such a reset; all 3 new tests pass.

### 6. Test gate
```
pytest registered/unit/mem_cache/test_storage_hash_chain_invariant.py registered/unit/mem_cache/test_mem_cache_utils.py
=> 39 passed, 15 warnings, 26 subtests passed (3 new + 36 existing)
```
Full mem_cache dir (3038 collected) has 500 failures + 1389 passed + 1152 skipped — the 500 are a **pre-existing environment issue**: `ValueError: Not enough host memory available. Requesting 0.10 GB but only have -2.26 GB free` in `pool_host/base.py:177` (`host_memory_budget_bytes()` returns negative on this memory-contended 15GB box). Reproduces in a fresh process that never imports my test file => definitively unrelated to my change.

## Summary
- The storage hash-chain (write `node.hash_value` vs query rebuilt `get_hash_str`) is **provably identical** on every page for all live shapes: single 2048-node, 4096 cross-batch, radix split, growth 1024->2048, live continuation-from-anchor. No divergence at 1024/1027.
- The only "divergence at 1024" found was a probe artifact (wrong seed). There is no cross-batch seed-reset mechanism in `_storage_hit_query` or `_page_backup` — the chain is position-continuous by construction.
- Therefore `storage_hit=0` is NOT a chain-generation bug in the UnifiedRadix layer either. The remaining live-side suspects: the backend scans ONLY the freshly reconstructed suffix `keys` (both `batch_exists`/`batch_exists_v2` IGNORE `prefix_keys`), so the storage hit is capped at what `get_hash_str(new_input_tokens, anchor.last_hash)` finds — the query-span/anchor-selection mismatch (prefetch `new_input_tokens` slicing, or the anchor not covering the written pages) is the only layer left.
- Permanent test added guarding the invariant (4096 pages + cross-1024 batch + split).

## Followups
1. The coordinator's "first divergence at ~1024/1027" hypothesis is DISPROVEN for chain generation. The next investigation must be the query-span/anchor-selection layer: which `new_input_tokens` + which `last_hash`/`prefix_keys` the scheduler actually passes to `prefetch_from_storage`, and what `batch_exists` scans (suffix-only, prefix_keys ignored). Suggest comparing the scheduler's `matched_len`/`match_end` slice vs the storage-persisted page range.
2. Full gate (75+ tests) cannot be run to green on this box: the host-memory-budget ValueError blocks 500 mem_cache tests (machine memory contention). Needs either a less loaded runner, a memory-budget mock/override in those tests, or the orchestrator's decision.

## Open Issues
- `host_memory_budget_bytes()` (pool_host/base.py:177) returns negative on this machine (6GB used / 8GB avail, 15GB total) — pre-existing, blocks ~500 unit tests. Not caused by this epoch.
- venv lacks pytest/ninja; system lacks `Python.h` and `openssl/sha.h` and a `libcrypto.so` symlink. Worked around in user-space (see below) without touching repo or system.
- Native hash C++ build environment: must set `PATH`(venv bin for ninja), `CPATH`(venv python3.12 include + node openssl include), `LIBRARY_PATH`(/home/charles/tmp-libcrypto + /usr/lib/x86_64-linux-gnu), `PYTHONPATH`(repo/python). Scratch symlink `/home/charles/tmp-libcrypto/libcrypto.so -> libcrypto.so.3` created (user-space, removable).
- Instrumentation (t38c probes) must NOT be deleted per the e27 constraint — left intact.
