# G1 target recon — ExtentFileBackend data model (read-only scout, 2026-09-12)

Source task: `G1-TARGET-RECON-20260912` (scout). Repo
`/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt` @ HEAD `4f41f5bab5`.
All claims are read-only source facts with anchors. No design proposed.

## 0. Path corrections

* `python/sglang/srt/managers/hybrid_cache_controller.py` does NOT exist; the
  hybrid controller is `python/sglang/srt/mem_cache/hybrid_cache/hybrid_cache_controller.py`
  (subclasses `cache_controller.HiCacheController` at `:225`).
* Extent unit tests: `test/registered/unit/mem_cache/test_extent_file_backend_unit.py`.
* E2E restart test: `test/registered/hicache/test_hicache_spec_file_storage.py`.

## 1. File format

`FACT`: **there is no header, superblock, magic, version, checksum, or metadata
record** in the extent file or code. `grep` for `checksum|crc32|md5|digest|sha`
in `storage/extent/` matches only comments/fields; `grep` for
`fsync|fdatasync|O_DSYNC` matches only the docstring `extent_file_backend.py:18`.

* Data file: `f"hicache.data{self.config_suffix}"` — `extent_file_backend.py:345-347`.
* `config_suffix`: `_<model with / -> ->` `:268-270`, `_<tp_rank>_<tp_size>` `:271-272`,
  `_<pp_size>_<pp_rank>` `:273-274`, `_cp...` `:278-279`.
* Creation: `os.open(path, O_CREAT|O_RDWR, 0o644)` `:368`; `os.ftruncate(fd, file_size)` `:370`.
  Sparse preallocation; only written regions allocate blocks.
* Geometry: `extent_size` default 64 MiB `:60`; `file_size` default 64 GiB `:62`;
  `extent_size % 4096 == 0` `:310-313`; `file_size >= extent_size` `:314-317`;
  slots = `file_size // extent_size` `:371`.
* Byte layout: slot `s` = bytes `[s*extent_size, (s+1)*extent_size)`; key bytes at
  `slot_base + ref.offset` (`extent_allocator.py:6-9`).
* Only payloads are written (`pwritev` at `extent_id*extent_size + first`
  `:1153-1157`, `:639-646`). **All metadata is RAM only.** No `.tmp`/`os.replace`
  (unlike `HiCacheFile`, `hicache_storage.py:532-537`).

## 2. Key layout

* `_storage_key(key) = key + config_suffix` `:383-384`.
* `_component_key(pool,key)` = storage_key if pool in {None,"__default__",KV} else
  `_storage_key(f"{key}.{pool}")` `:386-389`.
* `PoolName` str-Enum `hicache_storage.py:63-85` -> `H.mamba`, `H.swa`, `H.indexer`, ...
* Collision condition: KV key of `K'` == component key of `K` for pool `p` iff
  `K' == K + "." + p`. Observed logical keys are sha256 hex (no `.`), so not
  reachable today, but the code does not enforce it.

## 3. In-RAM authoritative state (`ExtentAllocator`, `extent_allocator.py:122-130`)

| field | line | class |
|---|---|---|
| `_index: dict[key->ExtentRef]` | `:129` | **authoritative** |
| `_generations: [int]*num_slots` | `:124` | **authoritative** |
| `_cursors: [int]*num_slots` | `:126` | **authoritative** |
| `_slot_keys: [set]*num_slots` | `:127` | **authoritative** bookkeeping |
| `_slot_bytes: [int]*num_slots` | `:128` | **authoritative** bookkeeping |
| `_next_slot: int` | `:125` | **authoritative** |
| `_recency: OrderedDict` | `:130` | **authoritative** (LRU victim) |
| `used_bytes` | `:134-136` | derived |
| backend `_stats` | `:349-367` | derived |

`FACT`: **all of the above are lost on restart**; a fresh allocator is built at
`:371`. On-disk bytes survive but are unaddressed. Empirically re-confirmed
2026-09-12: `test_crash_reopen_all_cold` -> ok (`Ran 1 test ... OK`).

## 4. ExtentRef (`extent_allocator.py:99-103`)

`msgspec.Struct(frozen=True)` with exactly `extent_id:int, offset:int,
length:int, generation:int`. **No `component`, dtype, key, or checksum field.
No serialization anywhere.** Constructed in `plan` `:204-211`.

## 5. Write / commit path and durability

* `plan` (`:172-213`, pure): refuses page > extent_size `:190-192`; refuses batch
  > file (self-overwrite) `:195-198`; stamps `generation = _generations[slot] +
  passed.count(slot)` `:209`.
* `pwritev` `extent_file_backend.py:1267-1298` (sharded at IOV_MAX=1024 `:73`).
* `commit` `:215-240`: applies drops, unlinks old ref accounting, installs
  `_index[key]=ref` `:234`, advances cursor, refreshes recency.
* Entry: `_write_pages` `:1124-1160` (gc -> plan -> group by extent -> pwritev ->
  commit); `batch_set_v1` `:598-667`; `batch_set_v2` -> per-transfer `_write_pages` `:1018`.
* `FACT`: **no fsync/fdatasync anywhere.** Docstring `:17-20`: "ACK here means
  pwrite success + index registration (no fsync ... a crash leaves the file
  orphaned and the restart starts cold -- no metadata persistence)".
