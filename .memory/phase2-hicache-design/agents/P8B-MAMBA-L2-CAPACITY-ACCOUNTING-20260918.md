# P8B-MAMBA-L2-CAPACITY-ACCOUNTING-20260918

Status: DONE

Task: READ-ONLY capacity accounting + root-cause adjudication of the production Mamba L2
HOST_ALLOC tail. Decide exactly one of (A) capacity insufficient, (B) split-ratio wrong,
(C) allocator reclaim/lifetime bug, and name ONE minimal lever. Enforce unit discipline on
`required 3436-3556` (corrected: 484-65347) vs `free_before=0` vs
`hicache_mamba_host_usable_tokens=142`.

Scope: read-only code + log investigation against the frozen prod tree
`/opt/sglang/local-prod-v1.2.1-candidate` (source_head `4f41f5bab562b99562f30c67540eb05344d13637`,
deployment_manifest_digest `262a9362e345df15d93049301d2b0e60990ba65d80c3bbc5209fb4cdab140e2d`,
SGLANG_RUN_ID `prod-20260917T211800Z-1653969`) and worktree HEAD
`ea7b0e9b445e23852cd900ee0abe9e2a1eab17ee` (decisive lines verified identical). No restart, no
parameter change, no code change, no GPU, no server launch. Only this artifact was written.

## Result

**Verdict: (C) allocator reclaim / lifetime bug.** Not capacity, not split ratio.

**Single minimal lever:** fix the **mamba host-pin lifetime** — the host-lock pin acquired when an
L3 backup op is submitted and released only on its ack drain. Decisive line (prod tree, = worktree):

```
src/python/sglang/srt/mem_cache/unified_radix_cache.py:5006
        self.ongoing_backup[operation_id] = (
            node_id,
            self.inc_host_lock_ref(node_id).to_dec_params(),
        )
```

Release exists only on ack drain (`:7135`) / storage-failure (`:7971`) / detach
(`storage_attachment.py:395-399`). No in-run watchdog releases a pin whose ack never drains, so a
pinned mamba host node is never evictable again.

**Coupled secondary defect (does not change the verdict, must not be conflated with the lever):**
the wake predicate compares a **token** quantity to a **slot** quantity, making `WAIT_CAPACITY`
permanently unsatisfiable. Decisive lines:

```
src/python/sglang/srt/mem_cache/unified_radix_cache.py:5457
            required_aux_units.setdefault(failed_pool, len(prefetch_key))
src/python/sglang/srt/managers/scheduler.py:3764
            if free + evictable < required:
```

`required_aux_units["mamba"]` is built at `:5451-5457` from `len(transfer.host_indices)` and falls
back to `len(prefetch_key)` — i.e. **prefetch prefix tokens** — while `free_units`/`evictable_units`
are **mamba host slot counts** (pool total 142). Observed `required` range across the 42 retries is
**484..65347**.

## Evidence

### E1. Unit derivation (resolves the apparent contradiction)
- `prepare_prefetch` (`unified_cache/components/mamba_component.py:836-849`) allocates **exactly 1
  slot**: `host_pool_group.alloc(1, pool=PoolName.MAMBA, reclaim=lambda size: cache.evict_host(size, ComponentType.MAMBA))`;
  `alloc_failed=True` on `None`.
- `HostPoolGroup.alloc` (`pool_host/group.py:108-127`) **does** invoke reclaim once then retries:
  `indices = alloc_fn(need); if indices is None and reclaim is not None: reclaim(need); indices = alloc_fn(need)`.
  So reclaim is wired; it simply reclaimed `0`.
- `required_aux_units` (`unified_radix_cache.py:5451-5457`) is in **prefix-token** units; the
  alloc-failure metric bumps `len(prefetch_key)` (`:5446-5448`).
- `hicache_mamba_host_usable_tokens=142` is the host pool total. Mamba **device** gauges
  (`mamba_available/evictable/used_tokens`) come from `mamba_allocator.available_size()` /
  `mamba_pool.size` (`managers/scheduler_components/pool_stats_observer.py:240-300`) and are
  **not** host occupancy — device pool is 48→49 slots.
