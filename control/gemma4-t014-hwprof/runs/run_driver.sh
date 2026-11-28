#!/usr/bin/env bash
# T014 driver wrapper: production env, GPU lock, one Forward per process.
set -Eeuo pipefail
ROOT=/home/ubuntu/workspaces/3rdparty/sglang-hicache
VENV=/home/ubuntu/venvs/sglang-3090
AOT=/data/sglang-hicache/g2-quasar-runs/20261110T-g2-postrope-e5m2-quality/aot-sm86-package
LOCK=/tmp/f1-r16b-gpu-exclusive.lock

export PYTHONNOUSERSITE=1 SGLANG_GEMMA4_SWA_POOL_TOKENS=65536
export PYTHONPATH="$AOT:$ROOT/python:$VENV/lib/python3.12/site-packages:$ROOT/python/sglang/kernels/aot/python"
export LD_LIBRARY_PATH="$VENV/lib/python3.12/site-packages/torch/lib:/usr/local/cuda-12.9/lib64"
export SGLANG_CACHE_DIR=/data/sglang-hicache/gemma4/cache HF_HOME=/data/sglang-hicache/gemma4/cache/hf-home
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
export SGLANG_HUMMING_USE_F16_ACCUM=0
export SGLANG_T011_BF16_PREFIX_BUDGET_MB=128

exec 9>"$LOCK"
flock -n 9 || { echo GPU_LOCK_BUSY >&2; exit 90; }
exec "$VENV/bin/python" "$ROOT/control/gemma4-t014-hwprof/runs/t014_forward_driver.py" "$@"
