# E0 — L3 backend identity audit (read-only)

```yaml
schema: phase2-hicache-e0-audit-1
artifact_id: E0-BACKEND-IDENTITY-AUDIT-20260912
task_id: PHASE2-E0-20260912
role: orchestrator (read-only direct audit)
repo: /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt
head: 4f41f5bab562b99562f30c67540eb05344d13637
branch: 3060-12g-qwen35-4b
mode: READ_ONLY (no product code changed, no server started, no GPU taken)
classification: KNOWN-PATTERN (extent backend already exists in-tree)
```

## 0. Authorization and method

Read-only source/log/fs inspection only, per the user redirect that stops
optimizing the legacy FileBackend and targets the extent + RAM-index L3. No
filesystem mutation, no server launch, no GPU lock. All facts below cite
`file:line` at the pinned HEAD; each cited file is bound by its content
sha256 in section 7.

## 1. Decision

The R129 fallback is fully explained by a **deployment/selection** fact, not a
missing capability: the launch profile selects `--hicache-storage-backend file`,
which resolves to the legacy `HiCacheFile` one-small-file-per-key backend with
its metadata cache disabled by default. The extent backend
(`ExtentFileBackend`) already exists in-tree, is registered as `extent`, and is
constructed alongside `file`; nothing in the engine dispatch chain is
backend-specific, so switching the deployment to `extent` (plus its config)
restores the RAM-authoritative-index architecture without touching the query
path. No product-code change is required to answer the user's Q1/Q2/Q3; the
minimal E2 action is a deployment/selection change and is therefore a
KNOWN-PATTERN / non-novel change (section 6).

## 2. Q1 — Why R129 fell back to the 3M-small-file path (CONFIRMED)

Complete selection chain, all verified at HEAD:

1. Launch profile argv contains `--hicache-storage-backend file`
   (`launch-r112.sh`). Live proof in
   `/mnt/data/neuron/sglang-3090-r112-20260911/sglang-server-p2a.log`:
   `'hicache_storage_backend': 'file'`, `'page_size': 1`, and
   `[2026-09-12 08:05:30] Creating storage backend 'file'
   (sglang.srt.mem_cache.hicache_storage.HiCacheFile)`.
2. `server_args.py:2790` `--hicache-storage-backend` choices include
   `file, extent, sim, mooncake, hf3fs, nixl, aibrix`.
3. `backend_factory.py:197-199` registers `"file" ->
   sglang.srt.mem_cache.hicache_storage.HiCacheFile`.
   `backend_factory.py:161-162` constructs `file`/`sim`/`extent` as
   `backend_class(storage_config)` (no `file_path`).
4. `cache_controller.py:642-648` calls
   `StorageBackendFactory.create_backend(storage_backend, self.storage_config,
   self.storage_host_pool)` — the backend choice is data-driven; the engine does
   not hardcode FileBackend anywhere.
5. `HiCacheFile.__init__` sets `self.file_path =
   envs.SGLANG_HICACHE_FILE_BACKEND_STORAGE_DIR.get() or file_path`
   (`hicache_storage.py:373`); the launcher sets
   `SGLANG_HICACHE_FILE_BACKEND_STORAGE_DIR="$D/l3"` (`launch-r112.sh`), i.e.
   `/mnt/data/neuron/sglang-3090-r112-20260911/l3`.
6. **Root cause of the 17.8 s/query:** `HiCacheFile` builds its metadata cache
   only when `SGLANG_HICACHE_FILE_BACKEND_ENABLE_METADATA_CACHE` is true
   (`environ.py:697`, default **False**; not set by the launcher). With
   `metadata_cache=None` (`hicache_storage.py:423`),
   `_collect_existing_component_keys` (`hicache_storage.py:589-606`) takes the
   `os.scandir(self.file_path)` branch and enumerates the whole L3 directory on
   **every** query.
7. That directory is a one-`.bin`-file-per-key namespace: measured
   **3,314,758 files / 133 GB** (live `ls -1 | wc -l` + `du -sh` on
   `/mnt/data/neuron/sglang-3090-r112-20260911/l3` after R129/R125/R126;
   sample names confirm `<hash>_-mnt-data-models-qwen35-gptq_0_1.bin`).
   (An earlier note recorded 3,090,193; that was a stale/earlier count — the
   live re-measured value is 3,314,758 and is the figure this report uses.)
   `page_size = 1` (token-level keys) is the multiplier: every token page is
   its own file.
8. R129 collection measured the consequence: Q3 (storage query) n=27,
   p50 **17.777 s**, p99 22.278 s, `backend_lookup` ≈100% of stage. This is a
   **legacy FileBackend scalability failure**, not a production baseline and
   not a Ready-Horizon defect.

