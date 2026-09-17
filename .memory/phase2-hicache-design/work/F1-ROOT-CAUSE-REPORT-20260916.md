# F1 — first true->false lookup condition (root cause + minimal fix), CPU-only static/offline analysis

Task: `f1-l3-restore-miss-rootcause-20260916` — role `debugger-deep`.
Tree analysed (frozen, read-only): `/opt/sglang/local-prod-v1.1-candidate/src/python/sglang`
(`sglang.__file__` verified => `.../local-prod-v1.1-candidate/src/python/sglang/__init__.py`).
Evidence store (read-only): `/var/log/sglang/local-prod-v1.1/phase9-production-validation-20260916/`.
Scratch: `/tmp/opencode/f1-restore-miss-20260916/`. Nothing under `/opt/**`, the workspace,
`/data/models`, or `/data/l3/**` was modified; no GPU lock, no server, no port.

## 1. Verdict

**ENTRY: ACCEPT.** The defect is real, reproducible from preserved artifacts, and is a
**layer (A) storage-layer false negative**, not an admission-policy exclusion:

* The runtime's own post-restart `prefetch_revoke ... storage_hit=0 requested=23182
  miss_reason=miss storage_generation=0` is produced **after a completed storage query**
  (`operation.storage_hit_count == 0`, not "never asked").
* The rebuilt index does hold 23,165 of the 23,182 queried page keys — **in one contiguous run
  that starts at page 3, not page 0**. `ExtentFileBackend.batch_exists` has the contract
  "number of consecutive existing keys **from the start**" (`hicache_storage.py:316-325`) and
  returns the index of the *first absent* key, so it returns **0** and the whole chain is
  reported as missing.
* **The first true->false transition is therefore the presence check on the FIRST queried page
  key (page 0)**; every earlier stage of the trace order is TRUE.
* Layer (B) (`restore_potential=False`, `negative_cache_blocked=True`, `reason=negative_cache`)
  is **strictly downstream**: the preadmission log shows `decision=issue reason=issued
  restore_potential=True` at pass 22285 (before/at the byte lookup) and the `negative_cache`
  park only at pass 22298, and the park is armed by `RestoreEvent.REVOKED_MISS`
  (`scheduler.py:4578-4589`) — i.e. by this very miss.
* `storage_generation=0` is a **red herring**: it is the *global* `l3_publish_epoch()`
  (`unified_radix_cache.py:6649` -> `unified_tree_core.py:2146`), which the code documents as
  **diagnostic-only, never participating in any gate**. The negative-cache cursor in the same
  log is the *per-anchor* `storage_version` (`negative_cursor=1`, non-zero).

The chain that broke is:

```
WAL seq 1  SET page0 -> slot 0, offset 0, generation 0      (the ONLY key in that frame)
   |
   |  page 0 is the shared prompt-head page; every later request matches it in L1/L2,
   |  so the write-back span starts after it and it is NEVER written again
   v
21:37:30  evt=extent_recycle slot=0 generation=1 freed=52559872
          (circular cursor wrap, `ExtentAllocator._plan_pure` -> passed -> apply_drops)
   |
   |  DROP_SLOT frame seq 3978 records it durably; WAL replay reproduces it
   v
