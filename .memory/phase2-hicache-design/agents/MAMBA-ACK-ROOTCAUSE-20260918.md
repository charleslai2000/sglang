# MAMBA-ACK-ROOTCAUSE-20260918

Status: DONE

## Task
READ-ONLY root-cause of the FIRST break in the Mamba ACK/unpin chain:

`backup submit (write_storage) -> ACK produced by backend -> ACK queued -> scheduler drains ACK -> unpin (ongoing_backup.pop -> dec_host_lock_ref)`

Classify the first break as exactly ONE of:
(a) ACK never produced by the L3 backend;
(b) ACK produced but dropped / never enqueued;
(c) ACK enqueued but the scheduler never drains the queue;
(d) ACK present but filtered/rejected by a generation/ownership/durability predicate;
(e) the only release path ever taken is shutdown detach (normal in-run drain structurally unreachable for Mamba backups).

## Scope
- READ-ONLY. No code/test/config change, no restart, no GPU, no server launch, no new instrumentation,
  no diagnostic-gate enablement. Only this artifact was written.
- FROZEN tree `/opt/sglang/local-prod-v1.2.1-candidate` is authoritative. All `file:line` evidence below is
  from that tree. Verified against `manifest/TREE-SHA256.txt` at the time of analysis:
  - `unified_radix_cache.py` sha256 `5b5dc29fa21eefdf44ac660881cab02e9bc6ab1408cd33ca645a4bb326f6bf6f` (MATCH)
  - `hybrid_cache/hybrid_cache_controller.py` sha256 `4462403deb5b4975a5be95072cd344bb98a01dba78f10c40eb9aead08b843729` (MATCH)
  - `storage/extent/extent_file_backend.py` sha256 `a5c99fd1cc32b64518ceaed01cac46c53b5622395d259a897c674e317cdd0cbd` (MATCH)
  - `managers/cache_controller.py` sha256 `ef09a30780cb3b5d625cfe57887f6485fd96004f801aa5a9623878a74dfdf001` (MATCH)
  - `managers/scheduler.py` sha256 `a85e8078d476b1f5107186b58babf78d3becedf596cfc1df92343bd29165efdc` (MATCH)
  - `unified_cache/storage_attachment.py` sha256 `f22de1948c4692d701ad4bbda22988d6cea29c6848a7087a3d2bd3beb2af6af6` (MATCH)
  - Manifest identity: `identity.json` TREE_HASH `5ed662d0b603ef9ab29294a690c036718714e0ed5b699b62b8b7be488defd950`,
    `SOURCE_COMMIT b2bbd6ea28`, deployment_manifest_digest `262a9362e345df15d93049301d2b0e60990ba65d80c3bbc5205fb4cdab140e2d`
    (as embedded in every run's `[HAE]`/`[P3]` event).
- Worktree `/home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt` HEAD `ea7b0e9b445e23852cd900ee0abe9e2a1eab17ee`;
  `unified_radix_cache.py` is concurrently modified (`git status` = ` M`), so it was NOT used for any `file:line`
  claim. No claim here depends on worktree bytes.
- Failing run under analysis: `SGLANG_RUN_ID=prod-20260917T211800Z-1653969`, prod pid 1654601, launcher
  `/opt/sglang/local-prod-v1.2.1-candidate/launcher/launch.sh`, L3 namespace
  `/data/l3/prod-20260917T211800Z-1653969`.
- Log sources used: `server.console.log`, `supervisor.log` under
  `/tmp/opencode/prod-service-20260917/logs/prod-20260917T211800Z-1653969/`; scrapes
  `/tmp/opencode/mam_metrics{,2,3}.txt`; control runs under `/tmp/opencode/prod-service-20260917/logs/*`
  and `/tmp/opencode/mamba-sweep-20260918/phase2/logs/*`; L3 store on disk `/data/l3/*`.

## Result

**Primary verdict: (a) ACK never produced by the L3 backend.**

The L3 backend produced **zero durable commits for the entire failing run**. Because the controller-level ack
is enqueued only after `_page_backup` returns True, zero commits means the ack is never enqueued, the
`ack_backup_queue` never fills, the (fully reachable) scheduler drain has nothing to drain, and the
submit-time pin at `unified_radix_cache.py:5004-5007` is never released in-run. The pin is released only
later by shutdown detach, which is why 128 mamba nodes stayed pinned until 23:06:30.

Established components of the chain:
- **Submit: ESTABLISHED (submits occurred).** Pins are acquired only at `unified_radix_cache.py:5004-5007`,
  immediately after `cache_controller.write_storage(...)` returns (`:4974`). The 23:06:30 teardown event shows
  `pool="mamba", cause="lock_release_evictable", evictable_before 0 -> after 128, telemetry_mutation_count 128`
  from `dec_host_lock_ref` — i.e. 128 mamba nodes transitioned out of `host_lock_ref>0` in one coalesced burst.
  Known non-backup pin sources are far too small to account for that: `load_back_tokens_total{mamba}` = 38-40
  (`/tmp/opencode/mam_metrics{,2,3}.txt`) and `prefetch_issued` count = 13 (`server.console.log`). So the
  large majority are `ongoing_backup` entries and the submissions definitely happened.
- **ACK produced by backend: NOT ESTABLISHED (this is the FIRST break).**
- **ACK queued: DID NOT HAPPEN.**
- **Scheduler drain: REACHABLE and functioning; nothing to drain.**
- **Unpin: only the shutdown-detach path was taken.**

**Partial-classification caveat (stated explicitly):** I can establish that the first break is the backend
hop and that it is not (b)/(c)/(d)/(e). I cannot, from existing frozen evidence, prove the *reason* the
backend never committed (silently swallowed exception vs. backup-thread death). That residue is enumerated
in "Remaining claims" as item R1 and requires one live diagnostic read to close; it does not change the
(a) classification.

## Evidence

### E1. Chain walk with `file:line` (frozen tree)

Hop 1 — SUBMIT:
```
unified_radix_cache.py:4837   def write_backup_storage(self, node_id)
unified_radix_cache.py:4907   def _write_backup_storage_node(self, node_id)
unified_radix_cache.py:4974   operation_id = self.cache_controller.write_storage(...)
unified_radix_cache.py:5004   self.ongoing_backup[operation_id] = (
unified_radix_cache.py:5006       self.inc_host_lock_ref(node_id).to_dec_params(),
unified_radix_cache.py:5010   self.tree_core.mark_storage_written(node_id)   # dedupe: never re-collects this node
```
`write_storage` here is the hybrid override (the attached controller is `HybridCacheController`,
`server.console.log` 21:20:00 "Attached hybrid pool stack to UnifiedRadixCache: pools=KV + MAMBA"):
```
hybrid_cache/hybrid_cache_controller.py:850  def write_storage(...)
hybrid_cache/hybrid_cache_controller.py:883  self.backup_queue.put(operation)
hybrid_cache/hybrid_cache_controller.py:884  return operation.id
```
=> `write_storage` returning an id ALWAYS arms a pin at `:5006`. The pin is unconditional on backend outcome.

Hop 2 — ACK PRODUCED BY BACKEND (the break):
```
hybrid_cache/hybrid_cache_controller.py:1227  def backup_thread_func(self)
hybrid_cache/hybrid_cache_controller.py:1236  operation = self.backup_queue.get(block=True, timeout=1)
hybrid_cache/hybrid_cache_controller.py:1239  if not self._page_backup(operation):
hybrid_cache/hybrid_cache_controller.py:1240      continue          # <-- op discarded here; NO ack ever enqueued
...
hybrid_cache/hybrid_cache_controller.py:1332  self.ack_backup_queue.put(operation)   # reached ONLY if _page_backup True
```
`_page_backup` returns False on every failure branch without emitting an ack:
```
hybrid_cache/hybrid_cache_controller.py:1154-1155   if not sidecar_ok: return False
hybrid_cache/hybrid_cache_controller.py:1192-1193   if not kv_ok: return False
hybrid_cache/hybrid_cache_controller.py:1194-1196   committed = commit_group(group_id); return committed
hybrid_cache/hybrid_cache_controller.py:1198-1199   except Exception: return False   # SILENT
hybrid_cache/hybrid_cache_controller.py:1200-1202   finally: abort_group if not committed
```
The backend "ack" is the extent store's successful commit:
```
storage/extent/extent_file_backend.py:2257  def _write_pages_locked(...)   # all-or-nothing
storage/extent/extent_file_backend.py:2351-2359  if group_id: stage_group_members(...)
storage/extent/extent_file_backend.py:2360-2365  commit_install + _components.update + _t38c_extent_commits -> True
```
=> `_page_backup` False means the backend did not durably commit, so the ack (which is only the
success return of `batch_set_v2`/`commit_group`) was never produced.

Hop 3 — ACK QUEUED:
Contractually only at `hybrid_cache_controller.py:1332`, immediately after a True `_page_backup`. There is no
other `ack_backup_queue.put` in the hybrid path (verified: the only put is `:1332`).

Hop 4 — SCHEDULER DRAINS ACK:
```
managers/scheduler.py:6695       if self.enable_hierarchical_cache or get_memory().enable_flexkv:
managers/scheduler.py:6696           self.tree_cache.check_hicache_events()
unified_radix_cache.py:7975      def check_hicache_events(self)
unified_radix_cache.py:8009-8014     ... = self._sync_hicache_ready_counts()   # MIN-reduced qsizes
unified_radix_cache.py:8018-8037     self._drain_storage_control_queues_impl(...)
unified_radix_cache.py:7033      def _drain_backup()
unified_radix_cache.py:7035          for operation in _drain_queue(cc.ack_backup_queue, n_backup)
```
Reachability (see V-e below): `check_hicache_events` is on the unconditional path of
`_get_new_batch_prefill_raw`, which `get_next_batch_to_run` calls every scheduler iteration; `_should_defer_prefill`
returns False because `prefill_decode_interval == 0` (`scheduler.py:1489-1494`, server args
`'prefill_decode_interval': 0`). So the drain runs every scheduler pass, not just when prefetches occur.

Hop 5 — UNPIN:
```
unified_radix_cache.py:7131   if buffer_mode:
unified_radix_cache.py:7135       entry = self.ongoing_backup.pop(operation.id, None)
unified_radix_cache.py:7137-7138  node_id, lock_params = entry; self.dec_host_lock_ref(node_id, lock_params)
```
The pop at `:7135` is **unconditional** in the non-buffer branch. `_t38c_mamba_rank_proof` (`:7073`) is
called just before but its result gates only the *promotion* (`:7156-7426`), not the unpin. The only other
in-run release is the storage-degraded path `unified_radix_cache.py:7971-7973`
(`_handle_storage_failure`), which fires only when `cc.storage_failure_reason is not None`
(`:7978`), which never happened (see E4).

### E2. Decisive store evidence: the L3 backend committed NOTHING in the failing run

`server.console.log` for the failing run contains **0** occurrences of `evt=extent_write`,
**0** `pc_mamba_write`, **0** `pc_storage_query`, **0** `Write page to storage`, **0** `partial backup`,
**0** `native write failed`, **0** `refused`, **0** `indices length mismatch`, **0** `storage failure`.
Info-level logging was demonstrably active (13,571 lines incl. 3,305 `[P3]` and 286 `[P2A]` lines).

`_log_extent_write` is the success-only record:
```
storage/extent/extent_file_backend.py:1391  def _log_extent_write(...)
storage/extent/extent_file_backend.py:1424      self._log_extent_write("kv", None, storage_keys, values)   # batch_set
storage/extent/extent_file_backend.py:1631      self._log_extent_write(...)                                # batch_set_v1 (KV zero-copy)
storage/extent/extent_file_backend.py:2030      self._log_extent_write(...)                                # batch_set_v2 (sidecar/MAMBA)
```
It is called only under `if ok`, and `batch_set_v2` is the path used for the Mamba transfer
(`mamba_component.py:905-916` builds `PoolTransfer(name=PoolName.MAMBA, host_indices=cd.host_value,
keys=[node.hash_value[-1]], hit_policy=TRAILING_PAGES)`; `hybrid_cache_controller.py:1132-1138` calls
`batch_set_v2`). Zero `extent_write` therefore means zero successful L3 page writes of ANY pool.

On-disk confirmation (independent of the log). The manifest encodes the durable index:
```
extent_metadata.py:543  def deserialize_manifest(data)
extent_metadata.py:591  entry_count = reader.u32()
```
Parsing the three stores with the frozen serializer's layout:
| run dir | manifest bytes | `checkpoint_lsn` | `entry_count` | data file allocated bytes |
|---|---|---|---|---|
| `prod-20260917T211800Z-1653969` (failing) | 20604 | **0** | **0** | **0** |
| `prod-20260918T002151Z-1750622` (later, same tree) | 27862 | 2643 | 49 (48 KV + 1 MAMBA) | 2,334,003,200 |
| `sweep-mamba48-20260917T231327Z-1726566` | 5423884 | 734 | 36505 (36415 KV + 90 MAMBA) | 5,232,644,096 |

`/data/l3/prod-20260917T211800Z-1653969/hicache.data_*` is 67 GiB apparent / **0 allocated blocks**;
the later run and the sweep allocated GB. The failing run's WAL segment header (`SEGMENT_HEADER_SIZE=28`,
`extent_metadata.py:166`) encodes checkpoint lsn 0 and one empty segment.

