# P0-C re-freeze — local RTX 3090 SGLang profile (post-HOST_ALLOC-wake-fix build)

- Task: `P0-C-3090-PROFILE-REFREEZE-20260912` (follows the R117 freeze).
- Reason: user-authorized Option 1 — the HOST_ALLOC wake-liveness fix changed a
  producer source file (`scheduler.py`), so the running build is no longer the
  one R117 bound. R117 remains **immutable**; this is a NEW freeze.
- Scope: no profile/param change; only the build binding and live process identity
  change. Launch argv is byte-identical to R117.

## Live target (post-restart)

| Item | Value |
| --- | --- |
| Server PID | `3082643` (`python -B -m sglang.launch_server`) |
| Scheduler child PID | `3086752` (`sglang::scheduler`) |
| Detokenizer child | `3086753` |
| Base URL | `http://127.0.0.1:30000` (health 200) |
| Server log | `/mnt/data/neuron/sglang-3090-r112-20260911/sglang-server-r124.log` |
| Launch script | `/mnt/data/neuron/sglang-3090-r112-20260911/launch-r112.sh` |
| Launch script sha256 | `2259d406f8f2239289d799bfd7bffd6401dedd101ed90225ddc05508cf8caaa3` (unchanged) |
| argv | 59 tokens, byte-identical to the R117 freeze |
| GPU | RTX 3090, UUID `GPU-2e3ed202-3655-d919-0a64-259209bc6587` (index 1, SM86, 24576 MiB, driver 580.178.04) |
| Repo HEAD | `4f41f5bab562b99562f30c67540eb05344d13637` (unchanged; worktree intentionally dirty) |
| Model | `/mnt/data/models/qwen35-gptq` |

## Build binding (authoritative; `source_build` is defective — see below)

| Producer file | content sha256 |
| --- | --- |
| `python/sglang/srt/managers/scheduler.py` | `892efc25e2a9ef7c5ebb4afa09cf6914182b1467981d14cd76c53eea5d8de9d7` |
| Six-producer content digest (real bytes) | `abe6504f4b8539a9d93ba6461fb7e559d4c95a0384e2481856879ef85f34974b` |

The changed producer file carries the `_host_alloc_wait_eligible` per-domain fix
(`scheduler.py:3716-3755`): a blocked domain stops blocking if its generation
advanced OR it is currently capacity-satisfiable (`free+evictable >= required`).

## Unchanged frozen capacity semantics (from R117; re-confirmed live in the new log)

- `mem_fraction_static=0.82`; `max_total_tokens=65536`; `max_running_requests=1`;
  `chunked_prefill_size=2048`; `max_prefill_tokens=16384`; `max_mamba_cache_size=53`;
  `kv_cache_dtype=fp8_e4m3`; `page_size=1`; `context_len=262144`.
- HiCache: `host_memory_mode=cache`, `ratio=2.0`, `write_policy=write_through`,
  `io_backend=kernel`, `mem_layout=page_first`, `storage_backend=file`,
  `storage_prefetch_policy=wait_complete`,
  `extra_config={"hicache_storage_pass_prefix_keys":true}`,
  `prefetch_speculative_fraction=0.6`, `promotion_margin_tokens=2048`.
- Ready horizon: `frontier_n=8`, host watermarks `[55000/110000]`.
- Host pools re-allocated in the new log: KV host `131073` tokens / `2.15 GB`;
  Mamba host `5.51 GB`.
- L3 file backend `SGLANG_HICACHE_FILE_BACKEND_STORAGE_DIR=/mnt/data/neuron/sglang-3090-r112-20260911/l3`,
  cap `200000000000 B`, min_free `20000000000 B`;
  current `117022638080` bytes / `2742295` files (grew from the R117 freeze due to
  R119/R121/R122/R123 runs).

## REGISTERED DEFECT — `source_build` does not bind the running code

`python/sglang/srt/mem_cache/telemetry_context.py::_source_digest()` builds each
path as `Path(__file__).resolve().parents[3] / "<relative>"`. In this worktree the
module lives at `<repo>/python/sglang/srt/mem_cache/telemetry_context.py`, so
`parents[3]` = `<repo>/python` and every relative path becomes
`<repo>/python/python/sglang/...` (nonexistent) -> each hashes as `b"<missing>"`.

- Verified: the all-`<missing>` model reproduces the observed constant
  `source_build` suffix `03750d8519fdae277a0d04938c53c73ff2d5400be8c6f9f51a3d2bc7b3338d07`.
- The real six-file content digest is
  `abe6504f4b8539a9d93ba6461fb7e559d4c95a0384e2481856879ef85f34974b`.
- Consequence: `source_build` is constant across builds. P0-C build binding MUST
  use the content sha256 above, not `source_build`.
- Not fixed: it is a product change outside the wake-liveness authorization.

## Provenance markers

`deployment_manifest_digest` is a hard-coded constant
`262a9362e345df15d93049301d2b0e60990ba65d80c3bbc5209fb4cdab140e2d` (unchanged).
`run_id` / `profile_id` change per process; they are harvested from the new
server's own `host_alloc.v1` producer events in `R124-bundle` (same build as this
freeze) and recorded there; `source_build` is the defective constant above.

## Verify (read-only)

```bash
# health + pids
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:30000/health
# build binding
sha256sum /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/python/sglang/srt/managers/scheduler.py
# launch script binding
sha256sum /mnt/data/neuron/sglang-3090-r112-20260911/launch-r112.sh
```

R117 (`work/R117-profile/`) remains the immutable pre-fix freeze; its
`verify_profile.sh` no longer matches the live process PIDs by design.
