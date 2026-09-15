# E1 — L3 Extent Backend architecture freeze

```yaml
schema: phase2-hicache-e1-freeze-1
artifact_id: E1-EXTENT-L3-ARCHITECTURE-FREEZE-20260912
task_id: PHASE2-E1-20260912
role: architect
mode: READ_ONLY (report-only; no product/test/launch/git change)
repo: /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt
head: 4f41f5bab562b99562f30c67540eb05344d13637
branch: 3060-12g-qwen35-4b
classification: KNOWN-PATTERN (EXEMPT-eligible: restores an already-in-tree backend by deployment selection; no new mechanism)
inputs:
  - E0-BACKEND-IDENTITY-AUDIT-20260912 (sha256 bf126e3899078954046c605fa4e64007f889f13ff6f63e4725ff11411da7946d)
  - launch-r112.sh (frozen profile, sha256 2259d406f8f2239289d799bfd7bffd6401dedd101ed90225ddc05508cf8caaa3)
  - P2A-LIVE-COLLECTION-20260912-R129 (sha256 f3e32ee54138e47ecf210fc02ea0d04826509a0de9f1841e2174e170526db17a)
status: done
```

## 0. Scope and method

Read-only architecture freeze. I re-verified the E0 sha256-bound facts at the
pinned HEAD and every `file:line` below; I did not edit product code, tests,
launch scripts, or git. The single write is this report. Observations are
separated from assumptions/proposals below; no performance claim is made
(E4 measures).

## 1. Frozen target architecture (L3)

```
logical key
  --[_storage_key / _component_key]-->  suffixed storage key
  --[ExtentAllocator._index dict]-->    RAM-authoritative metadata index (online truth)
  --[ExtentRef{extent_id, offset, length, generation}]-->
  --[slot s occupies file bytes [s*extent_size, (s+1)*extent_size)]-->
  --[preallocated sparse file hicache.data{config_suffix}]-->
  --[preadv/pwritev exact merged ranges = block/batch IO]-->
```

- `ExtentRef` is the frozen 4-field struct: `extent_id`, `offset`, `length`,
  `generation` (`extent_allocator.py:99-103`).
- Slot geometry and the file-layout contract are stated in the allocator
  docstring (`extent_allocator.py:6-22`); the allocator "never touches the
  filesystem and holds no lock" — the backend serializes under one index lock
  (`extent_allocator.py:12-15`).
- Online metadata authority is RAM only. The filesystem namespace is never used
  as an online metadata DB: no `os.scandir`/`os.listdir` exists anywhere in the
  extent package (verified: `grep -rn` returns NONE).
- One data file per rank/config suffix (`extent_file_backend.py:344-347`),
  preallocated sparse via `os.ftruncate(self._fd, self._file_size)`
  (`extent_file_backend.py:370`).

## 2. MUST / MUST-NOT properties → providing symbol, or GAP id

| # | Property | Kind | Providing symbol (file:line) | Status |
| - | --- | --- | --- | --- |
| M1 | v1 and v2 keys agree (write side cannot silently disagree with query side) | MUST | `_storage_key` `extent_file_backend.py:383-384`; `_component_key` `:386-389` | met |
| M2 | RAM index is the online metadata authority | MUST | `ExtentAllocator._index` `extent_allocator.py:129`; `lookup` `:138-147` | met |
| M3 | O(1) per-key lookup | MUST | `self._index.get(key)` `extent_allocator.py:139` | met |
| M4 | Batch lookup (no per-key syscall) | MUST | `snapshot` `:149-150`, `verify` `:152-163`; `present()` loop `extent_file_backend.py:777-783` | met |
| M5 | Generation-aware validity after slot reuse | MUST | gen re-check `extent_allocator.py:142-146`; plan gen `:209`; `_drop_slot` bump `:303` | met |
| M6 | Write-ACK atomic visibility (ACK = pwrite success + index registration) | MUST | two-phase `plan` `:172-213` / `commit` `:215-240`; lock spans plan→pwrite→commit `extent_file_backend.py:1136-1160`, `:625-667`, docstring `:17-22` | met |
| M7 | Batched/block IO over preallocated extent file | MUST | `ftruncate` `:370`; `pwritev` `:1267-1298`; `preadv` `:1216-1265`; exact-range merge `:174-192` | met |
| M8 | Lazy GC, bounded growth | MUST | `_gc_evict` `:1164-1187`; `evict_slot_lru` `extent_allocator.py:244-256`; circular reuse `:193-211` | met |
| M9 | Fail-closed on malformed/stale (miss, never serve wrong bytes) | MUST | oversized page→None `extent_allocator.py:190-191`; batch > file refused `:196-198`; read size mismatch→None `extent_file_backend.py:404-409`, `:456-461`; short pread→miss `:1090-1096` | met |
| M10 | Engine dispatch is backend-generic (extent is a drop-in selection) | MUST | `server_args.py:2794-2807`; `backend_factory.py:161-162,201-205`; `cache_controller.py:645-648`; `hybrid_cache_controller.py:890,914,922` | met |
| N1 | MUST-NOT enumerate the whole directory in the query path | MUST-NOT | grep: no `os.scandir`/`os.listdir` in extent package; `present()` dict lookup `extent_file_backend.py:777-783` | met |
| N2 | MUST-NOT use one small file per KV page | MUST-NOT | single file `hicache.data{config_suffix}` `:344-347` | met |
| N3 | MUST-NOT call scandir per query | MUST-NOT | same as N1 | met |
| N4 | MUST-NOT grow the file without limit | MUST-NOT | circular reuse + generation bump `extent_allocator.py:193-211,288-333`; `file_size >= extent_size` guard `extent_file_backend.py:314-317` | met |
| N5 | MUST-NOT rely on on-disk metadata persistence (frozen contract) | MUST-NOT | docstring "restart starts cold -- no metadata persistence" `:17-20` | met (G1) |

