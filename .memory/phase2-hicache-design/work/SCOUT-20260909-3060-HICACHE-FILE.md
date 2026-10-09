# Scout report: HiCache file backend and Qwen3.5 hybrid Mamba

Task ID: `SCOUT-3060-HICACHE-FILE-20260909`  
Epoch: `3060-P4`  
Status: `done`

## Scope and baseline

Read-only search was limited to `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt`, its applicable `docs/AGENTS.md`, and the existing phase-2 memory handoff under `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory`. No remote process control, test execution, or product edits were performed. The checkout has uncommitted control-plane/storage files (`git status --short --branch`), so this report describes the checked-out source as observed and does not infer upstream behavior.

## Authoritative launch schema

`python/sglang/srt/server_args.py:2739-2823` defines the relevant options:

* `--enable-hierarchical-cache` is the gate.
* `--hicache-host-memory-mode` is `cache` (persistent L2 host tier) or `buffer_only` (transient GPU/storage staging); default `cache`.
* `--hicache-ratio` is host-pool/device-pool size; defaulting is `2.0` for `cache`, `1.2` for `buffer_only` (`server_args.py:8490-8507`). `--hicache-size` overrides the ratio (`2755-2759`).
* `--hicache-write-policy` choices are `write_back`, `write_through`, and `write_through_selective`; default is `write_through` (`2760-2767`).
* `--hicache-storage-backend` choices include `file`, `extent`, `sim`, `mooncake`, `hf3fs`, `nixl`, `aibrix`, and others (`2790-2810`).
* `--hicache-storage-prefetch-policy` choices are `best_effort`, `wait_complete`, and `timeout`; default `timeout` (`2811-2818`).
* `--hicache-storage-backend-extra-config` accepts an inline JSON object or `@` JSON/YAML/TOML file (`2819-2823`).

`buffer_only` requires a storage backend and rejects `write_back` (`server_args.py:8570-8583`). It is also rejected for decode instances because the decode path bypasses the buffer-mode pipeline (`8585-8591`). For the requested prefill-side Qwen3.5 experiment, `cache` is the least ambiguous mode.

Recommended deterministic baseline, copied from the registered Qwen3.5 test (`test/registered/hicache/test_qwen35_hicache.py:40-91`):

```bash
export SGLANG_HICACHE_FILE_BACKEND_STORAGE_DIR=/tmp/qwen35-hicache
python -m sglang.launch_server \
  --model-path Qwen/Qwen3.5-27B \
  --tp-size 4 \
  --max-mamba-cache-size 500 \
  --max-total-tokens 120000 \
  --chunked-prefill-size 2048 \
  --mamba-scheduler-strategy extra_buffer \
  --mamba-track-interval 128 \
  --mamba-ssm-dtype bfloat16 \
  --speculative-algorithm NEXTN \
  --speculative-num-steps 3 \
  --speculative-eagle-topk 1 \
  --speculative-num-draft-tokens 4 \
  --max-running-requests 128 \
  --reasoning-parser qwen3 \
  --model-loader-extra-config '{"enable_multithread_load": true,"num_threads": 64}' \
  --hicache-mem-layout page_first_direct \
  --hicache-io-backend direct \
  --enable-hierarchical-cache \
  --hicache-ratio 2 \
  --hicache-size 0 \
  --hicache-write-policy write_through \
  --hicache-storage-backend file \
  --hicache-storage-prefetch-policy wait_complete \
  --kv-events-config '{"publisher":"zmq","topic":"kv-events"}'
```

The checked-in test uses `Qwen/Qwen3.5-27B`, four GPUs, and a temporary file directory. A 3090/Qwen3.5-9B vehicle is referenced by the existing handoff, but its exact model-specific launcher is not in the source test above; do not silently substitute 27B flags for the 9B vehicle without recording that change.

## `file` backend extra-config schema

The plain `file` backend is `HiCacheFile` (`python/sglang/srt/mem_cache/hicache_storage.py:368-455`). Its storage directory is selected by the environment variable `SGLANG_HICACHE_FILE_BACKEND_STORAGE_DIR` (`373-374`); unlike the `extent` backend, the `file` constructor does not read `storage_dir` from `extra_config` at that point. It creates one `.bin` file per suffixed key, with model/TP/PP/CP isolation in the suffix (`375-455`).

The file backend's `extra_config` is passed to `LRUFileEvictor` (`hicache_storage.py:425-438`). The evictor documents and parses these keys (`python/sglang/srt/mem_cache/storage/file/lru_file_evictor.py:59-148`):

```json
{
  "hicache_storage_pass_prefix_keys": true,
  "max_size": "120G",
  "min_free_space": "10G",
  "eviction_ratio": 0.9,
  "enable_metadata_cache": false,
  "metadata_ttl": 5.0
}
```

