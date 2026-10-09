# phase2-hicache-design-coder-l0-loss-e1

## status
done

## artifacts
- Analysis only, no code change. Read: mamba_component.py, full_component.py,
  unified_tree_core.py, unified_radix_cache.py, cache_controller.py,
  hybrid_cache_controller.py, pool_host/group.py, l2_transfer.py,
  scheduler.py (restore/prefetch gate + _final_storage_survivability),
  gate2_load.py + gate2-saturation report.

## evidence (verified code path, with line numbers)

### D→H / H→L3 backup construction (Q1)
- `_build_backup_spec` (unified_tree_core.py:2034-2050): iterates all
  components (skips base). For mamba: skip if `host_value` already set, else
  `build_hicache_transfers(node, BACKUP_HOST)`.
- `build_hicache_transfers(BACKUP_HOST)` (mamba_component.py:711-720): returns
  `PoolTransfer(device_indices=cd.value)` **only if `cd.value is not None`**.
  A node whose mamba device value is already None produces NO host backup.
- `_execute_and_commit_kv_backup` (unified_radix_cache.py:1595-1613) →
  `_execute_kv_backup` → `cache_controller.write(device_value, extra_pools=aux)`
  → HybridCacheController.write (hybrid_cache_controller.py:327-359) →
  `resolve_host_transfers` (pool_host/group.py:139-238) allocates the mamba
  host slots and fills `transfer.host_indices`.
- Commit: `commit_backup` (unified_tree_core.py:2377-2401) →
  mamba `commit_hicache_transfer(BACKUP_HOST)` (mamba_component.py:790-794):
  `if cd.host_value is None: cd.host_value = transfers[0].host_indices.clone()`.
- Conclusion: **mamba BACKUP_HOST is constructed+executed for EVERY node backup
  whose mamba device value is present, leaf or internal alike — the gate is
  `cd.value is not None`, NOT leaf-only.** But a node whose mamba `value` is
  already tombstoned (None) is silently skipped (nothing to copy).

### write_back removes the D→H write-through on insert (Q1/Q4)
- `_inc_hit_count_and_check` (unified_tree_core.py:886-899): `if
  self.is_write_back: return False` — so **insert never issues a host backup**
  under write_back. The only D→H backup routes in write_back are (a) leaf
  eviction BackupKV (`_evict_device_leaf` → `_build_backup_kv_action`,
  unified_tree_core.py:1296-1323, 2337-2353) and (b) L3-persist gap-fill
  (`write_backup_storage`, unified_radix_cache.py:2120-2165).

### mamba BACKUP_STORAGE gate (Q3)
- mamba_component.py:752-763: `if cd.host_value is None or not node.hash_value:
  return None`. So **an L3 write carries the mamba sidecar ONLY if the node's
  mamba host_value is still present at write time.** If the mamba host copy was
  already evicted, the L3 write proceeds with KV but drops the mamba sidecar
  silently.

### internal-node mamba device eviction is a bare tombstone (Q2)
- mamba `_evict_device_next_node` (mamba_component.py:401-423): an internal
  node (not a D-leaf) → `_evict_component_and_detach_lru(target=DEVICE)` →
  `evict_component` (mamba_component.py:321-357) sets `value=None` with **no
  BackupKV, no host backup**. The mamba is lost from device immediately.

### leaf demote DOES host-backup mamba (Q4 primary path)
- write_back D-leaf demote: `_evict_device_leaf` (line 1305-1316) → BackupKV →
  `_execute_and_commit_kv_backup(write_back=True)` (back up KV + mamba sidecar)
  → `_demote` (unified_tree_core.py:1694-1720) which cascade-evicts the node's
  device mamba (leaf: all priority 0) and moves the mamba to the HOST LRU
  (`_for_each_component_lru(..., target=HOST, insert_mru)`).
- So after a Full-leaf demote, L0's mamba lives on HOST (host_value set).

