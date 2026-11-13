#!/usr/bin/env bash
set -Eeuo pipefail
ROOT=/home/ubuntu/workspaces/3rdparty/sglang-hicache
RUNS=/data/sglang-hicache/g2-quasar-runs
MODEL=/data/models/gemma4-quasar-q4_0/gemma-4-E4B-it-QUASAR-Q4_0.gguf
LOCK=/tmp/f1-r16b-gpu-exclusive.lock
BASE=${G2_NEEDLE_RUN_TAG:-$(date -u +%Y%m%dT%H%M%SZ)-quasar-needle}
OUT=$RUNS/$BASE
mkdir -p "$OUT"
exec 9>"$LOCK"; flock -n 9 || { echo GPU_LOCK_BUSY >&2; exit 90; }
export PYTHONNOUSERSITE=1
export PYTHONPATH="/tmp/g2-quality-head-kernel:$RUNS/aot-sm86-package:$ROOT/python:/home/ubuntu/venvs/sglang-3090/lib/python3.12/site-packages:$ROOT/python/sglang/kernels/aot/python"
export SGLANG_ENABLE_JIT_DEEPGEMM=0
cleanup(){
  for port in 31221 31222; do for p in $(pgrep -f "sglang.launch_server.*--port $port" || true); do kill -TERM "$p" 2>/dev/null || true; done; done
  sleep 5
  nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader > "$OUT/gpu-final.csv" 2>/dev/null || true
}
trap cleanup EXIT INT TERM
for arm in bf16 e5m2; do
  if [[ $arm == bf16 ]]; then dtype=bf16; port=31221; else dtype=fp8_e5m2; port=31222; fi
  d=$OUT/$arm; mkdir -p "$d"
  PYTHONPATH="$PYTHONPATH" /home/ubuntu/venvs/sglang-3090/bin/python - <<'PY'
import sglang.kernels.ops.attention.extend_attention as e
from pathlib import Path
assert e.__file__.startswith('/tmp/g2-quality-head-kernel/')
assert 'BF16_KV_COMPUTE' not in Path(e.__file__).read_text()
PY
  (cd /tmp; setsid /home/ubuntu/venvs/sglang-3090/bin/python -m sglang.launch_server \
    --model-path "$MODEL" --tokenizer-path "$MODEL" --load-format gguf --quantization gguf \
    --dtype bfloat16 --kv-cache-dtype "$dtype" --context-length 40000 --max-total-tokens 42000 \
    --mem-fraction-static 0.88 --chunked-prefill-size 2048 --attention-backend triton \
    --disable-prefill-cuda-graph --disable-decode-cuda-graph --disable-radix-cache \
    --max-running-requests 1 --host 127.0.0.1 --port "$port" --random-seed 666360643 --log-level info) >"$d/server.log" 2>&1 &
  pid=$!; echo "$pid" >"$d/server.pid"; ready=0
  for _ in $(seq 1 720); do if curl -fsS "http://127.0.0.1:$port/model_info" >"$d/model-info.json" 2>/dev/null; then ready=1; break; fi; if ! kill -0 "$pid" 2>/dev/null; then tail -100 "$d/server.log"; exit 2; fi; sleep 1; done
  [[ $ready == 1 ]] || { echo "server readiness timeout $arm" >&2; exit 3; }
  for n in 16384 32768; do
    /home/ubuntu/venvs/sglang-3090/bin/python "$ROOT/control/g2-rtx3090-quasar-q4_0-fp8kv/eval_paired_needle.py" --arm "$arm" --base-url "http://127.0.0.1:$port" --out "$d" --target-tokens "$n"
  done
  for p in $(pgrep -f "sglang.launch_server.*--port $port" || true); do kill -TERM "$p" 2>/dev/null || true; done
  for _ in $(seq 1 120); do ss -ltnp | grep -q ":${port}\\b" || break; sleep 1; done
  ss -ltnp | grep -q ":${port}\\b" && { echo "port remains $port" >&2; exit 4; }
  nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader >"$d/gpu-after.csv"
done
printf '%s\n' "$OUT"
