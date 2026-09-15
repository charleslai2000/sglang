# R117 - Local RTX 3090 SGLang profile freeze

Task: `P0-C-3090-PROFILE-FREEZE-20260911-R117`
Epoch: `2026-09-11`

Read-only freeze of the exact local RTX 3090 SGLang server profile and capacity
semantics that later P1/P2/P3 measurements and acceptance use. No server state was
changed: the process was not started, stopped, restarted, killed, or reconfigured,
and no product code or instrumentation was added.

The 3060 freeze (R60/R61) no longer applies: the experiment environment was
pivoted to this local 3090 host, so this document re-establishes the freeze
against the live 3090 process and binds it to the frozen R114 evidence.

## Live target

| Item | Value |
| --- | --- |
| Server PID | `48746` (`python -B -m sglang.launch_server`) |
| Scheduler child PID | `48806` (`sglang::scheduler`) |
| Base URL | `http://127.0.0.1:30000` (health 200 at freeze) |
| GPU | RTX 3090, UUID `GPU-2e3ed202-3655-d919-0a64-259209bc6587` (GPU 1, SM86, 82 SMs, 24576 MiB) |
| Repo HEAD | `4f41f5bab562b99562f30c67540eb05344d13637` (worktree intentionally dirty) |
| Server log | `/mnt/data/neuron/sglang-3090-r112-20260911/sglang-server-r112.log` |
| Launch script | `/mnt/data/neuron/sglang-3090-r112-20260911/launch-r112.sh` |
| Model | `/mnt/data/models/qwen35-gptq` (Qwen3.5, GPTQ 4-bit) |

## Frozen capacity semantics (each sourced from the live log/process)

- `mem_fraction_static` = `0.82`; `max_total_tokens` = `65536`;
  `max_running_requests` = `1`; `chunked_prefill_size` = `2048`;
  `max_prefill_tokens` = `16384`.
- `max_mamba_cache_size` = `53` (device); `kv_cache_dtype` = `fp8_e4m3`
  (`torch.float8_e4m3fn`); `page_size` = `1`; `context_len` = `262144`.
- Device KV cache: `65536` tokens, K `0.50 GB`, V `0.50 GB`. Device Mamba cache:
  conv `0.06 GB`, ssm `2.53 GB`. Memory pool end `15.69 GB`, available GPU
  `15.26 GB`.
- HiCache: `host_memory_mode=cache`, `ratio=2.0`, `write_policy=write_through`,
  `io_backend=kernel`, `mem_layout=page_first`, `storage_backend=file`,
  `storage_prefetch_policy=wait_complete`,
  `extra_config={"hicache_storage_pass_prefix_keys":true}`,
  `prefetch_speculative_fraction=0.6`, `promotion_margin_tokens=2048`.
- Ready horizon: `enable_ready_horizon=true`, `frontier_n=8`, host watermarks
  `[55000/110000]`.
- Host KV pool: `131073` tokens, `2.15 GB` host memory
  (log: `Allocating kv hierarchical KV host pool: 131073 tokens, 2.15 GB host memory.`).
- Host Mamba pool: `5.51 GB` host memory, `page_first`
  (log: `Allocating 5.51 GB host memory for hierarchical Mamba cache (layout=page_first).`).
  The host Mamba **token/slot count is not logged**, so it is recorded as an
  explicit gap in `profile.json` rather than an estimated number.
- L3 file backend: dir `/mnt/data/neuron/sglang-3090-r112-20260911/l3`,
  cap `200000000000 B`, watermark `0.90`, min_free `20000000000 B`;
  current `20455358464` bytes / `484747` files (stable at freeze).

## Provenance bind

- `process_id` = `48806`
- `run_id` = `run-48806-4187756182262`
- `profile_id` = `profile-97ee3d5d3bfdca6237dc746e`
- `source_build` = `4f41f5bab562b99562f30c67540eb05344d13637:03750d8519fdae277a0d04938c53c73ff2d5400be8c6f9f51a3d2bc7b3338d07`
- `deployment_manifest_digest` = `262a9362e345df15d93049301d2b0e60990ba65d80c3bbc5209fb4cdab140e2d`

The first four match `R114-bundle/manifest.json` `runtime` exactly. The
`deployment_manifest_digest` is **not** a top-level field in that `manifest.json`;
it was confirmed from `R114-bundle/raw.log` and from the live server's own
`host_alloc.v1` product markers. No discrepancies were found.

## Files

- `profile.json` - the frozen profile (all values sourced from the live host).
- `README.md` - this summary.
- `verify_profile.sh` - read-only, idempotent re-derivation and comparison.

## Verify

```bash
bash /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/.memory/phase2-hicache-design/work/R117-profile/verify_profile.sh
```

Exit `0` means every live-derived field matches `profile.json`; otherwise the
script prints the exact mismatching field(s) and exits non-zero. It re-checks:
health 200, both PIDs alive, exact PID argv, launch-script sha256, material
environment variables, repo HEAD, python/torch/triton/transformers/sglang
versions and sglang import path, the UUID-pinned GPU facts (model, driver,
VRAM, SM count, compute capability), L3 dir stats, the live provenance markers,
and the R114 manifest identity.