`max_size`, `min_free_space`, and `eviction_ratio` are eviction controls. `enable_metadata_cache` and `metadata_ttl` are read by `HiCacheFile` (`401-423`). Extra-config values take precedence over the corresponding `SGLANG_HICACHE_FILE_BACKEND_*` environment variables in the evictor (`lru_file_evictor.py:127-148`). The registered file-backend test uses the minimal prefix-key JSON `{"hicache_storage_pass_prefix_keys": true}` (`test_hicache_storage_file_backend.py:79-93`).

Do not confuse `file` and the repository's `extent` backend. The extent backend is selected with `--hicache-storage-backend extent`; its schema is in `python/sglang/srt/mem_cache/storage/extent/extent_file_backend.py:281-337`: `storage_dir`, `extent_size`, `file_size`, `max_size`, `min_free_space`, `eviction_ratio`, and `direct_io`. The checked-in parked launcher uses:

```bash
--hicache-write-policy write_back \
--hicache-storage-backend extent \
--hicache-storage-backend-extra-config '{"max_size":"120G","file_size":"120G","min_free_space":"10G"}' \
--hicache-storage-prefetch-policy wait_complete \
--hicache-ratio 1.3
```

This exact argument shape is in `3090-dev/direct-launch-gate3-parked.sh:46-51`. The phase-2 handoff also records the frozen experiment parameters `hicache_ratio=1.3`, extent `file_size=120G`, and `r=0.42` in `plan-rh-durability.md:53-61`.

## Write, flush, and durability semantics

For `file`, `HiCacheFile.set()` writes tensor bytes to a unique temporary file, calls `os.replace`, then commits the evictor entry (`hicache_storage.py:507-554`). The source does not call `fsync`/`fdatasync` in this path. Therefore a successful backend write/engine ACK is an application-level write plus metadata/index visibility, not proof of power-loss durability.

For `extent`, the source explicitly describes the ACK as `pwrite` success plus index registration, with “no fsync” (`storage/extent/extent_file_backend.py:1-21`). `batch_set_v1` performs pwritev, then allocator commit (`598-667`); eviction is synchronous on the write path and has no background daemon (`1164-1183`). `file_size` is preallocated with `ftruncate` (`368-375`).

`POST /flush_cache` is used by both the Qwen3.5 test (`test_qwen35_hicache.py:124-131`) and file-backend tests (`test_hicache_storage_file_backend.py:172-179`) to clear device cache and force a subsequent storage path. It should be treated as a cache-transition/test control, not an fsync or crash-consistency barrier. The existing phase-2 handoff explicitly says a fixed settle, including `sleep 300`, is not a durability criterion (`.memory/phase2-hicache-design/plan-rh-durability.md:80-89`); use observed per-session submit/ACK/frontier evidence instead.

## Runtime effective-state endpoint and fields

The runtime storage endpoint is implemented in `python/sglang/srt/entrypoints/http_server.py:1083-1157`:

```bash
curl -s http://127.0.0.1:30000/hicache/storage-backend
```

The JSON fields exposed by `GET /hicache/storage-backend` are `hicache_storage_backend`, `hicache_storage_backend_extra_config`, `hicache_storage_prefetch_policy`, and `hicache_write_policy` (`1143-1157`). The registered lifecycle test asserts these exact fields and values after attach (`test_hicache_storage_runtime_attach_detach.py:271-313`). Runtime attach uses `PUT /hicache/storage-backend` with JSON keys `hicache_storage_backend`, `hicache_storage_backend_extra_config_json`, `hicache_storage_prefetch_policy`, and `hicache_write_policy` (route comment and handler `http_server.py:1075-1100`); detach is `DELETE /hicache/storage-backend` (`1116-1127`).

Useful experiment observations come from `GET /metrics`, not the storage status endpoint. HiCache gauges are created only when hierarchical cache is enabled (`python/sglang/srt/observability/metrics_collector.py:651-748`) and include:

* `sglang:hicache_host_used_tokens`, `sglang:hicache_host_total_tokens`, `sglang:hicache_kv_pool_tokens`;
* `sglang:hicache_writeback_reserve_tokens`, `sglang:hicache_ready_resident_tokens`, `sglang:hicache_working_tokens`;
* `sglang:hicache_spec_inflight_tokens`, `sglang:hicache_usable_tokens`, `sglang:hicache_kv_host_usable_tokens`, `sglang:hicache_mamba_host_usable_tokens`, and `sglang:hicache_ready_state_max_tokens`.

The collector updates these fields at `metrics_collector.py:1498-1538`. Storage transfer counters include `sglang:hicache_backup_duration_seconds`, `sglang:hicache_backup_bytes_total`, `sglang:hicache_backup_tokens_total`, and `sglang:hicache_dropped_tokens_total` (`2017-2024`, `2251-2322`).