21:56:41  restart server finishes replay (scheduler_e2e=900.55 s)  -> index rebuilt WITHOUT page 0
21:56:56  request 2010dbf4… : prefetch 23182 pages from page 0 -> batch_exists -> 0 -> RECOMPUTE
```

## 2. Trace table: `storage key -> config_suffix -> namespace/epoch -> batch_exists* -> generation -> extent/ref -> admission/negative`

| # | stage | value observed (post-restart) | T/F | evidence |
|---|-------|-------------------------------|-----|----------|
| 1 | storage key | runtime key = `sha256(page, prior_hash) + config_suffix`. Version in the tree is 64-hex (`get_hash_str(..., page_size=1)`). WAL `seq=1` key = `f9ec16cd…759b4b` + `_-data-models-qwen35-9b-w4a16_0_1`; the frozen tree recomputes the *same* 64-hex string for page 0 of the exact 23,183-token prompt (`matches_round1_prompt_tokens: true`). | **TRUE** | `extent_file_backend.py:1147`; `cache_controller.py:1303-1305`; `utils.py:107-113`; WAL seq 1 (`verify_f1_v2.json`); `offline_marker_membership.json` |
| 2 | config_suffix | `_-data-models-qwen35-9b-w4a16_0_1`, identical pre- and post-restart (same model path / tp=1), so the same data/manifest/WAL paths. | **TRUE** | `extent_file_backend.py:354-376`; `server.console.log.pre-restart:688` vs `server.console.restart.log:688` (same `file=/data/l3/local-prod-v1.1/hicache.data_-data-models-qwen35-9b-w4a16_0_1`) |
| 3 | namespace / epoch | The lookup path has **no epoch component** (`_storage_key` = key+suffix only). `_namespace_epoch` is regenerated per startup (`:920`) and only gates *staging new group writes*; it never gates a read. Same store dir `/data/l3/local-prod-v1.1`. Recovery validated geometry/uuid/dev/ino and replayed; no `clear` is called anywhere in the harness. | **TRUE** (not a cause) | `extent_file_backend.py:920, 795-934, 1147`; no `storage-backend/clear` in `*.py`/`*.sh`; `manifest` re-persisted at startup |
| 4 | **batch_exists*** | `_storage_hit_query` queries **23,182** keys starting at **page 0** (`prefetch_length=23182`, `device_hit_tokens=0`). `ExtentFileBackend.batch_exists` returns the index of the **first absent** key = **0**; `_storage_hit_query` sees `hit_page_num(0) < len(batch)` and breaks with `storage_query_count = 0`. | **FALSE at index 0** | `cache_controller.py:1296-1319`; `extent_file_backend.py:1267-1274`; `hicache_storage.py:316-325`; runtime `prefetch_revoke storage_hit=0 requested=23182 miss_reason=miss` |
| 5 | generation | `lookup` rejects a ref whose `generation != _generations[ref.extent_id]`. Post-replay `_generations = replay.generations` and `_restore_allocator` **already asserts** `entry.generation == replay.generations[entry.extent_id]` for every entry (or the server raises `RecoveryError` at init). The server started => every installed ref passes the generation check. `generations_set=[0,1]` (slots 0-150 at gen 1 via DROP_SLOT). | **TRUE** | `extent_allocator.py:148-157`; `extent_file_backend.py:727-733, 780-788`; `verify_f1_v2.json` |
| 6 | extent / ref | For the 23,165 surviving keys the refs are intact (slots 993-999 region, generation matches). **Page 0 has no ref at all** — its key was removed with slot 0. | TRUE for 3..23167, **absent for 0,1,2** | `offline_marker_membership.json` (`n_present=23165`, `n_missing=18`, `first_missing_index=0`, `present_slots=[993..999]`, `n_drops_hitting_present_marker_slots=0`); `verify_f1_v2.json` |
| 7 | admission / negative state | Pass 22285 (before the query result): `restore_potential=True staging_eligible=True negative_cache_blocked=False decision=issue reason=issued issue_origin=READY_HORIZON`. Pass 22298 (after the miss): `reason=negative_cache negative_cache_blocked=True negative_cursor=1`. Park armed by `RestoreEvent.REVOKED_MISS and genuine_miss`. | not a cause (strictly downstream) | `server.console.restart.log:722 vs :729`; `scheduler.py:4578-4589, 5308-5309` |

### 2.1 Which `batch_*` the restore path actually calls (dispatch question)

`cache_controller.py:685-696`: for `storage_backend_type == "extent"` the controller selects the
**zero-copy v1 surface** — `page_get_func = _page_get_zero_copy` -> `batch_get_v1`
(`extent_file_backend.py:1278`) and `page_set_func = _page_set_zero_copy` -> `batch_set_v1`
(`:1362`). The *existence gate* of the restore path is **`batch_exists` (v1, `:1267-1274`)**
(`cache_controller.py:1311`), **not** `batch_exists_v2`/`batch_get_v2` (those are used for the
sidecar/Mamba pool checks) and not the generic `batch_get`/`batch_set` (used only when the backend
is outside the zero-copy list). So: the query that returned "absent" is `batch_exists`; the read
that would have followed is `batch_get_v1`.

**First true->false transition:** the presence check of the **first queried page key**,
`ExtentAllocator.lookup(self._storage_key(page_hash[0]))` returning `None`
(`extent_allocator.py:148-157`, entered from `extent_file_backend.py:1271-1273`).

## 3. Why it is a *false* negative: the arithmetic closes exactly

| measurement | value | source |
|---|---|---|
| pre-restart query (21:28:58, same 23182-page window from page 0) | `storage_hit=23168` | `server.console.log.pre-restart:4138` |
| pre-restart restore outcome | `completed=23168 matched=3 loaded=23165` | `server.console.log.pre-restart:4200`, `:4207` |
| post-drop replayed index, marker keys present | `23165` | `offline_marker_membership.json` |
| difference | **23168 − 23165 = 3 = pages 0,1,2** | |
| page 0's only ever write | WAL `seq=1`, `slot=0, off=0, gen=0, len=16384` | `verify_f1_v2.py` `first_set_frame` |
| page 1's only ever write | WAL `seq=4`, `slot=0, off=16384` | `verify_f1_v2.json` `head_key_write_history` |
| page 2's only ever write | WAL `seq=4`, `slot=0, off=32768` | `verify_f1_v2.json` `head_key_write_history` |
| page 3 (first non-head page) | **two** writes: `seq=29 slot=4` and `seq=3735 slot=993` | `verify_f1_v2.json` `head_key_write_history` |
| the eviction | `evt=extent_recycle slot=0 generation=1 freed=52559872` @ 21:37:30 | `server.console.log.pre-restart` |
| the drop set | slots 0..150 only, `first_drop_seq=3978` | `offline_marker_membership.json`, `verify_f1_v2.py` |

So the pre-restart index held pages **0..23167** (page 0 from WAL seq 1 in slot 0; pages 3..23167
from the marker's own write, still live in slots 993-999). The 21:37-21:40 sweep recycled slots
0-150 and destroyed the **write-once head**; the 21:56 restart replayed that faithfully. The
post-restart query therefore starts on a key that is *guaranteed* absent, and a 99.93%-present
chain (23165/23182) is reported as 0 hits.

The eviction was **not** GC: with `max_size=100 GiB*0.9 = 96.6 GiB` vs `used_bytes≈47.1 GB`, and
`f_bavail*f_frsize ≈ 247 GiB > min_free_space 50 GiB`, `_select_gc_victims()` returns `[]`
(`extent_file_backend.py:2041-2062`). It is the circular cursor wrap: `_plan_pure` marks the
entered slot `passed` when its cursor cannot fit the new page
(`extent_allocator.py:237-299`) -> `apply_drops` (`:328-385`), invoked from
`_write_pages_locked` (`extent_file_backend.py:1978-1996`).

**Refuted alternatives (tested, not assumed):**

* *"never durably committed"* / *"replay failed"* — refuted by the WAL replay (921,893 entries,
  no torn tail, seq 1..5035 continuous) and by the runtime's own pre-restart `storage_hit=23168`.
* *"startup `clear` wiped the recovered index"* — refuted: no `clear` call exists in the harness;
  `wal.0`'s mtime is 21:40 (never unlinked/re-created by the 21:41 restart) and
  `scheduler_e2e=900.55 s` startup shows the restart spent ~15 min in WAL recovery, which a
  fresh/cleared namespace cannot do.
* *"generation mismatch after replay"* — refuted by the recovery assertion (`:727-733`).
* *"admission excluded it before the byte lookup"* — refuted (pass 22285 issued).
* *"`storage_generation=0` gated the decision"* — refuted (diagnostic-only counter).
* *"the prefetch was revoked before storage answered"* — refuted: `terminated=False` and the
  drain path that revoked it (`unified_radix_cache.py:6953-6977`) consumes the operation only
  after `prefetch_hit_queue` was fed by `_storage_hit_query` (`cache_controller.py:1333-1350`);
  `PrefetchOperation.storage_hit_count` defaults to 0 only for the terminated-not-queried case,
  which would have logged `terminated=True`.

### 3.1 Direct offline execution of the frozen predicate (`verify_f1_v2.json` / `verify_f1_v3.json`)

Full fold of the preserved WAL with the tree's own `replay_records`, index installed into a real
`ExtentAllocator`, then the real `ExtentFileBackend.lookup`/`batch_exists` path:

```
replay_full        : n_entries=921893, seen_max_seq=5035        (identical to offline_wal_analysis.json)
allocator_rebuilt  : n_index=921893, generations_set=[0,1], next_slot=0
membership_query_window (23,182-key window, pages 0..23181):
                     n_present=23165  n_absent=17
                     first_present=3  first_absent=0
                     single contiguous run: start=3, len=23165
