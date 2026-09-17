#!/bin/bash
# LOCAL-PROD-v1.1 — canonical launcher
# Frozen identity: /opt/sglang/local-prod-v1.1-candidate/manifest/IDENTITY.md
# Profile: SGLANG_PROFILE=perf|capacity   (default perf)
set -euo pipefail

PROFILE="${SGLANG_PROFILE:-perf}"
PORT="${SGLANG_PORT:-30000}"

# --- pinned cache budgets. Physical capacity != benchmark cache budget. ---
# NOTE: --hicache-size is SI GB (10^9), NOT GiB.
case "$PROFILE" in
  perf)     L2_GB=32; L3_MAX=100Gi ;;   # L2 = 32 GB = 29.8 GiB
  capacity) L2_GB=48; L3_MAX=200Gi ;;   # L2 = 48 GB = 44.7 GiB
  *) echo "FATAL: unknown SGLANG_PROFILE=$PROFILE (want perf|capacity)" >&2; exit 2 ;;
esac

LOG_DIR=/var/log/sglang/local-prod-v1.1
mkdir -p "$LOG_DIR"

# --- source binding: MUST be the frozen snapshot, NOT the editable venv path ---
export PYTHONPATH=/opt/sglang/local-prod-v1.1-candidate/src/python

# --- CUDA ---
export CUDA_HOME=/usr/local/cuda-12.9
export PATH="$CUDA_HOME/bin:$PATH"

# --- GPU pin: UUID only (NVML index and CUDA ordinal are INVERTED on this box) ---
export CUDA_VISIBLE_DEVICES=GPU-2e3ed202-3655-d919-0a64-259209bc6587

# --- Extent L3 backend. The extent backend reads EXTENT_BACKEND_*, NOT FILE_BACKEND_*. ---
export SGLANG_HICACHE_EXTENT_BACKEND_STORAGE_DIR=/data/l3/local-prod-v1.1
export SGLANG_HICACHE_EXTENT_BACKEND_MAX_SIZE="$L3_MAX"
export SGLANG_HICACHE_EXTENT_BACKEND_MIN_FREE_SPACE=50Gi

echo "=== LOCAL-PROD-v1.1 launcher ==="
echo "profile=$PROFILE port=$PORT hicache-size=${L2_GB}GB(SI) L3_MAX=$L3_MAX"
echo "PYTHONPATH=$PYTHONPATH"
echo "CUDA_VISIBLE_DEVICES=$CUDA_VISIBLE_DEVICES"
echo "L3_DIR=$SGLANG_HICACHE_EXTENT_BACKEND_STORAGE_DIR"
echo "======================================"

cd /tmp   # avoid the /home/ubuntu cwd-shadowing trap for `import sglang`
exec /opt/sglang/local-prod-v1.1-candidate/env/bin/python -u -m sglang.launch_server \
  --model-path /data/models/qwen35-9b-w4a16 \
  --host 127.0.0.1 --port "$PORT" \
  --tp-size 1 \
  --mem-fraction-static 0.92 \
  --max-total-tokens 65536 \
  --kv-cache-dtype fp8_e4m3 \
  --attention-backend flashinfer \
  --linear-attn-prefill-backend triton \
  --linear-attn-decode-backend triton \
  --mamba-radix-cache-strategy extra_buffer \
  --mamba-ssm-dtype float32 \
  --enable-hierarchical-cache \
  --hicache-write-policy write_back \
  --hicache-storage-backend extent \
  --hicache-storage-prefetch-policy wait_complete \
  --hicache-size "$L2_GB" \
  --enable-ready-horizon \
  --reasoning-parser qwen3 \
  --tool-call-parser qwen3_coder \
  --enable-metrics \
  --export-metrics-to-file \
  --export-metrics-to-file-dir "$LOG_DIR" \
  --disable-prefill-cuda-graph