Corroboration already frozen: 27 queries x 17.777 s ≈ 480 s inside the single
prefetch thread versus the 514 s total run.

## 3. Q2 — What ExtentFileBackend still lacks for production L3

Surface assessment against the `HiCacheStorage` contract and the frozen target
architecture (logical key -> RAM index -> `ExtentRef` -> preallocated extent
file -> block/batch IO). Verified at HEAD:

### 3.1 Present and correct (no gap)

- **Full storage surface implemented.**
  `get/set/exists` (`extent_file_backend.py:393+`),
  `batch_get/batch_set/batch_exists`, `batch_get_v1/batch_set_v1`,
  `batch_get_v2/batch_set_v2/batch_exists_v2` (`:745-893`),
  `clear` (`:1189`), `get_stats` (`:1202`), `stats_snapshot` (`:1204`),
  `close` (`:1209`), `_gc_evict` (`:1164`).
- **RAM-authoritative index, no scandir.** `batch_exists_v2` resolves every key
  through `self._allocator.lookup(key)` (`:777-778`); the allocator's `lookup`
  is a dict probe + generation check (`extent_allocator.py:138-147`). There is
  **no `os.scandir`/`os.listdir`** anywhere in the extent backend or allocator
  (grep-verified). The filesystem namespace is never used as an online metadata
  DB.
- **O(1)/O(log N) lookup + batch lookup.** dict lookup per key;
  `snapshot`/`verify` batch helpers (`extent_allocator.py:149-163`).
- **Generation-aware validity.** Slot reuse/cursor-wrap/`_drop_slot` bumps the
  slot generation (`extent_allocator.py:288-333`); a captured `ExtentRef` then
  fails `lookup`'s generation re-check (miss). Write-ACK atomic visibility is
  by construction: `plan` is pure and `commit` runs only after pwrite
  (`extent_allocator.py:17-22,172-240`).
- **Batched/block IO.** Preallocated sparse file (`os.ftruncate(self._fd,
  self._file_size)`, `extent_file_backend.py:370`); `pwritev`/`preadv` with
  iov sharding and range-merge; stats track read amplification
  (`:349-367`).
- **Lazy GC + bounded growth.** `_gc_evict` is a synchronous watermark GC on
  the write path (`:1164-1187`); circular reuse drops the slot the cursor wraps
  into even with no watermark set, so the file is hard-bounded by `file_size`
  (default 64 GiB) and never grows without limit.
- **Fail-closed malformed/stale handling.** Oversized page -> `None`
  (`extent_allocator.py:190-191`); batch larger than the file refused
  (`:196-198`); v1/v2 key scoping is identical (`_storage_key`/`_component_key`,
  `:383-389`) so write and query cannot silently disagree.
- **Factory constructible.** `backend_factory.py:201-205`, and
  `test_extent_file_backend_unit.py` exercises ~88 cases including
  `test_factory_creates_real_extent_backend`, `test_crash_reopen_all_cold`,
  `test_get_stats_matches_engine_contract`, `test_same_span_write_then_query_storage_hit_4`.

### 3.2 Gaps that remain (honest, ranked)

| # | Gap | Evidence | Severity for production L3 |
| - | --- | --- | --- |
| G1 | **No metadata persistence / restart rebuild.** Docstring: "restart starts cold -- no metadata persistence" (`extent_file_backend.py:20`); test `test_crash_reopen_all_cold` asserts the index is empty after reopen. After a restart the data bytes survive but are unreachable (the RAM index is the only authority). | `extent_file_backend.py:20`, allocator has no load/save path (grep: only `clear` touches index wholesale). | HIGH if restart-recoverable L3 is required; LOW under pure cache semantics (cold = misses, correctness preserved). |
| G2 | **Default sizing must be set explicitly for this workload.** `_DEFAULT_EXTENT_SIZE = 64 MiB`, `_DEFAULT_FILE_SIZE = 64 GiB` (`:60-62`). The R129 L3 footprint is 133 GB, so the default file holds under half. `storage_dir` defaults to `/tmp/hicache` when no env/extra is set (`:281-287`), which is wrong for this deployment. | `:60-62,281-287`; `du -sh l3` = 133 GB. | HIGH (deployment config; no code change needed). |
| G3 | **`get_stats()` returns `None`.** Deliberate: returning a dict crashes the scheduler's `prefetch_stats` assignment; only `stats_snapshot()` exposes raw counters. So the engine-level metrics path has no extent numbers without a probe. | `:1202-1207` + embedded comment. | MEDIUM (observability; E4 can read `stats_snapshot` via probe). |
| G4 | **Single data file per rank, no cross-rank sharing.** `config_suffix` isolates ranks; TP=1 is fine here but a multi-rank production topology gets one file per rank. | `:270-279,344-347`. | LOW for the frozen TP=1 3090 profile. |
| G5 | **No on-disk integrity verification.** `lookup` trusts the RAM index; disk corruption/truncation is not detected until a read mismatch. | `:138-147,297` (get size mismatch -> `None`). | LOW for cache semantics. |

