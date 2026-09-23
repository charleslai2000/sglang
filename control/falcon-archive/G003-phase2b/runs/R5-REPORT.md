# B4-R5 report

## Verdict

```text
B4 PASS
```

B5/B6 were not run.

## RESTORE CALL PATH

### FULL

```text
host-only match
  -> Req.host_hit_length
  -> UnifiedRadixCache.init_load_back()
  -> _load_back_transfers()
  -> tree_core.build_load_back_spec()
  -> main KV PoolTransfer
  -> HybridCacheController.load()
  -> CacheOperation.load_queue
  -> start_loading()
  -> L2TransferEngine.submit_host_to_device()
  -> ack_load_queue
  -> UnifiedRadixCache.loading_check()
  -> tree_core.commit_load_back()
  -> finish_load_back()
```

The main FULL transfer is the anchor KV transfer. `host_hit_length` is the
matched host prefix length and is used by scheduler admission to request the
load-back. The exact aligned span in R5 was 1789 KV tokens.

### MAMBA

```text
mamba_host_hit_length
  -> Req.needs_host_load_back()
  -> UnifiedRadixCache.init_load_back()
  -> tree_core.build_load_back_spec()
  -> MambaComponent.build_hicache_transfers(LOAD_BACK)
  -> PoolTransfer(name=PoolName.MAMBA)
  -> HybridCacheController.load(extra_pools=...)
  -> one merged CacheOperation
  -> L2TransferEngine.submit_host_to_device()
  -> ack_load_queue
  -> loading_check()
  -> tree_core.commit_load_back()
  -> MambaComponent.commit_hicache_transfer(LOAD_BACK)
```

The Mamba component allocates a request/device Mamba slot in
`prepare_load_back()`. Its LOAD_BACK transfer is committed into the node by
`commit_hicache_transfer()`. The same operation ID is used for FULL and MAMBA;
MAMBA appears twice at issue because the request has both the node restore
transfer and the request CoW/device-slot transfer, while the completion
counter is the MAMBA pool total.

## TELEMETRY PATCH

Only marker-gated diagnostics were added:

```text
python/sglang/srt/managers/cache_controller.py
  _r5_load_log()
  CacheOperation/HiCacheAck operation_id correlation
  load_back_issued at start_loading()
  operation_id propagated to ack

python/sglang/srt/mem_cache/unified_radix_cache.py
  load_back_snapshot_before
  load_back_completed
  load_back_snapshot_after
```

The trace is enabled only by:

```text
/tmp/t38c-durable-trace
```

It writes to `/tmp/t38c-probe.log` and does not alter admission, backup,
eviction, load-back, LRU, cache policy, or transfer scheduling.

Validation:

```text
py_compile: PASS
git diff --check: PASS
```

## BEFORE RESTORE

Target node 18 snapshot:

```text
node exists: yes
snapshot_complete: true
unsupported_component: false

FULL:
  device_present: false
  host_present: true
  host_slot_count: 1789
  host_lock_ref: 1

MAMBA:
  device_present: false
  host_present: true
  host_slot_count: 1
  host_lock_ref: 1
```

Global pressure state immediately before suffix B:

```text
FULL host_used: 201423 / 281377
FULL backup counter: 201423
MAMBA backup counter: 113
device evictions: 64159
```

## H2D TELEMETRY

Target-correlated transfer:

```text
transfer_id: 113
node_ids: [18]
```

### Issued

```text
FULL/KV:
  issued: yes
  token_count: 1789
  host indices: [3..1791]
  device indices: [64122..65910]

MAMBA:
  issued: yes
  node restore transfer: 1 state
  request CoW transfer: 1 state
  same transfer_id: 113
```

### Completed

The ack finish event was synchronized before completion records were emitted.

```text
FULL/KV:
  completed: yes
  token_count: 1789
  transfer_id: 113

MAMBA:
  completed: yes
  pool completion count: 2 state slots
  transfer_id: 113
```

The MAMBA count of two is expected for this implementation: one node restore
transfer and one request/device-slot CoW transfer share the MAMBA pool in the
merged operation.

## AFTER RESTORE

Target node 18 snapshot after ack drain and node finalization:

```text
node exists: yes
snapshot_complete: true
unsupported_component: false

FULL:
  device_present: true
  device_slot_count: 1789
  host_present: true
  host_slot_count: 1789
  device_lock_ref: 1
  host_lock_ref: 0

MAMBA:
  device_present: true
  device_slot_count: 1
  host_present: true
  host_slot_count: 1
  device_lock_ref: 1
  host_lock_ref: 0
```

This matches the implementation's legal residency semantics: host copies remain
as retained duplicates after promotion, while device values are restored and
placed on device residency/LRU.

## CORRECTNESS / RECOMPUTE

Suffix B returned successfully:

```text
HTTP: PASS
semantic output: coherent
sentinel path: PASS
cached_tokens: 1792
cached_tokens_details:
  device: 0
  host: 1792
```

Authoritative effective-prefill delta from before restore to after restore:

```text
host_hit: +1792
input: +116
```

The cached prefix was not recomputed. The request's post-admission snapshot
shows both components materialized on device; the host cache copies remained
retained as duplicates.

## FINAL GATE

```text
FULL D→H backup: PASS
MAMBA D→H backup: PASS
FULL device eviction: PASS
MAMBA device eviction: PASS
node retained: PASS
FULL host retained: PASS
MAMBA host retained: PASS
FULL host-only match: PASS
MAMBA host-only match: PASS
FULL H→D issued: PASS
FULL H→D completed: PASS
MAMBA H→D issued: PASS
MAMBA H→D completed: PASS
post-restore residency: PASS
semantic correctness: PASS
recompute reduction: PASS (+1792 host-hit tokens)
```

## Artifacts

```text
runs/r5/server.log
runs/r5/probe.stdout
runs/r5/r4-result.json
runs/r5/metrics-before.txt
runs/r5/metrics-after-A.txt
runs/r5/metrics-b00.txt ... metrics-b13.txt
runs/r5/metrics-before-restore.txt
runs/r5/metrics-after-B.txt
runs/r5/t38c-probe.log
```