- Pool construction: `hybrid_pool_assembler.py:134-147` `_split_hicache_size` splits proportional
  to device-pool **bytes** (call sites `:360-362`, `:710-714`); `pool_host/base.py:151-159`
  `size = int(host_size*1e9 // size_per_token)`, `page_num = size//page_size + 1`.
  32×2.524/11.114 = 7.267 GB → 141 → **142** slots. Console: `Allocating 7.31 GB host memory for
  hierarchical Mamba cache (layout=page_first).` (21:19:55).

### E2. The 42 parks are all "mamba host pool full and fully pinned"
All 42 `restore_host_alloc_retry_result` events (21:44:08 → 23:04:49):
- `failed_domains=("mamba",)` ×42; `retry_outcome="forfeited_alloc_failed"` ×42;
  `captured_generations.mamba == 12` ×42.
- mamba `free_before=0`, `evictable_before=0`, `reclaimed=0`, `alloc1=None`, `alloc2=None` ×42.
- `required` ∈ {484,575,802,910,1859,2697,3103,3131,3190,3224,3288,3436,3470,3511,3549,3556,3595,
  3630,3646,3715,3896,4089,4352,4813,8361,9299,12187,47541,57697,58951,62040,62681,62800,65347}.
- 303 `restore_host_alloc_wake_decision`: `decision="hold_no_generation"` ×261, `release` ×42,
  `retry_skip=true` ×303, `free_units={mamba:0}`, `evictable_units={mamba:0}`.

A failed allocation that asks for **1 slot** cannot be a shortage of 142 slots. Capacity is not the
binding constraint; reclaimability is.

### E3. The one-way-fill / pin signature (metric + generation evidence)
- `hicache_backup_tokens_total{mamba}` = **142** in all three scrapes (`/tmp/opencode/mam_metrics*.txt`),
  frozen at exactly the pool size, while `hicache_dropped_tokens_total{mamba,host_pressure}` climbs
  **218 → 234 → 251**. Host pool filled once to the brim and never recycled.
- `hicache_mamba_host_usable_tokens` = 142 in all three scrapes.
- `hicache_backup_tokens_total{kv}` keeps growing (718490 → 718490 → 777375), so the D->H ack
  pipeline for KV is alive; mamba's is the one wedged.
- All 64 `host_allocability_change` events parsed. Mamba generation advanced 0→12 only via
  `queued_release_drain` (12 events, `returned_units` 1-2 each, `evictable_after` stayed 0) between
  21:22:15 and 21:40:46. Generation then **froze at 12** for the entire retry window (21:44→23:04)
  and only moved at shutdown: 23:06:30 `lock_release_evictable` 12→28 (evictable 0→16), then a
  coalesced 139→140 (`evictable_after=128`, `telemetry_coalesced_mutations=111`,
  `telemetry_mutation_count=128`).
- The gen-freeze is robust to the telemetry emit cap: `_bump_host_allocability`
  (`unified_radix_cache.py:3729-3845`) increments the generation **before** the emit cap, and the
  `returned_units<=0` early return is bypassed for `cause=="lock_release_evictable"` (`:3753`).
  So 128 nodes were truly pinned, and truly unpinned only at shutdown.

### E4. Pin-source volume accounting
The 23:06:30 unlock is consistent with the atexit/shutdown teardown:
`unified_radix_cache.py:7644-7652 shutdown()` → `_release_all_load_backs(cause="shutdown")`
(`:4475-4481`) then `storage_attachment.shutdown()` → `detach()` →
`_release_pending_storage_ops` (`storage_attachment.py:349-399`) which pops `ongoing_prefetch`
anchors and `ongoing_backup` entries and calls `dec_host_lock_ref`. The mass unlock is emitted by
`dec_host_lock_ref` → `_bump_changed_host_allocability(..., "lock_release_evictable")`
(`unified_radix_cache.py:3346-3353`).

Pin sources by volume:
- `ongoing_load_back`: `load_back_tokens_total{mamba}` = 38-40 tokens over the run; mamba sidecar is
  1 token/node, so ≤ ~40 nodes.
- prefetch anchors (`:5408`): `prefetch_issued` ×13.
- `ongoing_backup` (`:5006`): the only source with volume able to account for the majority of the
  128 pinned nodes.