GAP mapping (from E0; re-verified here):

| Gap | Where it binds to the properties | Evidence |
| --- | --- | --- |
| G1 no metadata persistence / restart rebuild | N5; limits N/A recovery after restart (data bytes survive but are unreachable) | `extent_file_backend.py:17-20`; `test_crash_reopen_all_cold` `test_extent_file_backend_unit.py:461-488` |
| G2 defaults must be set explicitly | M7/M8 sizing; default extent 64 MiB / file 64 GiB, storage_dir `/tmp/hicache` | `:60-62`, `:281-287` |
| G3 `get_stats()` returns `None` | M10 observability | `:1197-1202`; raw counters only via `stats_snapshot()` `:1204-1207` |
| G4 one data file per rank/suffix (no cross-rank sharing) | M7 | `:270-279`, `:344-347` |
| G5 no on-disk integrity check | M9 (detected at read mismatch, not proactively) | `extent_allocator.py:138-147`; `extent_file_backend.py:404-409` |

## 3. Selection / dispatch delta (minimal)

**Frozen delta:** one new launch script that keeps the R112 argv identical but
selects `--hicache-storage-backend extent` and sets the `SGLANG_HICACHE_EXTENT_BACKEND_*`
sizing vars. No engine, factory, or branch code change is required.

Read-only evidence that `extent` is a data-driven drop-in:

- `server_args.py:2794-2807` includes `"extent"` in the
  `--hicache-storage-backend` choices.
- `backend_factory.py:201-205` registers `"extent"` →
  `...storage.extent.extent_file_backend.ExtentFileBackend`.
- `backend_factory.py:161-162` constructs `file|sim|extent` as
  `backend_class(storage_config)` (no `file_path` argument).
- `cache_controller.py:645-648` builds whichever backend name is configured via
  `StorageBackendFactory.create_backend(...)` and registers the same host pool.
- Query path is surface-generic: `batch_exists` `hybrid_cache_controller.py:890`,
  `batch_exists_v2` `:914`, no-transfers `batch_exists` `:922`.
- Write/read surfaces are generic: `batch_set_v1` `cache_controller.py:1383`,
  `batch_get_v1` `:1103`, `batch_get_v2` `:1219`,
  `batch_set_v2` `hybrid_cache_controller.py:1094`, `batch_get_v2` `:1059`.
- Honest nuance: the engine does contain one backend-type branch
  (`storage_backend_type == "mooncake"`, `hybrid_cache_controller.py:1196`), but
  it does not touch the `file`/`extent` dispatch. No `file`-vs-`extent` branch
  exists (`grep` for `HiCacheFile` in `managers/`, `hybrid_cache/`,
  `unified_radix_cache.py` → NONE).

Observed (not modified by me): an E2 script already exists at
`/mnt/data/neuron/sglang-3090-r112-20260911/launch-e-20260912.sh`
(sha256 `0c15c1c420d8c1b9a9a3769305e1910c01b6400dafd36c19edbb7a7eb0462419`).
Its L3 lines match the frozen config in §4 exactly. The frozen R112 script and
the R129 evidence directory `.../l3/` (133 G) are untouched.

## 4. Frozen expected config values for E2

