# P0-C Profile/Capacity Freeze R60

- Task ID: `P0-C-PROFILE-FREEZE-20260911-R60`
- Invocation: `ses-p0c-profile-freeze-r60-20260911`
- Epoch: `2026-09-11`
- Role: `devops-executor`
- Status: **done**
- Claim boundary: P0-C profile evidence only. This is **not** production acceptance and
  does **not** satisfy or bypass the P0-B hard gate.
- Amended: `.memory/phase2-hicache-design/work/P0-C-AMEND-20260911-R64.md` (2026-09-11).
  R64 scopes the conflict claim to the frozen capacity set, adds `max_req_input_len=65530`,
  relabels source independence, and relabels unsupported metadata. No value below is changed.
- Amended: `.memory/phase2-hicache-design/work/P0-C-R60-CORRECT-20260911-R73.md` (2026-09-11).
  Applies R70 F1: the Architecture row's layer-type wording is corrected from the ambiguous
  "32 layers of `linear_attention`/`full_attention`" to "32 layers total — 24 `linear_attention`
  + 8 `full_attention`; full_attention at indices 3,7,11,15,19,23,27,31", per the R66 F4 capture
  (`01_config.json` `text_config.layer_types`). No frozen numeric value changes.

## ENTRY / input validation

- `ENTRY: ACCEPT`.
- Authorized target only: remote `root@i-1.gpushare.com:27460`, key
  `/home/dev-codex/.ssh/sglang_3060_ed25519`, checkout `/root/sglang-3060-12g-hicache`,
  env `/root/sglang-env-3060-4b/bin/python`. 3090 and production were never touched.
- **Missing required input:** `.memory/phase2-hicache-design/work/P0-C-PROFILE-RECON-20260911-R59.md`
  does not exist (searched the whole live `.memory` workspace; latest P0-C artifact absent).
  The dispatch text itself restates the full procedure (steps 1–6), so the freeze was executed
  against those explicit, self-contained steps. The missing R59 is recorded as an open issue
  (no values were invented to fill it).
- No product source, tests, gates, storage, or Git were modified. No remote reset/reboot was
  performed; evidence was preserved first.

## Method decision (bounded start not required)

A SGLang 3060 4B profile server was **already running** with the complete profile flag set:

- parent launcher PID `218071`, server PID `218072`, started `Thu Sep 10 06:34:32 2026`
  (~31 h uptime at capture), cwd `/root/sglang-3060-12g-hicache`,
  `exe -> /usr/bin/python3.11`, venv `VIRTUAL_ENV=/root/sglang-env-3060-4b`.
- `LISTEN 127.0.0.1:30000` owned by PID 218072; `GET /health` → HTTP 200.

