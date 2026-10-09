# phase2-hicache-design-coder-fbe-e1

## status
done

## artifacts
- `python/sglang/srt/mem_cache/unified_cache/components/mamba_component.py`
  (`drive_host_eviction`, :849-936): added flush-before-evict (FBE) — a mamba
  host victim that is not yet L3-durable is spared this round, its node id is
  queued, and after the walk `self.cache.write_backup_storage(node_id)` is
  called (which pins the host copy to the storage ack). No other production
  file changed.
- `3090-dev/test_fbe_flush_before_evict.py` (new): 8 unit tests driving the
  real `MambaComponent.drive_host_eviction` / `evict_component` against a real
  `UnifiedTreeCore` + real host LRU.

## evidence

### Root-cause mapping (coder-l0-loss-e1 Q4: HOST->L3 break hop)
- Old code (pre-fix): `drive_host_eviction` evicted the LRU-oldest mamba host
  entry unconditionally (`_evict_host_leaf` / `_evict_component_and_detach_lru`
  HOST) even when its L3 sidecar was not yet persisted. The deferred L3 persist
  (`write_backup_storage`) then hit the BACKUP_STORAGE gate
  (mamba_component.py:754 `cd.host_value is None -> return None`) and silently
  dropped the sidecar -> device+host+L3 all lost -> 0 usable.
- New code: a mamba host victim is spared when
  `enable_storage and host_value is not None and host_lock_ref == 0 and not
  is_l3_durable(x.id)`. `write_backup_storage` pins via `inc_host_lock_ref`
  (unified_radix_cache.py:2225), which removes the node from the host LRU
  (mamba_component.py:449-452) so the next eviction round skips it; the ack
  path `_drain_backup` (unified_radix_cache.py:3557-3560) calls
  `dec_host_lock_ref`, which re-inserts it (mamba_component.py:479-483) once
  durable. This is the decision (a) invariant + (b) evict-before-flush =>
  flush-before-evict implementation; (c) read-side partial fallback NOT done;
  eager D->H persist NOT done.

### Design decision vs. inline flush (reentrancy / cursor safety)
- Flush is deferred to AFTER `cursor_end()` (session mode). An inline
  `write_backup_storage` may reenter this walk under host pressure
  (write_backup_storage -> D->H backup -> _execute_kv_backup -> evict_host ->
  tree_core.drive_host_eviction). A nested `cursor_begin()`/`cursor_end()`
  would clobber the outer walk's active cursor (cursor sentinel `lru_prev`
  becomes None after nested cursor_end -> outer cursor_next derefs
  None.component_data -> AttributeError). Post-walk flush removes this hazard.
- Victim pin (established synchronously inside write_backup_storage) removes
  the node from the host LRU before any nested walk could see it, so no
  re-entrant eviction of the victim is possible.

### Pin/release semantics confirmed
- `inc_host_lock_ref` (unified_tree_core.py:660-668) -> mamba
  `acquire_component_lock(lock_host=True)` increments `host_lock_ref` and
  removes from host LRU (mamba_component.py:448-453).
- `dec_host_lock_ref` (unified_tree_core.py:670-677) -> mamba
  `release_component_lock(lock_host=True)` decrements and re-inserts to MRU
  when ref reaches 0 and value is None and host_value present
  (mamba_component.py:477-483).
- Cursor walkers skip `host_lock_ref != 0` nodes:
  `cursor_next(host_lock=True)` (unified_tree_core.py:264-277) and
  `get_prev_no_host_lock` (unified_tree_core.py:357-368).

### `is_l3_durable` predicate (node-level, correct)
- `is_l3_durable` = `storage_persisted or storage_restored`
  (unified_tree_core.py:2144-2151). The BACKUP_STORAGE sidecar gate reads THIS
  node's host_value, so node-level durability is exactly the condition that
  the sidecar for this node's L3 write was/not carried.
- Gate on `tree_core.enable_storage` (live mirror, unified_radix_cache.py:4374):
  without it, is_l3_durable is always False outside HiCache and NO mamba host
  would ever be evictable. Pre-fix behavior preserved when storage disabled.

### Unit tests (3090-dev/test_fbe_flush_before_evict.py) — real MambaComponent
- `test_non_durable_internal_victim_spared_and_flushed`: non-durable internal
  -> write_backup_storage([id]) called once, host_value retained, still in LRU.
- `test_non_durable_host_leaf_victim_spared_and_flushed`: same for the atomic
  host-leaf path.
- `test_durable_internal_victim_evicted_without_flush`: durable -> evicted,
  no flush.
- `test_durable_host_leaf_evicted_atomically_without_flush`: durable host leaf
  -> atomic eviction, no flush.
- `test_storage_restored_counts_durable`: storage_restored counts as durable.
- `test_pinned_victim_spared_without_duplicate_flush`: host_lock_ref != 0 ->
  spared, no duplicate flush / no double pin.
- `test_storage_disabled_evicts_without_flush`: enable_storage False ->
  pre-fix eviction, no flush.
- `test_pin_then_ack_returns_victim_to_eviction_pool`: spared+flushed -> pin ->
  ack release -> durable -> evicted, no second flush.

All 8 pass (Ran 8 tests ... OK). Real MambaComponent loaded via
object.__new__ (skips the HybridReqToTokenPool-heavy __init__); real
UnifiedTreeCore + real host LRU cursor; stub FULL component for the host-leaf
atomic path.

### Regression (one process at a time, /home/charles/sglang-venv/bin/python3)
- 3090-dev/test_storage_regression.py: Ran 99 tests ... OK.
- 3090-dev/test_hicache_restore.py: Ran 69 tests ... OK.
- 3090-dev/test_hicache_restore_scheduler_feed.py (needs PYTHONPATH=python):
  Ran 7 tests ... OK.
- test_partial_restore_fallback_unit.py does not exist in the repo (referenced
  in dispatch; checked, absent).
- py_compile: mamba_component.py and test_fbe_flush_before_evict.py both OK.

## summary
Implemented the frozen-scope FBE invariant in
`MambaComponent.drive_host_eviction`: a mamba host victim that is not
L3-durable (and not already pinned) is spared and queued; after the walk its
`write_backup_storage` is triggered, which pins the host copy to the storage
ack, so the next eviction round skips it and only after durability (ack
release) is it evicted. This closes the gate2 HOST->L3 break hop: the mamba
sidecar is persisted before the host copy can be reclaimed. Flush is deferred
post-cursor_end to avoid a reentrant-walk cursor corruption. Minimal diff: one
file, one method; read path / BACKUP_STORAGE gate / eager persist untouched.
8 new unit tests + 175 regression tests green.

## followups
- Integration/end-to-end (tester scope): a live run that writes one L0 mamba
  chain, demotes it, forces mamba host pressure, and confirms the L0 mamba
  sidecar is now L3-durable before any host eviction (gate2 restore usable
  > 0). Counter/observability suggestion: a host-mamba eviction counter would
  make the spared-vs-evicted split visible (P3 read-only instrumentation;
  not added here per frozen scope).
- The dispatch referenced `3090-dev/test_partial_restore_fallback_unit.py`; it
  does not exist in this repo (the style-alignment reference tests present are
  test_storage_regression.py / test_drain_reentry.py). No action taken.

## open_issues
- None introduced. Pre-existing: the FBE flush is best-effort in the sense that
  write_backup_storage returns early if storage is degraded
  (`cc.storage_failure_reason is not None`, unified_radix_cache.py:2170-2173) —
  in that case the victim is still spared this round (host_value retained) and
  is not evicted, which is the safe direction (no data loss; the host copy
  survives until storage recovers). Noted for completeness, not a defect.