| Variable | Frozen value | Source/effect |
| --- | --- | --- |
| `SGLANG_HICACHE_EXTENT_BACKEND_STORAGE_DIR` | `$D/l3-extent` — a NEW dir; MUST-NOT reuse the R129 `$D/l3` (133 G, 3.09 M-file legacy namespace) | consumed at `extent_file_backend.py:281-287` |
| `SGLANG_HICACHE_EXTENT_BACKEND_FILE_SIZE` | `256G` | `:302-309`; overrides `_DEFAULT_FILE_SIZE` `:62` |
| `SGLANG_HICACHE_EXTENT_BACKEND_EXTENT_SIZE` | `64M` | `:294-301`; overrides `_DEFAULT_EXTENT_SIZE` `:60` |
| `SGLANG_HICACHE_EXTENT_BACKEND_MAX_SIZE` | `200G` | `:320-322`; drives `_gc_evict` watermark `:1164-1187` |
| `SGLANG_HICACHE_EXTENT_BACKEND_MIN_FREE_SPACE` | `20G` | `:323-327`; free-space watermark `:1179-1182` |
| `SGLANG_HICACHE_EXTENT_BACKEND_DIRECT_IO` | leave unset (default `False`); buffered IO first slice | env default `environ.py:708`; warning path `:333-342` |

Config semantics that E2 must respect:

- **File-backend env vars are irrelevant to extent.** `extent_file_backend.py`
  reads only `SGLANG_HICACHE_EXTENT_BACKEND_*` (grep for
  `SGLANG_HICACHE_FILE_BACKEND` in the extent backend → NONE). `_parse_size_to_bytes`
  is imported from the file package (`:54`) but is a pure string→bytes helper
  (`lru_file_evictor.py:39-51`), not a FileBackend dependency.
- **Env precedence:** `_config_value(extra, key, env_field)` returns
  `extra.get(key)` when present, else the env value (`:240-243`), i.e.
  **`extra_config` > env**. The E2 `--hicache-storage-backend-extra-config`
  contains only `hicache_storage_pass_prefix_keys`, which extent ignores, so the
  env values above take effect.
- Derived (config arithmetic, not a perf claim): with 64 MiB extents and a
  256 G preallocated file, `num_slots = file_size // extent_size = 4096`
  (`:371`); the `file_size >= extent_size` guard is `:314-317`.

## 5. Correctness invariants and E3 oracles

E3 must run these against the new deployment / backend (existing unit coverage
is cited; E3 adds the live and static checks where noted).

| # | Invariant | Oracle | Existing test |
| - | --- | --- | --- |
| I1 | v1 write then v2 query hits (engine flow) | `batch_set` then `batch_exists_v2` returns full KV prefix; cross-check `_storage_hit_query` via real controller | `test_v1_write_then_v2_query_hits` `:816-832`, `:1052`; `test_same_span_write_then_query_storage_hit_4` `:2010-2031` |
| I2 | Sidecar component keys isolated from KV index | `.mamba` component keys present, bare KV keys absent | `_component_key` `extent_file_backend.py:386-389`; `test_v2_sidecar_component_keys_do_not_share_index` `:541-563` |
| I3 | Generation invalidation after slot reuse | stale `ExtentRef` fails `lookup`/`verify` after `_drop_slot`; refs captured before wrap miss | `lookup` `extent_allocator.py:142-146`; `test_generation_invalidation_after_slot_reuse` `:111-127`; `test_circular_wrap_drops_oldest_slot_and_bumps_generation` `:93-109` |
| I4 | Restart-cold semantics (frozen, not a bug) | reopen same dir → `exists`/`get` all miss, `preads==0`, new writes land in same file | `test_crash_reopen_all_cold` `:461-488`; docstring `extent_file_backend.py:17-20` |
| I5 | No-scandir assertion (static) | `grep -rn "os.scandir\|os.listdir" python/sglang/srt/mem_cache/storage/extent/` returns NONE | **no existing unit test**; E3 must assert this statically (I verified NONE at HEAD) |
| I6 | Factory constructs the real backend for name `extent` | `type(backend).__name__ == "ExtentFileBackend"` and functional `set/exists` | `test_factory_creates_real_extent_backend` `:1913-1938` |
| I7 | `get_stats()` obeys engine contract (`None`), counters under `stats_snapshot()` | `assertIsNone(get_stats())`; required counter keys present | `test_get_stats_matches_engine_contract` `:501-509` |

The suite is CPU-registered (`register_cpu_ci(est_time=20, suite="base-a-test-cpu")`,
`test_extent_file_backend_unit.py:21-23`), so E3 can re-run it without a GPU.

## 6. Open decisions and explicit non-goals

- **G1 restart-rebuild is NOT added by E2.** Providing metadata persistence /
  restart rebuild would be a non-exempt product change (new persistent index
  format and recovery semantics) requiring the full Pattern Intake + Novel
  Mechanism gates. Frozen decision: E2 keeps restart-cold semantics; the data
  bytes remain but the index starts empty (correct under pure cache semantics).
  Owner of the decision to change this is the user/orchestrator, not E1/E2.
