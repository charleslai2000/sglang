#!/bin/bash
export PYTHONPATH=/tmp/opencode/fixprobe/python
export PYTHONDONTWRITEBYTECODE=1
export CUDA_VISIBLE_DEVICES=GPU-2e3ed202-3655-d919-0a64-259209bc6587
export CUDA_HOME=/usr/local/cuda-12.9
exec /opt/sglang/local-prod-v1/env/bin/python -u -m sglang.launch_server \
  --model-path /data/models/Qwen3.8-27B-GSQ-RCO-IQ3_S.gguf \
  --host 127.0.0.1 --port 30164 --tp-size 1 --mem-fraction-static 0.85 \
  --max-total-tokens 16384 --kv-cache-dtype fp8_e4m3 --attention-backend flashinfer \
  --linear-attn-prefill-backend triton --linear-attn-decode-backend triton \
  --mamba-radix-cache-strategy extra_buffer --mamba-ssm-dtype float32 \
  --cuda-graph-backend-decode full --cuda-graph-max-bs-decode 8 \
  --disable-prefill-cuda-graph --max-running-requests 8 \
  --reasoning-parser qwen3 --tool-call-parser qwen3_coder \
  --enable-metrics --export-metrics-to-file \
  --export-metrics-to-file-dir /var/log/sglang/local-prod-v1/phase8/m3-m4-gguf-rootcause-20260916/phaseB/metrics
