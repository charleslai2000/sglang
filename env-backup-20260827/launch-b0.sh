#!/usr/bin/env bash
# B0 correctness baseline: official SGLang dev image (dev-qwen38-27b-dflash2,
# pin main >= 8a1e6e4e4610), NVFP4 target, FP8 KV (fp8_e4m3, per #36121),
# unified radix tree ON (SGLANG_ENABLE_UNIFIED_RADIX_TREE=1), radix strategy
# extra_buffer_lazy, NO speculative decoding (no DSpark / DFlash2 / MTP).
# Flags = official verified cell (sgl-project/sglang#35514 rtx5090/nvfp4)
# oomfix3 (2026-08-26, devops): --max-total-tokens 262144 caps KV pool ~8G (262144 > 200995 leg200 still fits), leaves ~2.9G headroom for Triton JIT
# minus the speculative-algorithm block.
# P2 (2026-08-26, tester): attention backend flashinfer -> triton; GDN linear-attention
# prefill/decode backends explicitly triton (expert-matrix P2: isolate FlashInfer+FP8 KV).
set -e
NAME=sglang-b0
IMAGE=lmsysorg/sglang:dev-qwen38-27b-dflash2
docker rm -f "$NAME" >/dev/null 2>&1 || true
docker run -d \
  --name "$NAME" \
  --runtime nvidia --gpus all \
  --ipc host \
  -p 8021:30000 \
  -v /root/models/Qwen3.8-27B-NVFP4-RTX5090:/model:ro \
  -e CUDA_VISIBLE_DEVICES=0 \
  -e PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
  -e SGLANG_ENABLE_UNIFIED_RADIX_TREE=1 \
  --entrypoint python3 \
  "$IMAGE" \
  -m sglang.launch_server \
    --model-path /model \
    --served-model-name qwen3.8-27b-nvfp4-b0 \
    --trust-remote-code \
    --tp-size 1 \
    --host 0.0.0.0 --port 30000 \
    --kv-cache-dtype fp8_e4m3 \
    --attention-backend triton \
    --linear-attn-prefill-backend triton \
    --linear-attn-decode-backend triton \
    --mem-fraction-static 0.92 \
    --max-running-requests 1 \
    --cuda-graph-max-bs 1 \
    --mamba-radix-cache-strategy extra_buffer \
    --mamba-ssm-dtype float32 \
    --max-mamba-cache-size 8 \
    --max-total-tokens 262144 \
    --reasoning-parser qwen3 \
    --tool-call-parser qwen3_coder \
    --enable-metrics
echo "started: http://localhost:8021/v1 (health: /health)"
