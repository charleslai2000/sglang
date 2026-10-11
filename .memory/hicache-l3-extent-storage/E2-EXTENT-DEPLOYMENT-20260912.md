# E2 — Minimal L3 deployment/selection change: legacy FileBackend -> ExtentFileBackend

```yaml
schema: phase2-hicache-e2-deployment-1
artifact_id: E2-EXTENT-DEPLOYMENT-20260912
task_id: PHASE2-E2-20260912
role: orchestrator (deployment; no product code)
repo: /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt
head: 4f41f5bab562b99562f30c67540eb05344d13637
mode: deploy-only (new launch script; no product/test/gate change)
classification: KNOWN-PATTERN (already-in-tree backend; EXEMPT-eligible)
```

## 1. What changed (and what did NOT)

**Changed (deployment only):** created a NEW launch profile
`/mnt/data/neuron/sglang-3090-r112-20260911/launch-e-20260912.sh`, sha256
`d24195b9a66c832226d8956ac6c79c168fbc92c4b67de44c0e1485847ab3c651`.

The ONLY argv delta versus the frozen `launch-r112.sh`
(sha256 `2259d406f8f2239289d799bfd7bffd6401dedd101ed90225ddc05508cf8caaa3`) is:

```text
- --hicache-storage-backend file
+ --hicache-storage-backend extent
```

(verified by `diff` of the extracted argv; every other flag byte-identical).

Added environment (extent backend sizing; `SGLANG_HICACHE_FILE_BACKEND_*` is
irrelevant to this backend):

```text
SGLANG_HICACHE_EXTENT_BACKEND_STORAGE_DIR=$D/l3-extent   # NEW dir; l3/ untouched
SGLANG_HICACHE_EXTENT_BACKEND_FILE_SIZE=256G
SGLANG_HICACHE_EXTENT_BACKEND_EXTENT_SIZE=64M
SGLANG_HICACHE_EXTENT_BACKEND_MAX_SIZE=200G
SGLANG_HICACHE_EXTENT_BACKEND_MIN_FREE_SPACE=20G
SGLANG_P2A_TIMING_PROBE=1                                 # observability only
```

**NOT changed:** no engine/branch code; `hicache_storage.py` (legacy
FileBackend) and `lru_file_evictor.py` are byte-unchanged; no probe source
change (probe files still match the frozen P2-A shas: `p2a_timing_probe.py`
`96d077b8…0804`, `scheduler.py` `e58ca012…b853`, `unified_radix_cache.py`
`212c3a8f…067f`, `hybrid_cache_controller.py` `64e933f4…e4d5`); no
`ExtentFileBackend` code change; frozen `launch-r112.sh` untouched.

## 2. Why this is the minimal correct fix

E0 (`work/E0-BACKEND-IDENTITY-AUDIT-20260912.md` `bf126e38…946d`) established
that the engine already dispatches backends generically
(`cache_controller.py:645 StorageBackendFactory.create_backend`) and that
`ExtentFileBackend` implements the full `HiCacheStorage` surface with a
RAM-authoritative index and no directory enumeration. Therefore the fallback to
the 3M-small-file path was purely a **selection** outcome, and correcting the
selection is sufficient to restore the target architecture. No query-path code
change is needed.

## 3. Config precedence (why env is sufficient)

`ExtentFileBackend._config_value` (`extent_file_backend.py:240-243`) resolves
each setting as `extra_config[key]` if present else the env field. The frozen
profile's `--hicache-storage-backend-extra-config` contains only
`{"hicache_storage_pass_prefix_keys": true}`, so every sizing setting falls
through to the env vars above. `storage_config.extra_config` is populated from
that dict (`cache_controller.py:832`).

## 4. Deployment/failure behavior

- New L3 directory `l3-extent` is created if absent (`:288-292`); the legacy
  `l3/` (R129 evidence) is not touched.
- One data file per rank/config suffix (`:344-347`): `hicache.data_<model>_0_1`.
- `os.ftruncate(fd, file_size)` preallocates a 256 GiB sparse file; actual disk
  use is the packed live bytes, bounded additionally by GC at
  `max_size x eviction_ratio` (`:1164-1187`).
- GPU access uses the mandatory `flock /mnt/data/gpu/3090.lock`; the script
  self-locks (`exec 9>` + `flock -w`) and releases when the server stops.

## 5. E3 pre-live evidence (CPU-only)

`python -B test/registered/unit/mem_cache/test_extent_file_backend_unit.py`
(`CUDA_VISIBLE_DEVICES=0` to satisfy `test_utils`' `int()[0]` parse; unit test is
pure CPU) -> **Ran 77 tests, OK, exit 0**.
Log `/mnt/data/nerun-dev/e3/e3-extent-unit.log`
sha256 `90110253c66b3f064d9c947cb785b7da2b0eadd404a4dca7711472086b850a6e`.
This covers cross-path v1-write/v2-query hits, sidecar component-key isolation,
generation invalidation, `test_crash_reopen_all_cold`, and the factory
construction.

## 6. Live validation (E2 + E3-live) — DONE

- Backend identity in `sglang-server-e.log`:
  `Creating storage backend 'extent'
  (sglang.srt.mem_cache.storage.extent.extent_file_backend.ExtentFileBackend)`.
- Init line:
  `ExtentFileBackend: file=.../l3-extent/hicache.data_-mnt-data-models-qwen35-gptq_0_1
  extent=64000000 B slots=4000 max_size=200000000000 min_free=20000000000`.
- `/health` -> 200; server served the full E4 workload (59 requests, 0 bad).
- L3 layout: exactly ONE sparse data file (`hicache.data_...`, apparent 256 GB,
  physical ~11 GB live) — not one file per page.
- Live exercise: `evt=extent_write` 403; `evt=storage_hit_query` 111 (48 with
  positive `kv_hit_pages`, `sum = 247,168`); `restore_success` 33.
  This is live evidence of the v1-write -> v2-query storage-hit round trip.
- Legacy `l3/` untouched (newest mtime 08:20:47, before E2/E4; 133 GB).
- Server stopped after E4; GPU lock released (verified FREE).

E3-live coverage note: sidecar component-key isolation and
restart-cold semantics were covered by the CPU unit suite
(`test_extent_file_backend_unit.py`, 77 tests OK), not re-created live.
No-scandir is a static property of the extent package (grep-verified).

## 7. Content sha256 manifest

| Evidence | sha256 |
| --- | --- |
| `launch-e-20260912.sh` | `d24195b9a66c832226d8956ac6c79c168fbc92c4b67de44c0e1485847ab3c651` |
| `launch-r112.sh` (frozen) | `2259d406f8f2239289d799bfd7bffd6401dedd101ed90225ddc05508cf8caaa3` |
| `extent_file_backend.py` | `bef390f13e4479aae4016883ea45e713dc24f008997effed4aca7c4750a09600` |
| `extent_allocator.py` | `afec684803956cbcce637aa1896839a687c3c57e1d29f3dfbab4ae2eb68d339b` |
| E3 unit log | `90110253c66b3f064d9c947cb785b7da2b0eadd404a4dca7711472086b850a6e` |

Status: deployment written + unit-verified; live validation pending GPU release.