Cross-run control on the same frozen tree (all `/tmp/opencode/.../server.console.log`, `extent_write` count):
`183937Z-1600690`=1840, `190831Z-1602589`=440, **`211800Z-1653969`=0 (the only run with the 42 parks)**,
`002151Z-1750622`=841, others 0 (short/idle runs). So 0 is not a logging artifact: runs that triggered L3
writes logged them.

### E3. Metric evidence: the drain never processed an ack

`sglang:backuped_tokens_total` is created in the SAME `StorageMetricsCollector` as the present aux metric:
```
observability/metrics_collector.py:2088  self.backuped_tokens_total = Counter(name="sglang:backuped_tokens_total", ...)
observability/metrics_collector.py:2159  def log_backuped_tokens(...)
```
It is incremented only inside the ack drain:
```
unified_radix_cache.py:7443-7449   if log_metrics and self.enable_storage_metrics and self.storage_metrics_collector is not None:
unified_radix_cache.py:7448            self.storage_metrics_collector.log_backuped_tokens(operation.completed_tokens)
```
In all three scrapes (`/tmp/opencode/mam_metrics{,2,3}.txt`) `sglang:backuped_tokens_total` has **no
series at all** (only the HELP text of other metrics mentions it), while the same collector's
`sglang:hicache_prefetch_aux_alloc_failed_tokens_total` IS present (`543258.0 -> 556916.0`).
Same collector, same `enable_metrics=True` => the collector exists and emits; the absence means
`_drain_backup` never consumed an ack with `completed_tokens>0`. This is corroborated by
`hicache_dropped_tokens_total{mamba,host_pressure}` climbing `218 -> 234 -> 251` while
`hicache_backup_tokens_total{mamba}` is frozen at exactly the pool size `142.0`.