lookup(storage_key(page 0)) -> None          lookup_page0_is_none: true
lookup(storage_key(page 3)) -> ExtentRef     lookup_page3_is_none: false
head_key_write_history (all 5,035 frames / 2,044 SET frames):
                     page0: written 1x  (seq 1,  slot 0, offset 0)
                     page1: written 1x  (seq 4,  slot 0, offset 16384)
                     page2: written 1x  (seq 4,  slot 0, offset 32768)
                     page3: written 2x  (seq 29, slot 4, offset 51511296)
                                        (seq 3735, slot 993, offset 131072)
```

`batch_exists` for the runtime's window (starting at page 0, `STORAGE_BATCH_SIZE=1024`) therefore
returns **0** — the window's very first key is absent — and `_storage_hit_query` returns 0, exactly
matching the runtime's `storage_hit=0 requested=23182 miss_reason=miss`. A window starting at
page 3 (which is the shape pre-restart traffic produced when the head was still stored) would have
returned **23165**: the single present run `[3, 23165]` is the run pre-restart's restore consumed
(`completed=23168 matched=3 loaded=23165`).

### 3.2 Direct execution of the frozen predicate (`verify_f1_v3.json` — corrected harness)

`batch_exists` applies `_storage_key` itself, so the harness passes **bare** 64-hex page hashes.
Result (verbatim):

```
replay_full : n_entries=921893                       (identical to offline_wal_analysis.json)
predicate   : window_from_page0_hits    = 0      (requested 23182)   <-- reproduces the runtime
              window_from_page3_hits    = 23165  (requested 23179)
              first_batch_returned      = 0
              lookup_page0_none         = true
              lookup_page3_none         = false
              lookup_page0_storage_key  = f9ec16cdf22e0d09b737c0b00f7ad357eb62cd6ece579670
                                          6f0871f0e3759b4b_-data-models-qwen35-9b-w4a16_0_1
              STORAGE_BATCH_SIZE        = 1024
