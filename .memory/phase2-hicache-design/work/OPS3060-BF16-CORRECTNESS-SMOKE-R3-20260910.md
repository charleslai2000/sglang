# OPS3060-BF16-CORRECTNESS-SMOKE-R3-20260910

status: done
role: orchestrator-controlled bounded operational smoke after two child SSH-approval blocks
remote: i-1.gpushare.com:27460
workspace: /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt

## Prerequisites

- BF16 shard 1: `/hy-tmp/models/Qwen3.5-4B-BF16/model.safetensors-00001-of-00002.safetensors`
  SHA256 `26a93f066e1916adb13453dae5a0c707c0fbc71299ed98779571a907b8e74c61`.
- BF16 shard 2: symlinked into the model directory from `/root/model.safetensors-00002-of-00002.safetensors`,
  SHA256 `cb544bd9bfae93dc59b0f22b292f5933573854a7f9b97835c67060d7d910e188`.
- Both hashes match the verified local source files.

## R2 result

The first smoke used `max_mamba_cache_size=1`; BF16 weight loading succeeded but SGLang
rejected startup with `RuntimeError: Hybrid (mamba/linear-attention) state cache is too
small to serve any requests`, because one cache unit gives zero requests at mamba ratio 5.
No OOM occurred. AWQ was restored and health returned 200.

## R3 successful smoke

Profile: BF16 weights, FP8 E4M3 KV, `max_total_tokens=512`, chunked prefill 256,
`max_mamba_cache_size=5`, CUDA graph disabled, HiCache/RH disabled, one request.

- BF16 load: `mem usage=8.62 GB`, available GPU memory after load `2.99 GB`.
- Mamba pool: 5 slots, conv state `0.01 GB`, SSM state `0.28 GB`.
- KV pool: 512 tokens, FP8 E4M3, effectively 0.00GB K/V at this small budget.
- Engine became healthy: HTTP 200.
- Explicit `/generate` request: HTTP 200, prompt tokens 18, completion tokens 8,
  e2e latency `1.3314838334918022s`; response contained valid `output_ids` and text.
- BF16 service log showed no OOM or fatal startup error. It did show the expected FP8
  scaling-factor default warning and one transient post-warmup freeze-GC connection race.
- AWQ/RH-ON profile was unconditionally restored afterward: PID `144607`, health HTTP 200,
  Marlin/graph/HiCache startup completed, GPU snapshot `8513 MiB used / 3525 MiB free`.

## Conclusion

BF16 Qwen3.5-4B correctness is PASS at the minimum viable Mamba state-cache setting
(`max_mamba_cache_size=5`) with CUDA graphs and HiCache disabled. BF16 is not a production
capacity profile on the 12GB card: it consumes 8.62GB for weights before runtime pools,
leaving only 2.99GB. No BF16 capacity or performance sweep was run.
