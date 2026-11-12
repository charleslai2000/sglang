#!/usr/bin/env bash
set -euo pipefail
ROOT=/home/ubuntu/workspaces/3rdparty/sglang-hicache
LOCK=/tmp/f1-r16b-gpu-exclusive.lock
MODEL=/data/models/gemma4-quasar-q4_0/gemma-4-E4B-it-QUASAR-Q4_0.gguf
OUT=${1:?usage: run-llama-mmq-compare.sh OUTPUT-DIR}
BUILD=/data/sglang-hicache/g2-quasar-runs/llamacpp-cuda-sm86-mmq-20261112
mkdir -p "$OUT/weights"
exec 9>"$LOCK"
flock -n 9 || { echo 'exclusive GPU lock unavailable' >&2; exit 2; }
nvidia-smi --query-gpu=memory.used,utilization.gpu --format=csv,noheader
source /home/ubuntu/venvs/sglang-3090/bin/activate
cd "$ROOT"
export G2_LLAMA_MMQ_RUN_DIR="$OUT"
export LD_LIBRARY_PATH="$BUILD/bin:/usr/local/cuda-12.9/lib64:${LD_LIBRARY_PATH:-}"
python experiments/g2-quasar-gguf-matmul-optimization/compare_llama_aot.py >"$OUT/paired-results.json"
ss -ltnp | grep 31382 && exit 3 || true
nvidia-smi --query-gpu=memory.used,utilization.gpu --format=csv,noheader
