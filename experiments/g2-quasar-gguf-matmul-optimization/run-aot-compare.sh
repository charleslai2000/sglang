#!/usr/bin/env bash
set -euo pipefail
ROOT=/home/ubuntu/workspaces/3rdparty/sglang-hicache
LOCK=/tmp/f1-r16b-gpu-exclusive.lock
OUT=${1:?usage: run-aot-compare.sh OUTPUT.json}
exec 9>"$LOCK"
flock -n 9 || { echo 'exclusive GPU lock unavailable' >&2; exit 2; }
nvidia-smi --query-gpu=memory.used,utilization.gpu --format=csv,noheader
source /home/ubuntu/venvs/sglang-3090/bin/activate
cd "$ROOT"
python experiments/g2-quasar-gguf-matmul-optimization/benchmark_existing_aot.py --output "$OUT"
torch_pid=''
ss -ltnp | grep 31382 && exit 3 || true
nvidia-smi --query-gpu=memory.used,utilization.gpu --format=csv,noheader
