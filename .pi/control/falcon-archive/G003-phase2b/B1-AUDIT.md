# Phase 2B B1 audit

## Reference lineage

The target fork must use the local 3090 HiCache lineage, not upstream main as a replacement. The sibling reference checkout is:

```text
/home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt
branch: 3090-24g-hicache
HEAD: c72002ba14
```

Relevant HiCache lineage commits include:

```text
54c394a2e1  b1-hicache experimental hybrid HiCache engine and probes
4f06324468  write_back continuity / anchor-to-leaf L3 chain
8b3dca9674  backup-failure drain/retry eviction handling
2bdfcb5327  defer L3 persist out of ack drain
cd6c7d4c27  defer persist flush past demote
caeadcf492  skip stale L3 persists for deleted nodes
f3fffa7f09  restore retry/frontier wake, promotion admission, durability state machine
```

The target and reference source hashes match for the central runtime files:

```text
python/sglang/srt/mem_cache/unified_radix_cache.py
python/sglang/srt/mem_cache/unified_cache/unified_tree_core.py
python/sglang/srt/mem_cache/hybrid_cache/hybrid_cache_controller.py
python/sglang/srt/managers/scheduler.py
```

The only hash difference among this checked set is `server_args.py`, where the
target contains the Falcon-H1 prefill safe-fallback policy from Phase 1.
Therefore the Phase 2B audit must preserve the target HiCache implementation.

## Actual target runtime route

Static factory inspection establishes:

```text
create_tree_cache -> default_radix_cache_factory
                 -> UnifiedRadixCache
                 -> init_hicache when enable_hierarchical_cache
                 -> attach_hybrid_pool_to_unified_cache
                 -> HybridCacheController
```

For Falcon-H1, the tree components are hybrid:

```text
ComponentType.FULL
ComponentType.MAMBA
```

The assembler creates both host pools and registers them with the hybrid
controller. The MAMBA component has a distinct host value and host LRU path;
it is not merely a KV alias.

Evidence in target source:

```text
unified_radix_cache.py:
  init_hicache()
  cache_controller
  host_pool_group
  evictable_host_leaves

hybrid_pool_assembler.py:
  PoolName.KV / ComponentType.FULL host pool
  PoolName.MAMBA host pool
  host_mamba_evict_fn
  device_mamba_evict_fn

mamba_component.py:
  mamba host_value
  host LRU insertion after device eviction
  MAMBA PoolTransfer for LOAD_BACK

full_component.py:
  FULL host_value and host hit accounting

unified_tree_core.py:
  evictable_device_leaves
  evictable_host_leaves
  demote()
  host-only node traversal
  component host/device LRU separation
```

## #33713 sequence audit

The old failure sequence was:

```text
MAMBA host backup succeeds
-> GPU eviction
-> radix node is pruned
-> later host hit/load-back cannot occur
```

The current target lineage contains explicit mechanisms that prevent treating a
host-backed MAMBA component as an ordinary dead node:

1. MAMBA has `host_value` and `mamba_backuped` state.
2. MAMBA device eviction leaves host-backed component data and inserts it into
the MAMBA host LRU.
3. MAMBA matching accepts either device `value` or host `host_value`.
4. MAMBA match finalization raises `mamba_host_hit_length` for host-only state.
5. MAMBA load-back builds an explicit `PoolTransfer(name=PoolName.MAMBA, ...)`.
6. Unified tree host-leaf logic includes host-backed data and keeps host-only
nodes discoverable through `evictable_host_leaves` / host LRU structures.
7. Host eviction is separate from device eviction; host data is not freed merely
because device data is released.
8. The controller/restore path carries pool-specific transfer evidence and the
later lineage adds retry/frontier wake and durability fences for L3. Those L3
features are not required for the B2 L2-only test but must not be replaced.

The current source therefore does **not** support the claim that the old
MAMBA host-backup → device-eviction → unconditional radix-node-prune sequence
is still the normal path. A runtime B4 test is still required: static presence
of these mechanisms is not proof that the Falcon-H1 path exercises them.

## Supported B2 configuration from parser/source

Target `ServerArgs` defines:

```text
--enable-hierarchical-cache
--hicache-ratio
--hicache-write-policy {write_back,write_through,write_through_selective}
--hicache-io-backend {direct,kernel,kernel_ascend}
--hicache-mem-layout {layer_first,page_first,page_first_direct,page_first_kv_split,page_head}
--hicache-storage-backend (optional)
```

For GPU-L1 ↔ host-DRAM-L2 only, leave storage backend unset. The source
resolves the default CUDA path as:

```text
hicache_io_backend = kernel
hicache_mem_layout = page_first
hicache_host_memory_mode = cache
hicache_write_policy = write_through
```

`kernel + page_first` is the local CUDA-compatible default path in this fork;
`page_first_direct` is used with direct IO, not needed here. No `--hicache-size`
or L3 backend is part of B2.

## Reference validation assets

The 3090 lineage includes dependency-free HiCache tests and production gate
assets, notably:

```text
test/registered/unit/mem_cache/test_hicache_restore.py
test/registered/unit/mem_cache/test_drain_reentry.py
test/registered/unit/mem_cache/test_storage_regression.py
tools/legacy_3090/gate2-run.sh
tools/legacy_3090/gate3_parked_analyze.py
3090-dev/docs/PERFORMANCE-SCORECARD.md
```

Those assets establish the telemetry vocabulary (`device_hit`, `host_hit`,
restore/load-back, KV/Mamba pool accounting) and the previously verified
HiCache lifecycle. They are reference oracles, not a substitute for the
Falcon-H1 runtime B4 evidence.