- **G3 observability** is resolved without engine changes: read raw counters via
  a probe that calls `stats_snapshot()` (`extent_file_backend.py:1204-1207`).
  No change to `get_stats()` (it must stay `None`, `:1197-1202`).
- **Non-goals:** no legacy `HiCacheFile` optimization; no engine/factory/dispatch
  edits; no edit to frozen `launch-r112.sh`; no git operations; no performance
  claims (E4 measures); no change to the R129 `$D/l3` evidence directory.
- **Risks/uncertainty:** G5 (no on-disk integrity check) means corruption is
  detected only at read (size mismatch/short pread → miss), which is fail-closed
  but not proactive. G4 means multi-rank topologies would need one file per rank;
  the frozen TP=1 profile is unaffected. Both are accepted for this deployment.

## 7. Evidence manifest (content sha256, at HEAD)

| Evidence | sha256 |
| --- | --- |
| `python/sglang/srt/mem_cache/storage/extent/extent_file_backend.py` | `bef390f13e4479aae4016883ea45e713dc24f008997effed4aca7c4750a09600` |
| `python/sglang/srt/mem_cache/storage/extent/extent_allocator.py` | `afec684803956cbcce637aa1896839a687c3c57e1d29f3dfbab4ae2eb68d339b` |
| `python/sglang/srt/mem_cache/storage/backend_factory.py` | `2b79fb5bd3cc0cb76914735952ff34ff1edb7a02735ad2c69c9a6ef08eba2a77` |
| `python/sglang/srt/mem_cache/hicache_storage.py` (legacy `HiCacheFile`) | `7c5c7331eda1ded25a25bb5d9938aa76311651b16025f5b8743a17318ff1d1d7` |
| `python/sglang/srt/managers/cache_controller.py` | `a41e623a2d6e462720d6584af992da290ba54e0cb3766df794117b87678b656f` |
| `python/sglang/srt/mem_cache/hybrid_cache/hybrid_cache_controller.py` | `64e933f490884b74f0d38655a8f5a75157bab530dd0ea0688323c9780f1ce4d5` |
| `python/sglang/srt/server_args.py` | `5ec3740fdc61e2a977a5a1f01325070e68a4d2abedb9d4f9ecaf85f1a78ca03d` |
| `python/sglang/srt/environ.py` | `d01a4984728e82e8a9524da411f3f4b8cb09e321018a7cdcfa47b03b92124098` |
| `python/sglang/srt/mem_cache/storage/file/lru_file_evictor.py` | `9e590e144c1169d463102e9aa147432cf5fa9108f1f8936de1184903c79a1330` |
| `test/registered/unit/mem_cache/test_extent_file_backend_unit.py` | `59a750d768ef8c807443987fdaaad0c5e04c5c52d8f459d57692bbf00089928b` |
| `launch-r112.sh` (frozen profile, `/mnt/data`, outside git) | `2259d406f8f2239289d799bfd7bffd6401dedd101ed90225ddc05508cf8caaa3` |
| `launch-e-20260912.sh` (E2 script observed, `/mnt/data`, outside git) | `0c15c1c420d8c1b9a9a3769305e1910c01b6400dafd36c19edbb7a7eb0462419` |
| `E0-BACKEND-IDENTITY-AUDIT-20260912.md` | `bf126e3899078954046c605fa4e64007f889f13ff6f63e4725ff11411da7946d` |
| `P2A-LIVE-COLLECTION-20260912-R129.md` | `f3e32ee54138e47ecf210fc02ea0d04826509a0de9f1841e2174e170526db17a` |

## 8. Verification honesty — facts, assumptions, not-verified

Observed facts (verified at HEAD unless noted): all `file:line` citations above;
all sha256 values in §7; `grep` no-scandir in the extent package; the single
mooncake backend-type branch; the R112 launch profile hash and its
`file`/`$D/l3` selection; R129 Q3 p50 17.777 s as written in the R129 report.

Assumptions / proposals: the E4 expectation that removing the scandir mechanism
drops query latency is a hypothesis for E4 to measure, not a claim here; the
4096-slot arithmetic is config-derived.

Could NOT verify here: (a) `launch-r112.sh` and `launch-e-20260912.sh` are not in
the git tree (they live under `/mnt/data`), so they are hash-bound but not
HEAD-bound; (b) the E0 file count "3,090,193 files" — I re-verified only
`du -sh l3` = 133 G, not a full directory re-count (not re-derived to avoid
needless heavy I/O); (c) R129 raw per-query samples were not re-reduced, only
the frozen report figures were read; (d) no live server run was performed, so
all runtime behavior is asserted from source/unit tests, not observed live.