### E4. The in-run fallback release never fired

`_handle_storage_failure` (the only non-ack, non-detach in-run unpin) requires
`cc.storage_failure_reason is not None`:
```
unified_radix_cache.py:7975  def check_hicache_events(self)
unified_radix_cache.py:7978      if cc is not None and cc.storage_failure_reason is not None:
unified_radix_cache.py:7979          self._handle_storage_failure(cc.storage_failure_reason)
unified_radix_cache.py:7971-7973     for node_id, lock_params in list(self.ongoing_backup.values()):
unified_radix_cache.py:7972              self.dec_host_lock_ref(node_id, lock_params)
```
`storage_failure_reason` is set only by `_storage_thread_fatal` (`managers/cache_controller.py:587-602`),
which the hybrid `backup_thread_func` never calls (it has only `except Empty`, see E5). The failing log has
zero `storage failure`/`degrad`/`HiCache storage thread` lines. So the degraded-mode unpin never ran.

### E5. (b)/(c)/(d)/(e) rejected with `file:line`

- **(b) ACK produced but dropped:** cannot be the break. In the hybrid path the only ack enqueue is
  `hybrid_cache_controller.py:1332`, executed unconditionally right after a True `_page_backup`
  (`:1239`). There is no generation/ownership filter between production and enqueue. An exception between
  `:1239` and `:1332` would not "drop" the ack silently — it would propagate out (the hybrid function has
  only `except Empty` at `:1333-1334`), killing the thread (a distinct failure, see M2). Rejected as the
  *first* break; retained only as a mechanism candidate for why (a) happened.
