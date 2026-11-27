#!/usr/bin/env bash
set -Eeuo pipefail
ROOT=/home/ubuntu/workspaces/3rdparty/sglang-hicache; VENV=/home/ubuntu/venvs/sglang-3090
OUT=$(cd "$(dirname "$0")" && pwd); MODEL=/data/sglang-hicache/gemma4/model
AOT=/data/sglang-hicache/g2-quasar-runs/20261110T-g2-postrope-e5m2-quality/aot-sm86-package
OVERLAY=$ROOT/control/gemma4-w4a16-3090-performance-capacity/runs/overlay
RUNS=$ROOT/control/gemma4-w4a16-3090-performance-capacity/runs
LOCK=/tmp/f1-r16b-gpu-exclusive.lock; PORT=31412
exec 9>"$LOCK"; flock -n 9 || { echo LOCK_BUSY; exit 90; }
ss -ltn | grep -q ":$PORT\\b" && { echo PORT_BUSY; exit 91; } || true
nvidia-smi --query-compute-apps=pid --format=csv,noheader | grep -q '[0-9]' && { echo GPU_BUSY; exit 92; } || true
export PYTHONNOUSERSITE=1 SGLANG_GEMMA4_SWA_POOL_TOKENS=65536
export PYTHONPATH="$RUNS:$AOT:$ROOT/python:$VENV/lib/python3.12/site-packages:$ROOT/python/sglang/kernels/aot/python:$OVERLAY"
export LD_LIBRARY_PATH="$VENV/lib/python3.12/site-packages/torch/lib:/usr/local/cuda-12.9/lib64"
export SGLANG_CACHE_DIR=/data/sglang-hicache/gemma4/cache HF_HOME=/data/sglang-hicache/gemma4/cache/hf-home HF_DATASETS_CACHE=/data/sglang-hicache/gemma4/cache/datasets
export SGLANG_HUMMING_USE_F16_ACCUM=0 PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
cleanup_server(){ local p=$1; kill -TERM "$p" 2>/dev/null || true; for i in $(seq 1 45); do kill -0 "$p" 2>/dev/null || break; sleep 1; done; kill -KILL "$p" 2>/dev/null || true; wait "$p" 2>/dev/null || true; }
RUN_START=$(date -u +%FT%TZ)
for ARM in marlin humming; do
  DIR=$OUT/$ARM; mkdir -p "$DIR"
  ARGS=(--model-path "$MODEL" --trust-remote-code --host 127.0.0.1 --port "$PORT" --context-length 32768 --max-running-requests 32 --mem-fraction-static .92 --kv-cache-dtype fp8_e5m2 --attention-backend triton --cuda-graph-backend-decode full --cuda-graph-max-bs-decode 32 --log-level info --skip-server-warmup --disable-radix-cache)
  printf '%q ' "${ARGS[@]}" > "$DIR/launch-argv.txt"; printf '\n' >> "$DIR/launch-argv.txt"
  export T012_LOGITS_PATH="$DIR/logits.pt" T012_HUMMING_MARKER="$DIR/humming-layers.tsv"
  if [[ $ARM == humming ]]; then export SGLANG_CTWNA16_HUMMING=1; else unset SGLANG_CTWNA16_HUMMING || true; fi
  rm -f "$DIR/humming-layers.tsv"
  "$VENV/bin/python" -u "$OUT/capture_server.py" "${ARGS[@]}" > "$DIR/server.log" 2>&1 & PID=$!
  echo "$PID" > "$DIR/server.pid"
  ready=0
  for i in $(seq 1 600); do if curl -fsS --max-time 2 "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; then ready=1; break; fi; kill -0 "$PID" 2>/dev/null || { echo "$ARM SERVER_DIED"; break; }; sleep 1; done
  if [[ $ready != 1 ]]; then
    cleanup_server "$PID"
    pkill -TERM -f "sglang.launch_server .*--port $PORT" 2>/dev/null || true
    pkill -TERM -f "sglang.srt.managers.scheduler .*--port $PORT" 2>/dev/null || true
    exit 3
  fi
  curl -fsS "http://127.0.0.1:$PORT/model_info" > "$DIR/model-info.json"
  "$VENV/bin/python" "$OUT/probe.py" "$PORT" "$DIR/probes.json" > "$DIR/probe.log" 2>&1
  cp "$DIR/server.log" "$DIR/server-before-stop.log"
  cleanup_server "$PID"
  pkill -TERM -f "sglang.launch_server .*--port $PORT" 2>/dev/null || true
  pkill -TERM -f "sglang.srt.managers.scheduler .*--port $PORT" 2>/dev/null || true
  PID=; nvidia-smi --query-gpu=timestamp,utilization.gpu,memory.used,memory.total --format=csv > "$DIR/gpu-after.csv"
done
printf 'run_start=%s\nrun_end=%s\nexit=0\n' "$RUN_START" "$(date -u +%FT%TZ)" > "$OUT/exit.txt"
ss -ltnp | grep ":$PORT\\b" > "$OUT/port-after.txt" || true
nvidia-smi --query-gpu=memory.used,utilization.gpu --format=csv,noheader > "$OUT/gpu-final.csv"
printf 'PAIR_DONE\n'
