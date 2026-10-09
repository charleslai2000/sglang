# P0-C re-freeze — local RTX 3090 SGLang profile (P2-A observation-only probe build)

- Task: `P0-C-3090-PROFILE-REFREEZE-20260912-P2A` (follows the R124 freeze).
- Reason: the user-authorized P2-A observation-only probe edited three producer
  files (`scheduler.py`, `unified_radix_cache.py`, `hybrid_cache_controller.py`)
  and added `p2a_timing_probe.py`, so the running build is no longer the one R124
  bound. R117 and R124 remain **immutable**; this is a NEW freeze.
- Scope: NO profile/param change (same `launch-r112.sh`, byte-identical 59-token
  argv). Only the build binding, live process identity, log path, and one
  observability env toggle change.

## Live target (post-restart)

| Item | Value |
| --- | --- |
| Server PID | `616394` (`python -B -m sglang.launch_server`) |
| Scheduler child PID | `617035` (`sglang::scheduler`) |
| Detokenizer child | `617036` |
| Multiprocessing helper | `617034` |
| Base URL | `http://127.0.0.1:30000` (health 200) |
| Server log | `/mnt/data/neuron/sglang-3090-r112-20260911/sglang-server-p2a.log` (NEW) |
| Launch script | `/mnt/data/neuron/sglang-3090-r112-20260911/launch-r112.sh` |
| Launch script sha256 | `2259d406f8f2239289d799bfd7bffd6401dedd101ed90225ddc05508cf8caaa3` (unchanged) |
| argv | 59 tokens, byte-identical to R117/R124 (sha256 `535394766ce0a2b0d20132b5545ac48120dc9fd8136750f2010896bec23dc866`) |
| GPU | RTX 3090, UUID `GPU-2e3ed202-3655-d919-0a64-259209bc6587` (index 1, SM86, driver 580.178.04) |
| Repo HEAD | `4f41f5bab562b99562f30c67540eb05344d13637` (unchanged; worktree intentionally dirty) |
| Model | `/mnt/data/models/qwen35-gptq` |
| Probe env toggle | `SGLANG_P2A_TIMING_PROBE=1` (observability only, NOT a server arg) |
| Lock | `/mnt/data/gpu/3090.lock` held on fd 9 by PID 616394 |

## Build binding (authoritative; `source_build` is defective — see below)

| Producer file | content sha256 |
| --- | --- |
| `python/sglang/srt/managers/scheduler.py` | `e58ca012c48c1f42d01c1df06e4d9680a9dbdf3d0f8b960ec49040841b65b853` |
| `python/sglang/srt/mem_cache/unified_radix_cache.py` | `212c3a8ffa63f41a0594ab72efed44698c8062bf745190c63919108f0b6e067f` |
| `python/sglang/srt/mem_cache/hybrid_cache/hybrid_cache_controller.py` | `64e933f490884b74f0d38655a8f5a75157bab530dd0ea0688323c9780f1ce4d5` |
| `python/sglang/srt/mem_cache/p2a_timing_probe.py` (NEW; NOT in the 6-file digest) | `96d077b840d66e1d999a1e8f8308c9fc4169458f33da438f776e445032300804` |
| Six-producer content digest (real bytes) | `25391a5e8d3c632d1f3eaacc653e821ace0e3e4d6abbb699c04454f5bcb4851e` |

The prior HOST_ALLOC fix remains in `scheduler.py`
(`_host_alloc_wait_eligible` per-domain clause, previously bound at
`892efc25…`); its bytes are now inside the new `scheduler.py` sha above.

## P2-A probe binding (new in this build)

- `p2a_timing_probe.py` sha `96d077b8…0804` (M1/M2/M3 helpers, env-gated).
- Edited producers add only gated timestamp/log emission:
  `scheduler.py:6075` M1 (`mark_enqueue`); `unified_radix_cache.py:5548-5565` M2
  (`prefetch_issue_mono_ns`); `hybrid_cache/hybrid_cache_controller.py:866,888-948`
  M3 (`StorageQueryProbe`). No behavior change when the gate is OFF.
- Evidence the running process loads the new code: M1/M2/M3 probe lines are
  present in the new log (e.g. `evt=enqueue_mono_ns`,
  `evt=prefetch_issued … prefetch_issue_mono_ns=…`, `evt=storage_hit_query …`).
- `SGLANG_P2A_TIMING_PROBE` is NOT part of the server argv/profile; it is an env
  toggle read at runtime. It is recorded here so P2-A attribution is unambiguous.

## Unchanged frozen capacity semantics (re-confirmed live in the new log)

- `mem_fraction_static=0.82`; `max_total_tokens=65536`; `max_running_requests=1`;
  `chunked_prefill_size=2048`; `max_prefill_tokens=16384`; `max_mamba_cache_size=53`;
  `kv_cache_dtype=fp8_e4m3`; `page_size=1`; `context_len=262144`.
- HiCache: `host_memory_mode=cache`, `ratio=2.0`, `write_policy=write_through`,
  `io_backend=kernel`, `mem_layout=page_first`, `storage_backend=file`,
  `storage_prefetch_policy=wait_complete`,
  `extra_config={"hicache_storage_pass_prefix_keys":true}`,
  `prefetch_speculative_fraction=0.6`, `promotion_margin_tokens=2048`.
- Ready horizon: `frontier_n=8`, host watermarks `[55000/110000]`.
- `disaggregation_mode='null'` (P2-A targets the no-disaggregation prefetch path).
- `enable_request_time_stats_logging=False`.
- L3 file backend dir `/mnt/data/neuron/sglang-3090-r112-20260911/l3`,
  current `131579723776` bytes / `3090193` files (grew from R124's
  `117022638080` / `2742295`).

## REGISTERED DEFECT — `source_build` does not bind the running code (unchanged)

`telemetry_context.py::_source_digest()` uses `parents[3]`, which in this worktree
resolves to `<repo>/python`, so every `_PRODUCER_FILES` path becomes
`<repo>/python/python/...` (nonexistent) and hashes as `<missing>`. Reproduced
exactly: the all-`<missing>` digest is
`03750d8519fdae277a0d04938c53c73ff2d5400be8c6f9f51a3d2bc7b3338d07` = the observed
`source_build` suffix. The REAL six-file digest is `25391a5e…851e` above. P0-C
build binding MUST use content sha256, not `source_build`. Not fixed
(product change outside P2-A's observation-only authorization).

Note: `p2a_timing_probe.py` is not in `_PRODUCER_FILES`, so the 6-file digest does
not cover it; its own sha is bound separately above.

## Provenance markers (harvested from the new log)

| marker | value |
| --- | --- |
| `process_id` | `617035` |
| `run_id` | `run-617035-40503286897536` |
| `profile_id` | `profile-97ee3d5d3bfdca6237dc746e` (same as R124; profile unchanged) |
| `deployment_manifest_digest` | `262a9362e345df15d93049301d2b0e60990ba65d80c3bbc5209fb4cdab140e2d` (constant) |
| `source_build` | `4f41f5bab562b99562f30c67540eb05344d13637:03750d8519fdae277a0d04938c53c73ff2d5400be8c6f9f51a3d2bc7b3338d07` (defective constant) |

## Verify (read-only)

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:30000/health     # 200
sha256sum /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/python/sglang/srt/managers/scheduler.py
sha256sum /mnt/data/neuron/sglang-3090-r112-20260911/launch-r112.sh
```

R117 (`work/R117-profile/`) and R124 (`work/R124-profile/`) remain immutable; their
PID bindings no longer match the live process by design.
