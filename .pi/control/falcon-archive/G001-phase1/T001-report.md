# Phase 1 report — Falcon-H1 native bring-up + 3090 capacity

## VERDICT
**BLOCKED** — Phase 1 cannot proceed to T2–T4 in the current authorized environment without violating the frozen constraints / shared-GPU ownership boundary.

## Environment

- Repo: `/home/ubuntu/workspaces/3rdparty/sglang-falcon-h1-7b`
- Branch: `falcon-h1-7b`
- Commit: `f0075794b20a5b23d8b1b6cae417a8e10f2ae863`
- Fork import check: `PYTHONPATH=.../python /home/ubuntu/venv/bin/python` imports repo `sglang` from `python/sglang/__init__.py`; installed package metadata reports `sglang 0.5.18`.
- Runtime environment: `/home/ubuntu/venv`, `torch 2.13.0+cu129`, CUDA available, GPU `NVIDIA GeForce RTX 3090`, UUID `GPU-2e3ed202-3655-d919-0a64-259209bc6587`.
- Current worktree was clean before control artifacts were created. No product/runtime file was changed.

## Native path

- Config: `python/sglang/srt/configs/falcon_h1.py`, `FalconH1Config`, `model_type = "falcon_h1"`.
- Model: `python/sglang/srt/models/falcon_h1.py`, `FalconH1ForCausalLM`, `EntryClass`, hybrid decoder `FalconH1HybridAttentionDecoderLayer`.
- Falcon-H1 creates `RadixAttention` at `python/sglang/srt/models/falcon_h1.py:169` and exposes `mamba2_cache_params` at `:302-315`.
- Mamba dtype resolution: `python/sglang/srt/configs/mamba_utils.py:mamba2_state_dtype`; explicit `--mamba-ssm-dtype bfloat16` has highest priority over model config/default.
- HiCache is opt-in through `--enable-hierarchical-cache` (`python/sglang/srt/server_args.py:2739`); therefore omitting it is the frozen HiCache-off baseline. Radix cache remains enabled unless `--disable-radix-cache` is supplied.

## Quant/kernel path

- The standard GPTQ path is `python/sglang/srt/layers/quantization/gptq/gptq.py`.
- `GPTQMarlinConfig.override_quantization_method` (`gptq.py:414-438`) auto-converts compatible native GPTQ checkpoints to `gptq_marlin` when no explicit incompatible override is supplied.
- GPTQ-Marlin requires CUDA capability >= 80 (`gptq.py:377-380`) and dispatches linear layers through `GPTQMarlinLinearMethod` (`gptq.py:574+`), backed by the Marlin CUDA GEMM/repack kernels. RTX 3090 is SM86, so the expected native path for a compatible official GPTQ-Int4 checkpoint is GPTQ-Marlin, subject to the checkpoint's actual `quantize_config.json` compatibility. This was not runtime-confirmed because bring-up did not start.
- No silent fallback claim is made; the actual startup log is still required.

## Mamba/cache accounting path

- Falcon-H1 maps all hidden layers to Mamba/linear state (`falcon_h1.py:297-299`), and builds `Mamba2StateShape` from `mamba_intermediate`, `mamba_n_groups`, `mamba_n_heads`, `mamba_d_head`, `mamba_d_state`, and `mamba_d_conv` (`falcon_h1.py:302-315`).
- Per-request state bytes are computed in `mamba_utils.py:BaseLinearStateParams.mamba_cache_per_req` as:
  `(sum(conv_shape elements) * conv_dtype.itemsize + product(temporal_shape) * ssm_dtype.itemsize) * number_of_mamba_layers`.
  With BF16 SSM, the temporal/SSM component uses 2 bytes per element; conv dtype is separately resolved (default BF16 unless overridden).
- `max_mamba_cache_size` is solved in `python/sglang/srt/mem_cache/kv_cache_configurator.py:_handle_max_mamba_cache` from the remaining GPU budget and the configured `mamba_full_memory_ratio`, with a `+1` pool padding slot; no speculative scratch is expected under the frozen no-spec condition.
- Effective request cap is computed in `resolve_max_num_reqs` (`kv_cache_configurator.py:1910+`): requested `max_running_requests` is first limited by token capacity, then by `max_mamba_cache_size // _calculate_mamba_ratio()`. If Mamba is decisive, runtime emits the warning `max_running_requests is capped ... by the mamba state cache` and uses the lower effective value.
- Allocation logging is in `python/sglang/srt/mem_cache/memory_pool.py:849-872`, reporting `max_mamba_cache_size`, conv-state size, and SSM-state size.

## Blocker evidence

Command/evidence collected read-only:

```text
nvidia-smi:
GPU 0: NVIDIA GeForce RTX 3090 (UUID: GPU-2e3ed202-3655-d919-0a64-259209bc6587)

existing process:
2064356 /opt/sglang/local-prod-v1/env/bin/python -u -m sglang.launch_server \
  --model-path /data/models/swift-qwen38-27b-q3_k_m/Swift-Qwen3.8-27B-Q3_K_M.gguf \
  --host 192.168.20.250 --port 30000 ...

GPU memory:
23748 MiB / 24576 MiB used; utilization 0% at probe time

listening:
192.168.20.250:30000 -> pid 2064356
```

The single RTX 3090 is occupied by an existing M4 server using approximately 23.75 GiB. I did not signal, stop, or interfere with that process. The current repository has no `/mnt/data/gpu/3090.lock` file, so no alternate lock could safely authorize taking the device. Starting Falcon-H1 now would violate the single-GPU ownership and would predictably risk OOM/production disruption.

The official model is also not present in the inspected local model locations (`/data/models`, `/home/ubuntu/.cache/huggingface`, `/root/.cache/huggingface`). Only unrelated Qwen/OmniCoder model directories were found. No model download was started because it would not resolve the immediate GPU blocker and its storage/network identity was not part of a frozen artifact plan.

## T2/T3/T4 status

- T2 native server: **not executed**; no bring-up log exists because GPU/model preconditions are not satisfied.
- T3 accounting: static code-path accounting is established above; actual weight/static GPU memory, KV token capacity, Mamba allocation sizes, CUDA graph range, and effective runtime request cap are **not observed**.
- T4 c=1/2/4/8/16 probe: **not executed**. No concurrency result is claimed.

## Runtime modifications

**NONE.** No model weights, runtime source, server process, or existing service was modified.

## Recommended next frontier

Obtain an explicit bounded GPU window in which the incumbent service is voluntarily stopped/handed off, stage or download the fixed official model artifact, then run the minimal server command and capture startup accounting before any concurrency probe. Do not kill the incumbent automatically or infer a capacity verdict from this blocked attempt.