## Ready Horizon (RH) flags

The checked-out flag is `--enable-ready-horizon`, default false (`server_args.py:2866-2880`). Related sizing/experiment flags are:

```text
--hicache-prefetch-speculative-fraction 0.6
--ready-horizon-frontier-n 8
--ready-host-watermark-low 43513
--ready-host-watermark-high 87026
```

Definitions and defaults are `server_args.py:2881-2940`. The token watermarks are authoritative by default; the legacy count-mode pair `--ready-host-watermark-low-count` / `--ready-host-watermark-high-count` only takes precedence when both are set (`2941-2968`). Token/state reserve knobs are documented at `2969-3065`, including `--ready-horizon-margin-state-tokens`, `--hicache-writeback-reserve-state-tokens`, and `--ready-horizon-state-p95-tokens`.

The existing handoff requires an RH-off/RH-on paired replay where the only intended arm difference is `--enable-ready-horizon` (`plan-rh-durability.md:67-80`). It also requires engine-event joins by request ID; `rh_synced`, a host hit, or a driver label alone is not acceptance evidence (`plan-rh-durability.md:89-95`).

## Minimal deterministic GPU/Host/L3 experiment

1. Use one immutable request/session manifest and one clean storage directory per arm. Start with RH off using the Qwen3.5 launch above, choosing the checked-out model/TP configuration actually available on the GPU. Record `GET /hicache/storage-backend`, `GET /server_info`, and the full `/metrics` snapshot before traffic.
2. Warm a fixed set of Qwen3.5 hybrid-Mamba histories. Record exact tokenized lengths and request IDs. Require a per-session completion barrier based on KV and Mamba storage-submit/ACK/frontier evidence; do not use elapsed sleep as the barrier. The handoff's target vehicle is approximately 55K-token history and S=25 (`plan-rh-durability.md:40-61`).
3. Issue one deterministic continuation per warmed session, then `POST /flush_cache?timeout=30` and issue the same continuation again. Compare cached-token behavior, response correctness, `/metrics` GPU/host gauges, and file/extent occupancy. For the file backend, inspect only the configured storage directory and matching suffixed `.bin` files; for extent, inspect `hicache.data*` and allocator/log evidence.
4. Repeat the identical manifest with RH on, adding only:

```bash
--enable-ready-horizon \
--ready-horizon-frontier-n 8 \
--ready-host-watermark-low 43513 \
--ready-host-watermark-high 87026
```

5. Join `ready_stage`, `ready_pool`, `restore_ready`/`restore_state=READY`, `admission`, and `restore_success` by request ID. Report ready-before-admission rate, L3-to-host restore wait, TTFT, device/host/storage hit tokens, recompute fraction, restore success, and all relevant metrics. The handoff's hard RH-on criterion is at least 95% host-ready-before-admission over issued ready-stage events, with no correctness/deadlock/starvation/error regression (`plan-rh-durability.md:133-135`).

## Hybrid Mamba limitations and open issues

* Qwen3.5 is not an ordinary KV-only workload. The phase-2 handoff records that raw KV can be present while the Mamba trailing boundary is zero, and insists on the all-state KV+Mamba intersection (`plan-rh-durability.md:40-42`, `80-89`). A KV-only hit or a missing Mamba checkpoint must not be called a successful restore.
* The checked-in Qwen3.5 test is a large 27B/4-GPU accuracy smoke test (`test_qwen35_hicache.py:25-29`, `40-91`), not a 3090 single-GPU minimal benchmark. Hardware/model downscaling needs its own recorded launch decision.
* `file` backend uses per-key files and application-level atomic rename, but no fsync was observed. `extent` has explicit no-fsync ACK semantics. Neither backend alone proves crash/power-loss durability.
* `/hicache/storage-backend` reports configured/effective policy fields, but it does not expose per-session durable frontier or Mamba completeness. Those must come from engine traces/events and metrics.
* Ready Horizon is disabled by default and its current public observables are mostly metrics/internal event joins; the checked-out source does not expose a single RH status JSON endpoint. Treat missing event joins as unverified rather than inferred success.
* Search did not inspect external documentation, remote machines, or unrelated model backends. No claim is made about behavior outside this checkout or about a different SGLang revision.

## Artifacts and followups

Artifact written: this report. Evidence is source line references above. Followup owners can use the exact launch/test shapes and the phase-2 durability barrier contract to build the next deterministic vehicle; that would be extra work requiring a fresh Task ID.

Open issues: exact 3090/Qwen3.5-9B launch sizing; a durable-frontier/Mamba-completeness runtime endpoint is absent from the inspected endpoint surface; filesystem crash durability remains outside the backend ACK contract.