- **(c) ACK enqueued but never drained:** rejected on reachability. `scheduler.py:6696`
  (`check_hicache_events`) is called from `_get_new_batch_prefill_raw` before any early return, and
  `_should_defer_prefill` (`scheduler.py:1489-1494`) is always False because
  `prefill_decode_interval=0`. The drain (`unified_radix_cache.py:8018-8037 -> 7546 -> 7033-7035`) runs
  every scheduler iteration, and `n_backup` is the MIN qsize (TP=1 here). Corroborated by E3: had any ack
  been enqueued, `sglang:backuped_tokens_total` would have a series. It has none.
- **(d) ACK filtered/rejected by a predicate:** rejected. The unpin pop at `unified_radix_cache.py:7135`
  is unconditional; `operation.id` equality is the only key. The generation/rank/durability predicates
  (`_t38c_mamba_rank_proof` at `:7073`, `advance_storage_persisted` at `:7229`) gate only promotion, not
  `dec_host_lock_ref`. `is_l3_durable`/`is_storage_persisted` never gate the pop.
- **(e) normal in-run drain structurally unreachable for Mamba:** rejected; the normal drain is structurally
  reachable and is the designed release. For Mamba (TP=1, non-MLA), `should_backup` returns True
  (`hybrid_cache_controller.py:1205-1212` explicitly special-cases `PoolName.MAMBA`), the Mamba transfer is
  built at `mamba_component.py:905-916`, and `backup_thread_func` runs on every rank
  (`hybrid_cache_controller.py:1227-1234`). What is missing is not reachability but an ack to drain — i.e.
  (a). This distinction is the reason (e) is not selected.

