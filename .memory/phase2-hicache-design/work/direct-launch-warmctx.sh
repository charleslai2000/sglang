#!/usr/bin/env bash
# Warm-context (exp-2) launch wrapper -- three-tier cache warm-turn latency.
# Based on direct-launch-gate1-s32.sh; config-only differences:
#   --max-total-tokens  driven by MAX_TOTAL_TOKENS (env, default 65536) --
#                       64K/128K tiers pass a higher value (e.g. 131072/196608)
#   --min-free-space    driven by MIN_FREE (env, default 10G) so the extent
#                       backend can tolerate the near-full /data on the runner
#   --max-mamba-cache-size 32  (as the s32 precedent; single-concurrency
#                       latency test, pool is not the bottleneck)
# All other flags identical to the gate2-s32k8 precedent.
set -euo pipefail
export SGLANG_ENABLE_UNIFIED_RADIX_TREE=1
export MAX_JOBS="${MAX_JOBS:-1}"
export CUDA_HOME="${CUDA_HOME:-/root/miniconda3/envs/sglang-dev/lib/python3.10/site-packages/nvidia/cu13}"
export CPLUS_INCLUDE_PATH="${CPLUS_INCLUDE_PATH:-/root/miniconda3/envs/sglang-dev/include}"
export LIBRARY_PATH="${LIBRARY_PATH:-/root/miniconda3/envs/sglang-dev/lib}"
export LD_LIBRARY_PATH="/root/miniconda3/envs/sglang-dev/lib:${CUDA_HOME}/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export SGLANG_HICACHE_FILE_BACKEND_STORAGE_DIR="$STORAGE_DIR"
export SGLANG_HICACHE_FILE_BACKEND_MAX_SIZE="${MAX_SIZE:-20G}"
export SGLANG_HICACHE_FILE_BACKEND_MIN_FREE_SPACE="${MIN_FREE:-10G}"
export SGLANG_HICACHE_FILE_BACKEND_ENABLE_METADATA_CACHE=true
if [ "$L3_BACKEND" = "extent" ]; then
  export SGLANG_HICACHE_EXTENT_BACKEND_STORAGE_DIR="$STORAGE_DIR"
  export SGLANG_HICACHE_EXTENT_BACKEND_MAX_SIZE="${MAX_SIZE:-20G}"
  export SGLANG_HICACHE_EXTENT_BACKEND_MIN_FREE_SPACE="${MIN_FREE:-10G}"
fi
KEYFILE="${KEYFILE:-/opt/sglang/l3-admin-key}"
L3_ADMIN_KEY=$(cat "$KEYFILE")
exec /root/miniconda3/envs/sglang-patch/bin/python3 -m sglang.launch_server \
  --model-path "${MODEL_PATH:-/root/models/Qwen3.5-9B-w4a16}" \
  --served-model-name "${SERVED:-qwen3.5-9b-gptq}" \
  --trust-remote-code \
  --tp-size 1 \
  --kv-cache-dtype "${KV_DTYPE:-bf16}" \
  --attention-backend flashinfer \
  --linear-attn-prefill-backend triton \
  --linear-attn-decode-backend triton \
  --mamba-radix-cache-strategy extra_buffer \
  --mamba-ssm-dtype float32 \
  --mem-fraction-static 0.92 \
  --max-running-requests 8 \
  --cuda-graph-max-bs 8 \
  --enable-hierarchical-cache \
  --hicache-write-policy write_back \
  --hicache-storage-backend "$L3_BACKEND" \
  --hicache-storage-backend-extra-config "{\"max_size\": \"${MAX_SIZE:-20G}\", \"min_free_space\": \"${MIN_FREE:-10G}\"}" \
  --hicache-storage-prefetch-policy wait_complete \
  --enable-cache-report \
  --hicache-ratio "${HICACHE_RATIO:-1.5}" \
  --hicache-size "${HICACHE_SIZE:-0}" \
  --hicache-promotion-margin-tokens "${PROMO_MARGIN:-2048}" \
  --max-total-tokens "${MAX_TOTAL_TOKENS:-65536}" \
  --reasoning-parser qwen3 \
  --tool-call-parser qwen3_coder \
  --enable-metrics \
  --max-mamba-cache-size 32 \
  --admin-api-key "$L3_ADMIN_KEY" \
  --host 0.0.0.0 --port "${SGLANG_PORT:-8024}"