Because the target profile was already live, the bounded action taken was **capture, not
restart** (restarting would have destroyed the running profile's evidence). No server was
started by this invocation, so step (5) cleanup is a no-op; the live pre-existing server was
deliberately left running. This is a deliberate scope decision, not an omission.

## Preflight (step 1)

| Item | Observed |
|---|---|
| Host identity | `I2aff9805ac001019d1` |
| GPU | NVIDIA GeForce RTX 3060, 12288 MiB, driver 550.144.03, CUDA 12.4, 8897 MiB used |
| Checkout | `/root/sglang-3060-12g-hicache` (exists; **not a git repo**) |
| Deployed revision marker | `/root/sglang-3060-12g-hicache/.codex-deployed-revision` = `9213ee01d90ba3925e7fe928e80cc41354ee4fff` |
| Python env | `/root/sglang-env-3060-4b/bin/python` = Python 3.11.11, torch 2.6.0+cu124, CUDA 12.4, `cuda.is_available()=True` |
| `nvcc` | not on PATH (`which nvcc` empty) — not required for this runtime profile |

### Launch-script provenance (step 1)

There is **no persisted launch script or config file in the checkout that defines this 3060
profile.** The profile is defined by an ad-hoc inline `bash -c ... nohup python -m
sglang.launch_server ...` command (authoritative artifact = `/proc/218072/cmdline`, captured in
`r60_evidence.txt`). Content searches for `ready-host-watermark`, `hicache-prefetch-speculative-fraction`,
and `Qwen3.5-4B-AWQ` over `/root`, `/hy-tmp`, `/tmp` found only the running process, its log, and
`server_args.py` — no launcher file.

- `3090-dev/direct-launch-gate3-parked.sh` exists in the checkout but is **a different profile**
  (9B w4a16 default, `sglang-patch` conda env, session-radix-cache, L3 admin key); it is not the
  3060 4B profile and was not used.

## Frozen profile (step 3) — frozen vs unknown

All frozen values below are cross-consistent across the captured sources. Amendment R64 corrects
the original wording: the startup log `server_args` dump (log line 6) and the device/host-pool
startup lines (log lines 27-49) are the **same log file**, so they are one evidence channel, not
two independent ones; genuine independence exists between the log, the live `GET /get_server_info`
JSON, and the launch argv (`/proc/218072/cmdline`). **No conflicts were found among the frozen
capacity values below.** Non-frozen runtime-derived keys do diverge between the startup
`server_args` dump and the live JSON (`disable_chunked_prefix_cache` `False`→`True`,
`pp_max_micro_batch_size` `None`→`1`, `max_mamba_cache_size` `None`→`53`,
`disaggregation_decode_retraction_backup` `None`→`cpu_tensor`); none is in the frozen set — see
`P0-C-AMEND-20260911-R64.md` §2.

### Frozen

| Dimension | Frozen value | Source |
|---|---|---|
| Served model path / weights | `/hy-tmp/models/Qwen3.5-4B-AWQ` (`model.safetensors` 5,052,218,552 B; `model_mtp.safetensors` 241,200,704 B) | proc cmdline; model dir; `server_args` |
| Served / tokenizer name | `/hy-tmp/models/Qwen3.5-4B-AWQ` | `/get_model_info`; `server_args` |
| Architecture | `Qwen3_5ForConditionalGeneration`, `model_type=qwen3_5` (hybrid: 32 layers total — 24 `linear_attention` + 8 `full_attention`; full_attention at indices 3,7,11,15,19,23,27,31; source: R66 `01_config.json` `text_config.layer_types`) | `/get_model_info`; `config.json` (R66 F4 capture) |
| Quantization | `compressed-tensors` / `pack-quantized`, W4 group_size=128 symmetric int (AWQ-class), status `compressed`; `server_args.quantization=None` (auto-detected) | startup log `quant=compressed-tensors`; `config.json` |
| Load weight | elapsed 3.80 s, weights mem usage 3.85 GB | startup log |
| TP / PP / DP / EP | `tp_size=1`, `pp_size=1`, `dp_size=1`, `ep_size=1` | `server_args`; `/get_server_info` |
| Context length (model ceiling) | `context_len=262144` is the **model ceiling** (from `text_config.max_position_embeddings=262144`), **not** the usable single-request input cap; `--context-length` **not** set (`server_args.context_length=None`). Amendment R64 adds the capacity-relevant usable cap `max_req_input_len=65530` — see `P0-C-AMEND-20260911-R64.md` §3 | startup log line 42; `config.json`; `r60_server_info.json` |
| Device KV pool | `max_total_num_tokens=65536`; `KV Cache is allocated. dtype=torch.float8_e4m3fn, #tokens=65536, K size=0.50 GB, V size=0.50 GB` | startup log; `--max-total-tokens 65536` |
| KV cache dtype | `fp8_e4m3` (`torch.float8_e4m3fn`) | proc cmdline; log; `/get_server_info` |
| `mem_fraction_static` | `0.82`; `Memory pool end. avail mem=4.11 GB`; `available_gpu_mem=3.61 GB` | log; `/get_server_info` |
| Mamba device pool | `max_mamba_cache_size=53` (auto; `--max-mamba-cache-size` unset), `conv_state 0.06 GB`, `ssm_state 2.53 GB` | startup log; `server_args.max_mamba_cache_size=None` |
| Mamba semantics | `mamba_backend=triton`, `mamba_full_memory_ratio=0.9`, `mamba_radix_cache_strategy=extra_buffer`, `uses_mamba_radix_cache=True`, `mamba_ssm_dtype` from model config | `server_args`; proc cmdline |
| Sidecar | **none** — `sidecar=None`, `sidecar_args=None` (no separate sidecar pool exists in this profile) | `server_args`; `/get_server_info` |
| Host KV pool (HiCache L2) | `131073 tokens, 2.15 GB host memory` (`hicache_ratio=2.0`, `hicache_size=0` auto) | startup log `Allocating kv hierarchical KV host pool` |
| Host Mamba pool | `5.51 GB host memory` (`layout=page_first`) | startup log `Allocating 5.51 GB host memory for hierarchical Mamba cache` |
| Host pool total | ≈ 7.66 GB (2.15 GB KV + 5.51 GB Mamba); `host_headroom_tokens` initially 131073 | startup log; P3 `causal_epoch` |
| Page size | `page_size=1` (KV token granularity); `c128_page_size=16`; layout `hicache_mem_layout=page_first` | `server_args`; `/get_server_info` |
| HiCache transfer | `transfer_layer_num=32`; components `(<ComponentType.FULL:0>, <ComponentType.MAMBA:2>)`; `hybrid_swa=False hybrid_ssm=True` | startup log |
| Write / IO policy | `hicache_write_policy=write_through`, `hicache_io_backend=kernel`, `hicache_host_memory_mode=cache` | proc cmdline; log; `/get_server_info` |
| Storage backend | `file` (`sglang.srt.mem_cache.hicache_storage.HiCacheFile`), dir `/hy-tmp/hicache-rh-clean-20260910` (`SGLANG_HICACHE_FILE_BACKEND_STORAGE_DIR`), extra config `{"hicache_storage_pass_prefix_keys":true}` | env of PID 218072; startup log |
| Storage prefetch policy | `hicache_storage_prefetch_policy=wait_complete`; retry max attempts `4`, retry poll interval `0`; `hicache_restore_wait_timeout_s=60.0` | proc cmdline; `server_args` |
| Ready-horizon flags | `enable_ready_horizon=True`, `ready_horizon_frontier_n=8`, `ready_host_watermark_low=55000`, `ready_host_watermark_high=110000`; log emits `watermark=[55000/110000]` | proc cmdline; `server_args`; P3 log line 51 |
| Promotion / reserve margins | `hicache_promotion_margin_tokens=2048`, `hicache_writeback_reserve_gb=0.0`, `ready_horizon_safety_margin_gb=0.0`, `ready_horizon_state_p95_tokens=0` | `server_args`; `/get_server_info` |
| Prefetch / speculative capacity limits | `hicache_prefetch_speculative_fraction=0.6`; live P3 `physical_budget_limit_tokens=65536`, `speculative_budget_limit_tokens=39321` (= floor(0.6×65536)), `reserve_floor_tokens=0` | proc cmdline; `server_args`; P3 `rh_preadmission_decision` |
| Scheduler limits | `max_running_requests=1`, `chunked_prefill_size=2048`, `max_prefill_tokens=16384`, `schedule_policy=fcfs`, `retraction_policy=length` | proc cmdline; `server_args`; `/get_server_info` |
| CUDA graph | decode `full` bs `[1]`; prefill `breakable` bs `[4,8,16,32]`; `Capture target prefill/decode ... end` | proc cmdline; `server_args`; startup log |
| Attention/sampling backend | `attention_backend=flashinfer`, `sampling_backend=flashinfer`, `grammar_backend=xgrammar` | `server_args` |
| Speculative decoding | `speculative_algorithm=None` (no draft/EAGLE/MTP engine); `model_mtp.safetensors` present but unused by this profile | `server_args`; `/get_server_info` |

### Unknown / not determinable

| Dimension | Status | Exact reason | Exact command/log that would reveal it |
|---|---|---|---|
| HiCache file-backend max size & min free space | unknown | The live env sets only `SGLANG_HICACHE_FILE_BACKEND_STORAGE_DIR`; no `*_MAX_SIZE` / `*_MIN_FREE_SPACE` env is set, so backend defaults apply. Running server does not log the resolved values. | `tr '\0' '\n' < /proc/218072/environ \| grep HICACHE` (already run: only storage dir) then read defaults in `python/sglang/srt/mem_cache/hicache_storage.py` `HiCacheFile` |
| Running process revision vs current checkout | unknown | Checkout is not a git repo; log has no revision/commit banner; `.codex-deployed-revision`=`9213ee01…` is a marker file, not proof the in-memory process loaded that revision. | Compare `stat`/mtime of `python/sglang/**` at process start vs now; or a fresh bounded start of the same profile would print the loaded revision |
| `nvidia-smi` process list empty despite 8897 MiB used | observation | Container/PID-namespace visibility quirk; the running server accounts for the memory but is not listed. | `nvidia-smi --query-compute-apps=pid,used_memory --format=csv` (was empty); `fuser -v /dev/nvidia*` |
| Exact device page bytes (vs token count) | not applicable | `page_size=1` is expressed in tokens, not bytes; profile defines it at token granularity. | N/A |

## Evidence and artifacts (step 6)

Raw artifacts (local copies, verified against remote sha256):

- `P0-C-PROFILE-FREEZE-20260911-R60.artifacts/sglang3060-rh-clean-env-20260910.log`
  (remote `/tmp/sglang3060-rh-clean-env-20260910.log`, 382 lines, live/append)
  sha256 `01bcfa12bf2868722702b9de6a373f9f50ca8fc68502cdc9c3a88ea4b05a9ff3`
- `...artifacts/r60_server_info.json` (live `GET /get_server_info`, 33083 B)
  sha256 `1854d8ff2c549b764a6ae45e7e1b293209796826c874da53985d76b1e307dc19`
- `...artifacts/r60_model_info.json` (live `GET /get_model_info`, 1164 B)
  sha256 `01bc764229cec59a271b74f127375fd047f51ce831e473cbbc8486bfef5877a5`
- `...artifacts/r60_evidence.txt` (hostname, nvidia-smi, process table, `/proc/218072/cmdline`,
  `ss` port 30000, remote log sha256/wc, deployed revision)
  sha256 `c6085655e51dd9667c879f5b543d63482e6a0c1954223619b225d538d9f705cb`
- `...artifacts/SHA256SUMS.txt`

Remote raw paths: `/tmp/sglang3060-rh-clean-env-20260910.log`,
`/tmp/r60_server_info.json`, `/tmp/r60_model_info.json`, `/tmp/r60_evidence.txt`.

## Commands executed (read-only except local artifact writes)

All remote commands were read-only (`nvidia-smi`, `ps`, `ss`, `ls`, `cat`, `grep`, `sha256sum`,
`/proc` reads, `curl GET` to loopback endpoints, `python -c` JSON reads). No remote file in the
checkout/storage was created, modified, or deleted. Changed resources = the four local artifacts
plus this report only.

## Verification (step 5)

- Profile values verified consistent across `server_args` (log), `/get_server_info` (live), and
  device/host allocation log lines. **No conflicts among the frozen capacity values**; the
  `server_args` dump and the allocation lines share one log file, and the diverging non-frozen
  keys are listed in `P0-C-AMEND-20260911-R64.md` §2.
- No server was started, therefore no cleanup expected. Re-checked after capture:
  only PID 218072 owns `127.0.0.1:30000`; no new orphan `launch_server` processes were created by
  this invocation (the only transient PIDs were the evidence-capture shell/grep, now exited).
- The pre-existing running server was left running intentionally; port 30000 remains bound to the
  same PID. No port leak introduced.
- Local artifact sha256 matches remote sha256 for the live log, confirming faithful capture.

## Summary

The 3060 12G 4B profile is frozen from an already-running, healthy profile server. All requested
dimensions — served model/weights, quantization, TP/PP, context length, KV pool, Mamba/sidecar
pools, host (L2) KV and Mamba pool capacity, page size, ready-horizon flags and watermarks,
prefetch/speculative capacity limits, and logged capacity semantics — were determined and
cross-verified. Three residual items are recorded as explicit unknowns with their revealing
commands; none is a profile config conflict. No source, tests, gates, storage, or Git were
changed, and the server was not restarted or stopped.

## Followups

1. If a persisted 3060 profile launcher is required as an artifact, capture the inline command
   into a checkout script under separate authorization (not done here).
2. To close the file-backend default-size unknown, read the `HiCacheFile` defaults in the
   checkout source (read-only) in a fresh invocation if the P0 workstream needs those numbers.
3. To close the process-vs-checkout revision unknown, a bounded fresh start with the same flags
   would print the loaded revision and allow a hash comparison.

## Open issues

- Required input `P0-C-PROFILE-RECON-20260911-R59.md` is missing from the live workspace; the
  procedure was taken from the dispatch's explicit steps 1–6 instead.
- `nvidia-smi` lists no compute process while 8897 MiB is used (container visibility quirk).
- The running server's code revision cannot be proven to equal the current checkout contents
  because the checkout is not a git repository and the log has no revision banner.
- This report is P0-C evidence only and does not constitute production acceptance or satisfy the
  P0-B hard gate.