G1 is the only gap that could change the architecture contract. G2/G3 are
deployment/observability, resolved in E2 without code. Whether G1 is in scope
is a user decision (section 6); it is NOT required to answer the three
questions and NOT required for a same-run E4 performance gate.

## 4. Q3 — Expected improvement (hypothesis to be MEASURED, not claimed)

The extent backend's query path is RAM-dict lookup + generation check, versus
the legacy path's full-directory `os.scandir` of 3.09M entries. The mechanism
that produced 17.8 s/query is removed entirely, so the E4 expectation is that
Q3 storage-query latency drops by orders of magnitude and the L3 stage stops
being query-dominated. This is a **prediction only**; E4 must measure and this
report makes no performance claim.

## 5. Dispatch chain per operation (verified, generic)

- **Select backend:** `server_args.hicache_storage_backend` ->
  `cache_controller.py:645 StorageBackendFactory.create_backend` ->
  `backend_factory.py:161-162` for `file|sim|extent`.
- **Build backend:** `ExtentFileBackend.__init__` (`:255-376`) opens/creates
  `hicache.data{suffix}` under `storage_dir` and builds `ExtentAllocator`.
- **Query (read):** engine `unified_radix_cache.query_storage_hit_length`
  -> `hybrid_cache_controller._storage_hit_query`
  (`hybrid_cache_controller.py:864-932`) -> `batch_exists_v2` (`:914`)
  -> allocator dict lookup. Legacy fallback `batch_exists` (`:890,:922`).
- **Write (backup):** `cache_controller.py:1383 batch_set_v1` (KV) and
  `hybrid_cache_controller.py:1094 batch_set_v2` (non-KV/sidecars)
  -> `plan`/`pwritev`/`commit`.
- **Read (restore):** `cache_controller.py:1103 batch_get_v1`,
  `:1219 batch_get_v2` -> `preadv` at `ExtentRef` offsets.

No engine-side branch inspects the backend class, so `extent` is a drop-in
selection.

## 6. Handoff into E1/E2

- **E1 architecture freeze:** target = `--hicache-storage-backend extent` plus
  explicit `storage_dir`/`file_size`/`max_size`/`min_free_space`; RAM index is
  authoritative; no scandir in the query path. G1 (restart rebuild) is an open
  user decision, not silently added.
- **E2 minimal fix (deployment/selection/dispatch):** add the extent env/config
  to a NEW launch script (never edit `launch-r112.sh`, which is frozen evidence
  for R117/R121-R129); do not modify the legacy FileBackend and do not modify
  engine dispatch. A bounded CPU-only unit re-run of
  `test_extent_file_backend_unit.py` provides E3 pre-live correctness.
- **E3 correctness gates:** v1-write-then-v2-query hit, sidecar component-key
  isolation, generation invalidation, restart-cold semantics, no-scandir.
- **E4 performance gate:** R129-equivalent workload; measure L3 object/extent
  counts, index entries, query p50/p95/p99, L3->L2 stage, thread utilization.

## 7. Evidence manifest (content sha256)

| Evidence | sha256 |
| --- | --- |
| `extent_file_backend.py` | `bef390f13e4479aae4016883ea45e713dc24f008997effed4aca7c4750a09600` |
| `extent_allocator.py` | `afec684803956cbcce637aa1896839a687c3c57e1d29f3dfbab4ae2eb68d339b` |
| `backend_factory.py` | `2b79fb5bd3cc0cb76914735952ff34ff1edb7a02735ad2c69c9a6ef08eba2a77` |
| `hicache_storage.py` (legacy HiCacheFile) | `7c5c7331eda1ded25a25bb5d9938aa76311651b16025f5b8743a17318ff1d1d7` |
| `hybrid_cache_controller.py` | `64e933f490884b74f0d38655a8f5a75157bab530dd0ea0688323c9780f1ce4d5` |
| `cache_controller.py` | `a41e623a2d6e462720d6584af992da290ba54e0cb3766df794117b87678b656f` |
| `launch-r112.sh` | `2259d406f8f2239289d799bfd7bffd6401dedd101ed90225ddc05508cf8caaa3` |
| live log `sglang-server-p2a.log` ("Creating storage backend 'file'") | read-only quote |
| L3 dir `.../l3` | 3,090,193 files / 133 GB (measured) |

Status: `done` (read-only E0 audit). No product/test/gate change; no GPU used.
