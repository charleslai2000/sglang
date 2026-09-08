#!/usr/bin/env bash
# Gate A/B/C parked-fleet launcher.  Config-only vehicle; product code is
# unchanged.  RH is the only arm difference between paired fit runs.
set -euo pipefail

export SGLANG_ENABLE_UNIFIED_RADIX_TREE=1
export MAX_JOBS="${MAX_JOBS:-1}"
export CUDA_HOME="${CUDA_HOME:-/root/miniconda3/envs/sglang-dev/lib/python3.10/site-packages/nvidia/cu13}"
export CPLUS_INCLUDE_PATH="${CPLUS_INCLUDE_PATH:-/root/miniconda3/envs/sglang-dev/include}"
export LIBRARY_PATH="${LIBRARY_PATH:-/root/miniconda3/envs/sglang-dev/lib}"
export LD_LIBRARY_PATH="/root/miniconda3/envs/sglang-dev/lib:${CUDA_HOME}/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export SGLANG_HICACHE_FILE_BACKEND_STORAGE_DIR="$STORAGE_DIR"
export SGLANG_HICACHE_FILE_BACKEND_MAX_SIZE="${MAX_SIZE:-120G}"
export SGLANG_HICACHE_FILE_BACKEND_MIN_FREE_SPACE=10G
export SGLANG_HICACHE_FILE_BACKEND_ENABLE_METADATA_CACHE=true
export SGLANG_HICACHE_EXTENT_BACKEND_STORAGE_DIR="$STORAGE_DIR"
export SGLANG_HICACHE_EXTENT_BACKEND_MAX_SIZE="${MAX_SIZE:-120G}"
export SGLANG_HICACHE_EXTENT_BACKEND_MIN_FREE_SPACE=10G
export SGLANG_HICACHE_EXTENT_BACKEND_FILE_SIZE="${FILE_SIZE:-${MAX_SIZE:-120G}}"

KEYFILE="${KEYFILE:-/opt/sglang/l3-admin-key}"
L3_ADMIN_KEY=$(cat "$KEYFILE")
RH_ARGS=()
if [ "${RH:-off}" = "on" ]; then
  RH_ARGS+=(--enable-ready-horizon)
fi

export PATH="/root/miniconda3/envs/sglang-patch/bin:$PATH"
exec /root/miniconda3/envs/sglang-patch/bin/python3 -m sglang.launch_server \
  --model-path "${MODEL_PATH:-/root/models/Qwen3.5-9B-w4a16}" \
  --served-model-name "${SERVED:-qwen3.5-9b-gptq}" \
  --trust-remote-code \
  --tp-size 1 \
  --enable-session-radix-cache \
  --kv-cache-dtype "${KV_DTYPE:-fp8_e4m3}" \
  --attention-backend flashinfer \
  --linear-attn-prefill-backend triton \
  --linear-attn-decode-backend triton \
  --mamba-radix-cache-strategy extra_buffer \
  --mamba-ssm-dtype float32 \
  --mem-fraction-static 0.92 \
  --max-running-requests 8 \
  --cuda-graph-max-bs 8 \
  --mamba-full-memory-ratio "${MAMBA_RATIO:-0.42}" \
  --enable-hierarchical-cache \
  --hicache-write-policy write_back \
  --hicache-storage-backend extent \
  --hicache-storage-backend-extra-config "{\"max_size\": \"${MAX_SIZE:-120G}\", \"file_size\": \"${FILE_SIZE:-${MAX_SIZE:-120G}}\", \"min_free_space\": \"10G\"}" \
  --hicache-storage-prefetch-policy wait_complete \
  --enable-cache-report \
  --hicache-ratio "${HICACHE_RATIO:-1.3}" \
  --hicache-size 0 \
  --hicache-promotion-margin-tokens 2048 \
  --max-total-tokens 600000 \
  --reasoning-parser qwen3 \
  --tool-call-parser qwen3_coder \
  --enable-metrics \
  --admin-api-key "$L3_ADMIN_KEY" \
  --host 0.0.0.0 --port "${SGLANG_PORT:-8024}" \
  "${RH_ARGS[@]}"