* ACK semantics: `True` iff all pwritev shards succeeded AND commit registered;
  refused batch returns all-`False` with no mutation (all-or-nothing `:1134-1149`).
  Controller ack enqueue `cache_controller.py:1421`, hybrid
  `hybrid_cache_controller.py:1311`; tree drains `unified_radix_cache.py:6845-6947`.
* Ordering: hybrid `_page_backup` writes sidecars `batch_set_v2` `:1091-1094`,
  then KV `super()._page_backup` `:1142`. **No cross-pool transaction.**

## 6. Read / restore path

`_read_pages` `:1053-1122` (snapshot refs under lock, group by extent, merge
ranges gap<=4096, pread exact ranges, re-verify under lock, slice). `batch_get_v1`
`:514-596`, `batch_get_v2` `:909-961`, `batch_exists_v2` `:745-893` (KV prefix =
first missing; sidecar ALL_PAGES/TRAILING scans; result `min`-folded `:892-893`).
Missing key -> None; generation mismatch -> pop + miss `:138-147`; size mismatch
-> None/False.

## 7. Sidecar / all-or-nothing

KV and sidecars for the same logical hash are **separate index entries and
separate extents**. Sidecars are committed before KV in time. **There is no
atomic-group marker on disk or in the format.** On restart a recovered-but-
sibling-missing state would be reported as a shorter prefix by the existing
`min`-folded query, not silently stitched.

## 8. Generation semantics

Assigned in `plan` `:209`; bumped only in `_drop_slot` `:303` (from `commit`
drops `:223-226`, `evict_slot_lru` `:244-256`, watermark GC). `clear` does NOT
reset generations `:284`. Detected via `lookup` `:138-147` and `verify` `:152-163`.

## 9. GC / eviction / invalidation

LRU `evict_slot_lru` `:244-256`; watermark `_gc_evict` `extent_file_backend.py:1137,1164-1187`;
circular reuse via `plan`->`commit` drops; `_drop_slot` `:288-303`, `clear` `:258-284`.
File is never unlinked/truncated after creation; no hole-punch. **Nothing is
recoverable after restart today.**

## 10. Fail-closed / integrity

Oversized page -> None `:190-192`; batch>file -> all-None `:195-198`; size
mismatch -> None/False `:404-409,456-461,550-554,952-954`; short pread/pwrite ->
miss/refuse `:1086-1096,578-581,1285-1289`; v1/v2 geometry guards `:681-728,920-982`;
`get_stats()` -> None `:1197-1202`. **No checksums.** `test_crash_reopen_all_cold`
`:461-488` asserts all keys absent + `opens==1` after reopen.

## 11. Hook points (current anchors only)

* Construction/startup: `extent_file_backend.py:254-376` (config, open `:368`,
  ftruncate `:370`, allocator `:371`). **No load/replay step; no lazy trigger.**
* Factory: `backend_factory.py:161-162`; registered `:201-205`.
* Controller attach: `cache_controller.py:644-648`; hybrid `hybrid_cache_controller.py:305-306,315-316`.
* Per-key authoritative mutation: `ExtentAllocator.commit` `:234`; call sites
  `extent_file_backend.py:651,1158,1018`.
* Invalidation: `_drop_slot` `:288-333`; `clear` `:258-284`.
* Lifecycle seams: `close()` `:1209-1212`, `clear()` `:1189-1195`, controller
  detach `cache_controller.py:726-770`, `reset()` `:835-858`.

## 12. Tests

`test/registered/unit/mem_cache/test_extent_file_backend_unit.py` — `TestExtentAllocator`
`:62-188`; `TestExtentV1` `:269-509` (incl. `test_crash_reopen_all_cold` `:461`);
`TestExtentV2` `:512-777`; `TestExtentV1V2KeyScope` `:780-933`; `TestExtentV1ZeroCopy`
`:943-1352`; `TestExtentClosedLoop2048` `:1356-1525`; `TestExtentIovMaxBoundary`
`:1528-1563`; `TestExtentReadAmplification` `:1566-1736`; `TestExtentTensorPages`
`:1738-1881`; `TestExtentFullFile` `:1883-1908`; `TestExtentFactory` `:1912-1938`;
`TestExtentWriteQueryRoundTrip` `:1970-2031`.
E2E: `test/registered/hicache/test_hicache_spec_file_storage.py:88-156`.

## 13. E2E restart oracle (CRITICAL FINDING)

`FACT`: the shared mixin `python/sglang/test/hicache_spec_storage_common.py`
`_run_storage_loadback_keeps_spec_accept_length` (`:228-272`) asserts, **after a
real process restart** (`_restart_spec_server` = stop + launch, `:121-124`):

* `storage_cached_tokens >= input_token_len - 2*page_size` (`:249-254`), and
* `cached_tokens_details["storage_backend"] == expected_storage_backend` (`:258-262`).

That assertion was added to the shared mixin by commit `f4e7a98fe5`
(ancestor of HEAD, `git show` confirms `+storage_cached_tokens` lines).
`TestHiCacheSpecExtentStorage` (`test_hicache_spec_file_storage.py:88-158`)
inherits it and does NOT override it.
`FACT`: `HiCacheFile` scans the directory at restart (`hicache_storage.py:459,591,721`)
-> the `file` sibling is warm; `ExtentFileBackend` is cold (§3) -> the **extent
variant of this E2E test is expected RED today** (exact red/green to be
established during G1 verification; not run in this design-only recon).