### mamba HOST eviction is oldest-first and a SEPARATE pool from device
- `drive_host_eviction` (mamba_component.py:849-901): walks
  `host_lru_lists[MAMBA]` from LRU tail (oldest), tombstones internal-node
  mamba host (`target=HOST` → `evict_component` sets `host_value=None`).
- The device mamba gauge (`mamba_evictable_tokens`, 32/106 in gate2) does NOT
  reflect the HOST mamba pool; they are separate pools with separate LRUs.
- `hicache_dropped_tokens_total pool=mamba` counts only host-pressure device
  drops (`_record_dropped_tokens`, unified_radix_cache.py:1009-1024), not host
  eviction. So "dropped(mamba)=0" does not rule out mamba HOST eviction.

### match boundary is gated node-by-node by the mamba validator (Q4)
- `_match_prefix_helper` (unified_tree_core.py:706-791): `_update_best_if_valid`
  advances `best_match_node` only where ALL validators pass; mamba validator
  (mamba_component.py:141-152) = `value is not None OR host_value is not None`.
  If a boundary node's mamba is gone on both device and host, the match boundary
  stops at its parent. Full KV of that node is not credited to a mamba request
  whose boundary needs the node's own mamba state.

### `_final_storage_survivability` checks only the Full KV anchor (Q3)
- scheduler.py:3249-3262: returns "host" when `last_host_node` exists, is
  host-backed (`is_l3_durable` false). It does NOT inspect the mamba checkpoint
  at all. So "survivability=host" is fully consistent with the mamba being gone
  — it labels the surviving Full KV host backup.

## summary

### Q1 — backup op construction & whether mamba BACKUP_HOST always runs
Every node backup builds the mamba sidecar via `_build_backup_spec` →
`build_hicache_transfers(BACKUP_HOST)` and executes it through
`cache_controller.write(..., extra_pools=aux_xfers)` →
`resolve_host_transfers` → `commit_backup` sets `host_value`. **The mamba
transfer is skipped only when `cd.value is None`** (device tombstoned) — not
leaf-specific. So: yes, mamba is D→H backed up whenever the node still holds a
device mamba value at backup time.

### Q2 — L0-specific structural explanation
Mamba is leaf-only by design: `redistribute_on_node_split`
(mamba_component.py:309-319) clears the new parent's value+host_value and keeps
mamba on the child, whereas Full SPLITS its value between parent and child
(full_component.py:138-154). In a linear grow chain L0⊂L1⊂L2⊂L3, each level's
mamba checkpoint is an independent SSM snapshot at that level's boundary, and
**L0's is the oldest — hence the LRU tail of the mamba host LRU, first to be
host-evicted.** Splits per se do not destroy L0's mamba (it stays on the child),
but they do make L0's mamba an *internal*-node mamba, which is exactly the node
class the bare-tombstone device path and the oldest-first host path target
first. L0 is not special in the tree topology beyond being the oldest boundary.

### Q3 — survivability=host yet L3 storage_hit_count=0
`_final_storage_survivability` labels the anchor's **Full KV** host backup
(scheduler.py:3257-3262), which survives (it is a different pool/LRU from
mamba). `storage_hit_count=0` comes from the L3 KV page query
(`_storage_hit_query`, cache_controller.py:1291-1314) over KV hashes; the L0
chain KV is not L3-durable (write_back writes L3 only on eviction / frontier
wait, and the persist was deferred/incomplete). Independently, the mamba
sidecar was never persisted because the BACKUP_STORAGE gate (mamba_component.py:
754, `host_value is None → return None`) saw the already-evicted mamba host
copy. Both facts coexist: the anchor's Full KV host backup survives while the
chain's KV+mamba were never durably in L3 and the mamba host copy was evicted.

### Q4 — ROOT CAUSE
**L0's mamba checkpoint is lost at the HOST→L3 hop.** Mechanism:
1. The L0 chain's Full KV is demoted (device→host). The demote BackupKV
   (unified_tree_core.py:1305-1316 → 1580-1613) host-backs up L0's mamba
   (host_value set) and moves it to the mamba HOST LRU, oldest-first.
