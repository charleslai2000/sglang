# Phase C6.1 — HiCache Host/NVMe population closure

Authority at start: `344958262caa5c6c7f17524e4a2bfa530e9b5090`.

## Result

```text
HICACHE_HOST_POPULATION=PASS
HICACHE_STORAGE_POPULATION=PASS
HICACHE_STORAGE_REUSE=FAIL
HICACHE_STORAGE_RESTORE=FAIL
HICACHE_CORRECTNESS=PASS
CANONICAL_TREE_CLEAN=YES
CANONICAL_COMMIT=344958262caa5c6c7f17524e4a2bfa530e9b5090
```

C6.1 established that the original `host=0, storage=0` was primarily a workload-trigger issue for Host population, not a device-to-host backup defect. A deterministic pressure workload then populated Host and NVMe. However, this run did not produce a storage-tier hit/restore: requests were satisfied from Host after GPU eviction, while the runtime's storage lookup continued to report `storage_hit=0`/`MISS_RECOMPUTE`. No canonical code was changed.

## Runtime contract and capacity

Canonical Qwen3.5 runtime:

```text
--enable-hierarchical-cache
--hicache-host-memory-mode cache
--hicache-write-policy write_back
--hicache-storage-backend extent
--hicache-storage-prefetch-policy wait_complete
--hicache-size 32
SGLANG_HICACHE_EXTENT_BACKEND_STORAGE_MAX_SIZE=100Gi
SGLANG_HICACHE_EXTENT_BACKEND_MIN_FREE_SPACE=50Gi
```

Runtime startup evidence:

```text
host KV pool: 318457 tokens / 5.22 GB
hierarchical Mamba pool: 26.79 GB host memory
extent file: 64 GiB sparse address space
GPU: RTX 3090 24576 MiB
```

## Deterministic pressure workload

The first C6 workload was only about 1,229 tokens and did not approach the 318,457-token Host pool. It correctly produced no Host/NVMe population.

C6.1 then used unique prefixes of approximately 57,021 tokens each, below the per-request 65,530-token limit, and issued 18 requests with distinct document IDs. This exceeded the device+host working capacity and forced repeated device eviction/demotion.

The initial 117,021-token attempt was rejected with HTTP 400 because the current contract's effective maximum was 65,530 tokens; it was not counted as a runtime failure.

## Host population and D→H proof

After pressure:

```text
sglang:hicache_host_used_tokens=317508 then 318271
sglang:hicache_host_total_tokens=318457
sglang:hicache_backup_tokens_total{pool="kv"}=1.112834e6
sglang:hicache_backup_tokens_total{pool="mamba"}=549
sglang:hicache_backup_bytes_total=1.668e10 initially
sglang:backuped_tokens_total{storage_backend="extent"}=1.103234e6 initially
then 1.103234e6 remained the storage-backup counter at final sample
sglang:hicache_dropped_tokens_total{pool="kv",reason="host_pressure"}=0
```

The backup duration histogram showed 199 completed GPU→Host merged write operations with total duration about 13.84 seconds in the first pressure sample. Logs contained hundreds of `restore_backup` events with `l3_durable_frontier` values, proving the completed host-backed nodes were being advanced toward durable storage. The sparse extent data file grew from zero to:

```text
39G actual disk usage
64 GiB sparse address space
```

with a 127 MiB WAL and a 20 KiB manifest. This proves the ExtentFileBackend write path was actually entered and wrote data.

## Host reuse proof

After further unique-prefix pressure, the original document-0 prefix was requested again. The response was HTTP 200 and coherent:

```json
"usage": {"prompt_tokens_details": {"cached_tokens": 14336}},
"sglext": {"cached_tokens_details": {
  "device": 10,
  "host": 14326,
  "storage": 0,
  "storage_backend": "ExtentFileBackend"
}}
```

Final metrics included:

```text
prefill_effective_tokens_total{mode="host_hit"}=71276
cached_tokens_total{cache_source="host"}=71276
prefill_effective_tokens_total{mode="device_hit"}=170900
hicache_host_used_tokens=318271
hicache_backup_tokens_total{pool="kv"}=1.112834e6
backuped_tokens_total{storage_backend="extent"}=1.103234e6
```

This is direct Host-tier population and Host-tier restore evidence; it is not a TTFT inference.

## Storage result and root cause

NVMe population passed: the extent file reached 39G actual usage and the storage backup counter was positive. The direct storage restore requirement did not pass:

```text
prefill_effective_tokens_total{mode="storage_hit"}=0
sglext.cached_tokens_details.storage=0
```

The storage restore logs for the tested long prefixes repeatedly showed:

```text
prefetch_revoke ... storage_hit=0 ... miss_reason=miss
restore_state ... MISS_RECOMPUTE
rh_preadmission ... negative_cache ... NO_L3
```

The successful reuse request was instead satisfied by Host (`host=14326`), so it did not prove L3 restore. The result is therefore a remaining runtime/workload condition, not enough evidence for a canonical source defect. The population path is functional; the tested prefixes were still host-resident or storage keys/frontier were not reached by the particular reuse timing. No local source edit was justified.

## Correctness and stability

All pressure requests returned HTTP 200 with non-empty output. The Host restore request returned HTTP 200 with coherent output. No OOM, illegal access, fatal runtime error, cache corruption, or dropped-without-backup tokens were observed. GPU memory returned to 4 MiB used / 24121 MiB free after stopping the service.

## Final blocker

```text
HICACHE_HOST_POPULATION=PASS
HICACHE_STORAGE_POPULATION=PASS
HICACHE_STORAGE_REUSE=FAIL
HICACHE_STORAGE_RESTORE=FAIL
```

C6.1 did not modify canonical source or create a new commit. The remaining work is to force a reuse request only after the target prefix has left both GPU and Host (or use a clean process/restart with a populated extent tree and the exact storage-key contract), then directly observe `storage_hit>0` and a non-`MISS_RECOMPUTE` restore. This must not be replaced by a TTFT claim.