### E6. The pin is self-sustaining (why 128 accumulated)

`_write_backup_storage_node` marks the node `storage_written` at `unified_radix_cache.py:5010`; `collect_storage_gap`
walks past `storage_written` nodes (`unified_tree_core.py:2105-2106`). The mamba host-eviction flush
(`mamba_component.py:1044-1054, 1086-1087`) defers non-durable host checkpoints into
`write_backup_storage`, which arms a fresh pin. With acks never produced, each flush converts one more
evictable node into a permanently pinned, never-evictable node (`_host_evictable_signature` counts only
`host_lock_ref == 0` nodes, `unified_radix_cache.py:3683-3711`). Reclaim therefore returns 0
(`unified_radix_cache.py:6906`, `evict_host` at `:3977`), and the allocator's `alloc(1)` at
`mamba_component.py:842-848` fails -> the 42 parks. This is consistent with, and downstream of, verdict (a).

## Ranked candidate mechanisms for the break (why the backend produced no ack)

**M1 (top, accepted): a swallowed exception inside `_page_backup` converts a backup failure into a silent
no-ack.** `hybrid_cache_controller.py:1198-1199` wraps the entire KV + sidecar + group-commit sequence in
`except Exception: return False` with no logging. Candidate raise sites that are themselves silent or
log-free: `_resolve_sidecar_nonkv_derived_pool_transfers` raises `AssertionError` on a missing source
(`:1358-1361`); `batch_set_v2` does `self.registered_pools[transfer.name]` and would `KeyError` on an
unregistered pool (`extent_file_backend.py:1943`); `_write_pages_locked` silently returns False on
source/length mismatch (`:2273-2277`), unknown group (`:2283-2284`), or staged-slot conflict
(`:2297-2298`). This mechanism uniquely explains the combination of **zero commits AND zero diagnostic
lines AND no `storage_failure_reason`**. Accepted as the most probable.