2. `drive_host_eviction` (mamba_component.py:849-901) evicts the LRU-oldest
   mamba host entry — L0 — setting `host_value=None`. The device mamba is
   already gone (cascade on demote); the device mamba gauge (32/106) does not
   reflect this because host mamba is a separate pool.
3. When the deferred L3 persist (`write_backup_storage`, triggered by
   `writing_check` flush or the frontier-wait self-arm) finally writes the L0
   chain, `build_hicache_transfers(BACKUP_STORAGE)` (mamba_component.py:752-763)
   sees `host_value is None` and **silently drops the mamba sidecar**; the KV
   may also be missing/incomplete because the persist never completed.
4. Result: L0 mamba is gone from device (demoted) + host (evicted) + L3
   (sidecar gate skipped). The match validator (`value=None AND host_value=None`)
   stops the boundary at L0's parent → L0 restore = 0 usable → full recompute.
   L1/L2 mamba host_values are younger (MRU) and still present → they survive.

Consistency with the three phenomena:
- **L0-specific**: L0 is the oldest mamba boundary → LRU tail → first host
  eviction victim; L1/L2 younger → survive. `final_storage_survivability=host`
  confirms the Full KV host survived while the mamba did not.
- **pool unsaturated**: `mamba_evictable_tokens` (device gauge) and
  `dropped(mamba)=0` (host-pressure device drops only) neither reflect the HOST
  mamba pool, where the eviction actually happens.
- **survivability=host yet L3 no key**: survivability labels the surviving Full
  KV host, not the mamba; the L3 KV query returns 0 because the L0 chain was
  never durably persisted and the mamba sidecar was gated out at write time.

Precise break hop: **HOST → L3** (and the host copy was evicted before its L3
persist). The L0 mamba D→H backup (device→host) succeeds; the loss is the host
copy being evicted (oldest-first host LRU) before the deferred L3 persist can
write its sidecar.

## followups (open; would need 3090 evidence to disambiguate trigger, not to confirm root cause)
1. Confirm `drive_host_eviction` actually fired for mamba host entries at
   gate2: add/read a host-mamba eviction counter or the `_evict_component`
   HOST-path trace for the lost L0 node. The device gauge cannot show it.
2. Confirm the L0 chain's `write_backup_storage` timing vs the restore: was the
   L3 persist deferred (in `_pending_storage_writes`) and never flushed before
   the restore? Check `_storage_persist_skip_count` / `pc_write_seed` for the
   lost L0 vs a surviving L1.
3. Optional 3090 minimal experiment (one engine, fresh namespace, SIGTERM):
   write one L0 chain, demote it, force host mamba pressure to evict the L0
   host copy, then restore L0 — expect full miss with survivability=host. This
   isolates the host-eviction trigger from any other load factor.
4. Alternative (secondary) trigger to exclude: internal-node mamba device
   tombstone (`_evict_device_next_node`, mamba_component.py:412-423) removing
   L0's device mamba with no host backup under a CoW alloc burst — would also
   produce the signature but without a host copy ever existing.

## open_issues (fix direction — NOT implemented)
- write_back must not silently lose an internal/oldest mamba checkpoint.
  Candidates (for design decision, not this task):
  (a) host-evicting a mamba host_value that is not yet L3-durable should either
      block until its L3 sidecar persists, or the L3 persist must snapshot the
      mamba sidecar before/at D→H time rather than reading the current
      host_value (mamba_component.py:754 gate).
  (b) the deferred L3 persist (`_pending_storage_writes` /
      `_flush_pending_storage_writes`, unified_radix_cache.py:2097-2118) should
      be flushed before any mamba host eviction of the same node, or a demote
      should eagerly persist the chain it just backed up.
  (c) read-side: a restore whose mamba boundary is missing should degrade to a
      partial (KV prefix + recompute tail) instead of a hard 0-hit cliff, since
      the sibling L1 hit proves the KV prefix is recoverable.
- Gate2 is a FAIL under the frozen criteria; the policy changes are gate-3+
  work and remain out of scope here (no code/strategy changed).