Neither the absence of a `storage_failure` log (searched: none) nor any error/warning indicates the
backup thread died; `_handle_storage_failure` (`:7950-7973`) never fired. The observable L3 state
is consistent with acks simply never draining: `sglang:backuped_tokens_total` has **no series** in
any scrape (only HELP/TYPE docs), while `hicache_prefetch_aux_alloc_failed_tokens_total` is present;
and the L3 extent store is a 64 GiB sparse file with only **40 K actual bytes**
(`/data/l3/prod-20260917T211800Z-1653969/`, manifest 20604 B, `.wal.1` 28 B, `.wal.current` 2 B).
D->H bytes (20 GB) do not imply L3 persist.

### E5. Reclaim path and eviction trigger are correct code, wrong outcome
- `_host_evictable_signature` mamba branch (`:3683-3711`) counts nodes in `host_lru.cache.values()`
  with `host_lock_ref == 0 && host_value is not None` — i.e. a pinned node is invisible to reclaim.
- `cursor_next(host_lock=True)` / `get_lru_no_host_lock()` (`unified_tree_core.py:274-289`, `:386`)
  skip `host_lock_ref>0` nodes.
- `drive_host_eviction` is overridden by Mamba (`mamba_component.py:1002-1087`); its `deferred_flush`
  path at `:1084-1087` calls `cache.write_backup_storage(node_id)` for non-durable mamba host
  checkpoints, and `_write_backup_storage_node` (`:4837+`, pin at `:5006`) submits the L3 write.
  So the eviction loop itself drives new pins while pinned nodes are already non-evictable: a
  self-sustaining pin-fill with no in-run release.

### E6. Split ratio is exonerated
`hicache_size=32` GB SI, `hicache_ratio=2.0`, split proportional to device-pool bytes
(`hybrid_pool_assembler.py:134-147`). Mamba received 7.267 GB → 142 slots, KV 24.73 GB → 1,509,560
tokens. The failing request needed 1 mamba slot. Even a "perfect" split cannot help an allocation
whose blocker is zero reclaimable slots among an already-full pool.

## Defects (established)

1. **D1 (root cause of alloc failure): mamba host-pin lifetime leak.**
   Pins acquired at `unified_radix_cache.py:5006` for in-flight L3 backup ops are released only by
   ack drain / storage failure / detach; with L3 acks not draining in-run, 128 mamba host nodes stay
   pinned, `evictable=0`, `evict_host(MAMBA)` reclaims 0, `alloc(1)` fails, and the device pool
   thrashes (`dropped_tokens{mamba,host_pressure}` climbing).
2. **D2 (liveness / permanent park): unit mismatch in the wake predicate.**
   `unified_radix_cache.py:5457` puts prefix-token units into `required_aux_units`, compared against
   slot units at `scheduler.py:3764`. Even with D1 fixed, `free+evictable=0 < 1` still holds during
   contention, so the park is not self-healing on the generation counter alone.

## Remaining claims / exclusions / open issues

- **Open issue (does not change the verdict): exact pin-holder attribution.** Volume evidence
  strongly favors `ongoing_backup`, but no per-node `host_lock_ref` telemetry exists and the durable
  logger (`_t38c_durable_log`) gates (`/tmp/t38c-durable-trace`, `/tmp/t38c-on`) were absent, so
  `backup_submit`/`backup_ack_drain` events were not emitted. `ongoing_load_back` (≤40) and prefetch
  anchors (13) are individually too small but are not excluded as contributors.
- **Why L3 acks do not drain is not proven** (blocked extent backend write vs. ack queue never
  serviced). `sglang:backuped_tokens_total` absent in all scrapes and the near-empty L3 data file
  are consistent with (not proof of) non-completion.
- **Excluded from scope:** no restart, no parameter change, no code change, no GPU, no server launch;
  no durable tracing was enabled. The cancelled 48→56→64 sweep is out of scope and remains cancelled.
- **Not claimed:** that increasing `--hicache-size` or `max_mamba_cache_size` fixes anything; that the
  L3 backend is defective (only that its acks are not observed to drain).
- The `t38c` durable-log gate absence means "no backup events in the log" is **not** evidence of
  absence; this was respected in the analysis.

## Terminal state: DONE

Verdict (C); single lever = mamba host-pin lifetime, decisive line
`unified_radix_cache.py:5006` (release `:7135`/`:7971`/`storage_attachment.py:395-399`);
coupled units defect at `unified_radix_cache.py:5457` + `scheduler.py:3764`.