**M2 (close second, accepted): the backup thread died silently.** The hybrid override
`backup_thread_func` (`hybrid_cache_controller.py:1233-1334`) has only `except Empty`; it does **not**
reproduce the base's `except Exception -> self._storage_thread_fatal(...)` (`managers/cache_controller.py:1458-1460`).
An exception anywhere in the per-op block (including the large `_t38c_*`/`ordered_key_set_digest`
introspection at `:1241-1331`) kills the daemon thread without setting `storage_failure_reason`, without a
log, and without degrading the scheduler. All later ops then sit unread in `backup_queue` and no ack is
ever produced. This also fits zero commits/no logs. It is indistinguishable from M1 without a live check.

**M3 (rejected): extent-backend capacity/geometry refusal.** A page larger than `extent_size`
(`extent_file_backend.py:2299-2306`) or a short pwrite (`:2867-2871`) logs a warning/error. The failing log
has zero such lines, and the Mamba page (51,511,296 B from the later run's `component=mamba keys_n=1
bytes=51511296`) fits inside `extent_size=67,108,864 B`. Disk watermark pressure
(`SGLANG_HICACHE_EXTENT_BACKEND_MIN_FREE_SPACE=50Gi`) does not refuse a write in code either —
`_select_gc_victims` (`:2593-2618`) only selects victims; it never returns a refusal. Rejected.

## Defects / blockers

1. **D1 first-break (this task): L3 backend produced no ack; failure is silent.** The pin acquired at submit
   (`unified_radix_cache.py:5004-5007`) has no in-run release unless an ack drains
   (`:7135`), storage is marked degraded (`:7971-7973`, never fired), or the backend is detached
   (`storage_attachment.py:395-399`). Two contributing observability defects were confirmed:
   - `hybrid_cache_controller.py:1198-1199` swallows all `_page_backup` exceptions with no log.
   - `hybrid_cache_controller.py:1233-1334` omits the base controller's fatal handler
     (`managers/cache_controller.py:1458-1460`), so a thread death is silent and never sets
     `storage_failure_reason`.
2. **No reproducible fix was applied (READ-ONLY).** This artifact names the break and the ownership/lifecycle
   repair direction only as a hypothesis.

### D1 repair direction — HYPOTHESIS ONLY (not a patch)
Minimal ownership/lifecycle repair: make the **absence of an ack a terminal, observable failure that releases
the pin through the existing ownership path**, rather than adding a new lifetime. Concretely:
- Restore the base controller's `except Exception -> _storage_thread_fatal` semantics in the hybrid
  `backup_thread_func` (`hybrid_cache_controller.py:1233-1334`), so any per-op exception sets
  `storage_failure_reason` and the already-existing `_handle_storage_failure`
  (`unified_radix_cache.py:7971-7973`) releases every `ongoing_backup` pin. That routes the release through
  the *existing* storage-failure ownership path, not a new timer.
- Make `_page_backup` failure carry a reason that is logged and surfaced (remove the bare
  `except Exception: return False` at `:1198-1199`), so the failure is attributable.
This is a repair of *when ownership ends* (on a terminal backend failure), not a new lifecycle.

**Explicit constraint:** a timeout / forced-unpin watchdog MUST NOT become the normal lifecycle. A periodic
"unpin anything older than T" sweeper would mask exactly the silence that caused this incident (it would
break the invariant that a pin is held iff an ack is genuinely outstanding, and would let an in-flight
backup be evicted before it is durable). An orphan-pin **invariant guard** (detect and report a pin whose
operation can no longer complete) is acceptable only as a last-resort safety net, and must not be the path
that makes backups durable or frees pins in normal operation.

## Whether the ACK-drain path is reachable for Mamba, and caller cadence

**Reachable, and it is the designed release path.**
- Caller: `managers/scheduler.py:6695-6696`, `self.tree_cache.check_hicache_events()` at the top of
  `_get_new_batch_prefill_raw`.
- Cadence: every scheduler iteration that calls `get_next_batch_to_run` -> `get_new_batch_prefill` ->
  `_get_new_batch_prefill_raw`. `_should_defer_prefill` (`scheduler.py:1489-1494`) returns False because
  `prefill_decode_interval == 0` (server args in the failing run's `server_args`), so it is not skipped.
- From `check_hicache_events` (`unified_radix_cache.py:7975`): `_sync_hicache_ready_counts` (`:8009`) reads
  `cc.ack_backup_queue.qsize()` and MIN-reduces across ranks; then
  `_drain_storage_control_queues_impl` (`:8029`) -> `_drain_backup` (`:7033`) pops `n_backup` items and
  reaches the unconditional unpin at `:7135`.
- Mamba is not excluded from the backup queue: `should_backup` explicitly returns True for
  `PoolName.MAMBA` (`hybrid_cache_controller.py:1205-1212`), and the hybrid `backup_thread_func` is used
  (the controller is `HybridCacheController`; log line "Attached hybrid pool stack ... pools=KV + MAMBA").
- The failure is therefore an empty queue (no ack produced), not an unreachable drain. Corroborated by E3
  (`sglang:backuped_tokens_total` has no series).

## Remaining claims / exclusions

- **R1 (NOT established): the concrete reason the backend committed nothing.** M1 (swallowed exception) and
  M2 (silent thread death) are both consistent with the frozen evidence; they cannot be separated without a
  live probe. This does not affect the (a) verdict — both are on the "backend produced no ack" side.
  Minimal distinguishing live experiment (NOT run; read-only constraint): start the frozen tree with the
  existing zero-code diagnostic gates enabled and read, not a new instrumentation path:
    * gate files: `/tmp/t38c-durable-trace` (enables `_t38c_durable_log`, `hybrid_cache_controller.py:75-140`)
      and `/tmp/t38c-on` (enables `_t38c_log`, `hybrid_cache_controller.py:61-72`); output file
      `/tmp/t38c-probe.log`.
    * Distinguishing result: `evt=backup_submit` (`unified_radix_cache.py:4983-5003`) with NO matching
      `evt=backup_ack_enqueue` (`hybrid_cache_controller.py:1289-1331`) and NO `evt=batch_set_result`
      (`extent_file_backend.py:2007-2015`) for the same `operation_id` => M1/M2 on the controller/backend
      hop. If `batch_set_result result=false reason=...` DOES appear => the backend executed and returned a
      refusal (M3 class), which would move the first break to a backend-side failure with a reason.
      A live thread-alive check (e.g. `threading.enumerate()` name `backup_thread_func` via an admin probe)
      would separate M1 from M2; there is no existing no-code gate for this, so it would require a debugger
      attach or a new probe and is therefore out of scope.
- **R2 (NOT established): exact per-node pin-holder attribution.** Volume evidence (E1: 128 mamba
  lock-release mutations at shutdown vs. <=40 load-back tokens and 13 prefetches) strongly favors
  `ongoing_backup`, but there is no per-node `host_lock_ref` telemetry in the frozen tree.
- **R3 (excluded from scope by the task):** D2 unit mismatch (`unified_radix_cache.py:5457` prefix-token
  units vs. `scheduler.py:3764` slot units) is owned by the concurrent `MAMBA-D2-UNIT-FIX-R2` agent and is
  not re-litigated here.
- **R4 (excluded):** no claim that increasing `--hicache-size`, `max_mamba_cache_size`, or changing the split
  ratio fixes anything; no claim that the extent backend is defect-free, only that in this run it produced
  no ack and left no refusal/error trace.
- **No files other than this artifact were written; the ledger was not edited.**

## Terminal state: DONE

Primary verdict **(a) ACK never produced by the L3 backend**. First break at the backend hop:
`hybrid_cache_controller.py:1239-1240` requires a True `_page_backup` before the only ack enqueue
(`:1332`); the failing run shows zero successful L3 commits (0 `extent_write`; manifest `entry_count=0,
checkpoint_lsn=0`; data file 0 allocated bytes). (b)/(c)/(d)/(e) rejected with `file:line`. The reason the
backend produced no ack is established only as a ranked hypothesis (M1 > M2 > M3, R1).