```

`window_from_page3_hits = 23165` reproduces both the membership run `[3, 23165]` and the
pre-restart restore's `loaded=23165` (`server.console.log.pre-restart:4200`).
`window_from_page0_hits = 0` reproduces the post-restart `storage_hit=0`.

**Evidence-integrity note (why v3 exists).** The v1/v2 harnesses appended `config_suffix` twice
(windows were pre-suffixed and `ExtentFileBackend._storage_key` appends it again), so their
*literal* `batch_exists` output (0 for both windows) is **invalid evidence** and must not be
quoted. Their membership / `lookup` results index raw keys and are unaffected. v3 fixes this; the
v2 membership result (`single run [3, 23165]`, `first_absent=0`) independently predicts v3's
`0` / `23165`, and both agree.

### 3.3 Blast radius: when the defect bites (observed vs predicted)

The runtime only queries from page 0 when the request's in-memory prefix match is 0: the prefetch
key is `RadixKey(new_input_tokens)` = the tokens after the matched prefix
(`unified_radix_cache.py:5341-5347`), and the query window is that key's page-hash chain
(`cache_controller.py:1303-1305`). So:

* **Observed (this incident).** Post-restart, `device_hit_tokens=0 host_hit_tokens=0`
  (`server.console.restart.log:719`) -> the window starts at page 0 -> the evicted head is the very
  first key -> `storage_hit=0`. Pre-restart (21:28:58) the *same* 0-match geometry hit
  `storage_hit=23168` only because the head was still stored.
* **Observed counter-check.** Post-sweep pre-restart prefetches (96 of them, 21:37:30-21:41) all
  returned `storage_hit=0`, but their `requested` never exceeded 348 tokens (their L1 match was
  large, so they never queried page 0). They are therefore **not** evidence of the general case.
* **Predicted (not directly observed in these artifacts).** Once slots 0-150 are recycled, the
  shared prompt-head pages are gone from L3 permanently (they are write-once: see
  `head_key_write_history`). Any later request with a 0/short L1 match — a cold agent session, a
  post-eviction long-context request, or a restart — will query from page 0 and get
  `storage_hit=0` for an otherwise fully-present chain. No such request exists in the preserved
  artifacts (the server was killed at 21:41), so this remains a prediction and is exactly what a
  follow-up GPU run should test directly.

## 4. Minimal fix (REPORTED, NOT APPLIED)

The lookup predicate is **correct per its contract** ("consecutive keys from the start"), and a
"skip the gap" change would be **wrong**, because `_page_transfer` maps hit index *i* to host slot
*i* (`cache_controller.py:1155-1165`) — restoring pages 3..N into slots 0..N-3 would misplace
every page. The defect is therefore on the **durability** side: the chain head must not be lost.

**Primary (smallest change that makes the hit succeed).**
`UnifiedTreeCore.build_storage_backup_spec` (`srt/mem_cache/unified_cache/unified_tree_core.py:2062-2087`):
the spec already carries the ancestor chain's hashes as `prefix_keys`
(`node.get_prefix_hash_values(node.parent)`, `:2071`), so `prefix_keys[0]` **is** the chain head.
Change: when the node has a non-empty matched prefix, **prepend the chain-head page (key + its
host slot) to `hash_value`/`host_value`/`token_ids`** so the head page is re-written (16 KiB per
backup). The write path already re-writes per-node spans and `collect_storage_gap`
(`:2089-2109`) already re-writes ancestor pages from the host pool, so the mechanism exists; the
change is to include the head of the anchor chain once per backup instead of never.
Effect: page 0 stops being "write-once in the oldest slot" and is refreshed by ordinary traffic;
its `lookup` stays TRUE and the post-restart query returns the full 23,165-page run.

**Alternative (equally small, different owner/risk):** make the extent allocator
**head-aware** — register a key as a chain head when it is the first key of a `batch_set` whose
`prefix_keys` is empty (the backend can identify it: `extent_file_backend.py:1252-1274`,
`_page_backup` `cache_controller.py:1405-1432`) and make `_plan_pure`/`apply_drops`
(`extent_allocator.py:237-299, 328-385`) refuse to recycle a slot that holds a registered head.
Trade-off: needs an unpin rule, and pins accumulate for prompts with unique heads.

**Not recommended:** gap-tolerant `batch_exists` / `_storage_hit_query` (position contract);
per-key eviction instead of whole-slot recycling (fragmentation, larger change);
`file_size >= working set` (only postpones the wrap; the head is still write-once).

## 5. Evidence that would PROVE the fix (and what would falsify my root cause)

Decisive GPU run (one request, post-restart-equivalent cold L1):
1. **Proves the root cause**: after a `DROP_SLOT` sweep that recycles the slot holding page 0, a
   cold-L1 request must reproduce `storage_hit=0 miss_reason=miss` **while** an offline replay of
   the same WAL shows `n_present=23165` with `first_absent_index=0`. (Already true here.)
2. **Proves the fix**: with the head-refresh change, the same cold-L1 request must show
   `storage_hit > 0` and `restore_success n_tokens ≈ 23165` with `l3_tokens > 0`, and a WAL
   inspection must show page 0's key re-`SET` after the sweep (a `SET` frame for `page0` with a
   later `seq` than the last `DROP_SLOT` affecting its slot).
3. **Falsifies my root cause** if any of these holds: (a) an offline replay of the WAL that the
   *restart server actually consumed* (byte-identical to `pre-gate4-store/wal.0`) contains page 0
   — i.e. my `first_set_frame`/membership result is wrong; (b) a cold-L1 post-restart request
   returns `storage_hit=0` even though page 0's key IS in the rebuilt index (then the false step
   is later in the chain, and `_storage_hit_query`'s key list does not start at page 0);
   (c) the runtime's query window does not start at page 0 (e.g. `prefetch_length` ≠ queried page
   count) — verifiable in one run by logging `page_hashes[0]` next to `_storage_key(page_hashes[0])`.

Cheapest decisive instrumentation (no code change to the frozen tree; a diagnostic probe only if
the owner authorises it): log the full 64-hex `page_hashes[0]` and the `lookup(...)` verdict for
it in `_storage_hit_query`, plus `requested`; one cold-L1 request after one sweep settles 2 and 3.

## 6. Artifacts produced

* `/tmp/opencode/f1-restore-miss-20260916/verify_f1_v2.py` — offline replay + real
  `ExtentFileBackend.batch_exists` / `_storage_hit_query` predicate harness (frozen tree code).
* `/tmp/opencode/f1-restore-miss-20260916/verify_f1_v2.json` — full fold + membership + head-key
  write history (authoritative).
* `/tmp/opencode/f1-restore-miss-20260916/verify_f1_v3.py` / `run_v3.log` — corrected predicate
  harness (bare page hashes) run to replace the invalidated v1/v2 `batch_exists` invocation.
* `/tmp/opencode/f1-restore-miss-20260916/verify_f1_lookup.py` + `verify_f1_lookup.json` — v1
  (superseded; the `batch_exists` shim lacked `config_suffix` and raised after the replay).
* `/tmp/opencode/f1-restore-miss-20260916/marker_hashes.json` — the 23,183 prompt token ids.
