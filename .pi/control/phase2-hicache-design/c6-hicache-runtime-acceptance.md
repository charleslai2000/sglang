# Phase C6 — HiCache production runtime acceptance

Authority at start: `59b18cc0933ed134bf34745ccd19576225ec4850`.

## Verdict

```text
HICACHE_RUNTIME_ENABLED=YES
HICACHE_ACTIVE_TIERS=Qwen: GPU KV + Host KV + extent NVMe configured; OmniCoder contract: GPU KV + Host cache, L3/NVMe explicitly disabled
HICACHE_POPULATION=FAIL
HICACHE_REUSE=PARTIAL (GPU device reuse proven; Host/NVMe reuse not proven)
HICACHE_CORRECTNESS=PASS for exercised Qwen requests
HICACHE_STABILITY=PASS for exercised Qwen requests; no OOM/illegal access/corruption observed
OPENCODEX_HICACHE_PATH=NOT_ACCEPTED
CANONICAL_TREE_CLEAN=YES
CANONICAL_COMMIT=59b18cc0933ed134bf34745ccd19576225ec4850
```

C6 stops at the requested blocker: a direct storage-tier population/reuse proof was not achieved. No source change was made.

## Contract and tiers

### Qwen3.5-9B

The current frozen `LOCAL-PROD-v1.1.2` contract enables:

```text
--enable-hierarchical-cache
--hicache-write-policy write_back
--hicache-storage-backend extent
--hicache-storage-prefetch-policy wait_complete
--hicache-size 32                  # GPU/L2 budget, SI GB
SGLANG_HICACHE_EXTENT_BACKEND_STORAGE_DIR=/data/l3/<run-id>
SGLANG_HICACHE_EXTENT_BACKEND_MAX_SIZE=100Gi  # perf profile
SGLANG_HICACHE_EXTENT_BACKEND_MIN_FREE_SPACE=50Gi
```

The C6 run used canonical source, GPU UUID `GPU-2e3ed202-3655-d919-0a64-259209bc6587`, endpoint `127.0.0.1:30002`, and a unique `/data/l3/c6-qwen-*` directory. `/server_info` resolved `enable_hierarchical_cache=true`, `hicache_host_memory_mode=cache`, `hicache_size=32`, `hicache_write_policy=write_back`, `hicache_storage_backend=extent`, and `hicache_storage_prefetch_policy=wait_complete`. `/hicache/storage-backend` returned the same backend configuration when protected by the admin key.

Observed capacities:

```text
GPU: 24576 MiB total; peak during run approximately 18337 MiB used / 5788 MiB free
Host HiCache KV pool: 318457 tokens
NVMe extent file: sparse 68719476736 bytes (64 GiB allocated address space)
NVMe max_size: 100 GiB; min_free: 50 GiB
```

### OmniCoder-9B

The frozen `LOCAL-PROD-v1.2.1-M2` contract explicitly enables only GPU + Host cache:

```text
--enable-hierarchical-cache
--hicache-write-policy write_back
--hicache-size 32
--hicache-host-memory-mode cache
```

The launcher explicitly unsets the extent/L3 environment and documents L3 storage as disabled. Therefore C6 does not force an NVMe tier onto OmniCoder. This is a contract/configuration result, not an inference from historical M2 naming.

## Qwen direct evidence

The server reached `/health` HTTP 200 and accepted OpenAI requests. A reproducible shared prefix of approximately 1,229 prompt tokens was used with three different suffixes. All requests returned HTTP 200 with coherent non-empty output:

```text
cold suffix:    "Hello! How can I assist you today?"
reuse suffix 1: "Goodbye!"
reuse suffix 2: non-empty coherent response
```

The direct response and metrics evidence was:

```text
request 1: cached_tokens absent/zero; cold path
request 2: cached_tokens absent/zero; restore attempted but log says:
           prefetch_revoke ... storage_hit=0 ... miss_reason=miss
           restore_disposition ... RECOMPUTE ... revoked:miss
           restore_state ... MISS_RECOMPUTE
           restore_recompute ... final_storage_survivability=host
request 3: usage.prompt_tokens_details.cached_tokens=1152
           sglext.cached_tokens_details:
             device=1152, host=0, storage=0, storage_backend=ExtentFileBackend
```

Prometheus metrics after the requests:

```text
sglang:prefill_effective_tokens_total{mode="device_hit"}=1152
sglang:prefill_effective_tokens_total{mode="host_hit"}=0
sglang:prefill_effective_tokens_total{mode="storage_hit"}=0
sglang:cached_tokens_total{cache_source="device"}=1152
sglang:hicache_host_used_tokens=0
sglang:hicache_host_total_tokens=318457
sglang:hicache_dropped_tokens_total=0
```

This proves the request path entered HiCache and that device-tier prefix reuse worked. It does **not** prove Host/NVMe population or storage-tier reuse. The extent manifest remained about 24 KiB and the sparse data file remained unpopulated (`du` reported 0), consistent with the runtime's `NO_L3`/storage miss evidence.

## Correctness and stability

The exercised Qwen cold and reuse requests returned HTTP 200 and coherent output. No OOM, CUDA illegal access, cache corruption, or fatal runtime error was observed. The server was stopped cleanly and GPU memory returned to 4 MiB used / 24121 MiB free.

The runtime emitted non-fatal torchcodec/libavutil warnings inherited from the environment; these did not affect text requests.

## OpenCodex path

The C5 direct endpoints were used for this acceptance. The OpenCodex production scaffold was not driven through an actual OpenCodex client request during C6. Consequently `OPENCODEX_HICACHE_PATH` is not accepted as PASS.

## Blocker and next action

The blocker is not a proven canonical source defect. The current Qwen run configured extent storage, but the exercised prefix did not become an NVMe storage hit: storage population was zero and subsequent restores reported `NO_L3`/`storage_hit=0`. C6 therefore must not claim production-ready Host/NVMe reuse or OpenCodex-path acceptance.

Required follow-up is a separately authorized investigation of the write-back/storage eligibility path (including why the completed prefix is not durably published) and an OpenCodex-client run. No branch/worktree/`/opt` cleanup, push, `main` modification, model change, quantization change, or production semantic change was performed.
