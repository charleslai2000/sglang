#!/usr/bin/env bash
# Measure the next-token distribution at the single divergent position, in both
# backends, using the same launch argv as the paired qualification run.
set -Eeuo pipefail
ROOT=/home/ubuntu/workspaces/3rdparty/sglang-hicache
VENV=/home/ubuntu/venvs/sglang-3090
OUT=$(cd "$(dirname "$0")" && pwd)
MODEL=/data/sglang-hicache/gemma4/model
AOT=/data/sglang-hicache/g2-quasar-runs/20261110T-g2-postrope-e5m2-quality/aot-sm86-package
OVERLAY=$ROOT/control/gemma4-w4a16-3090-performance-capacity/runs/overlay
RUNS=$ROOT/control/gemma4-w4a16-3090-performance-capacity/runs
AUDITLIB=$OUT/auditlib
PORT=31412

exec 9>/tmp/f1-r16b-gpu-exclusive.lock
flock -n 9 || { echo LOCK_BUSY; exit 90; }
if ss -ltn | grep -q ":$PORT\\b"; then echo PORT_BUSY; exit 91; fi

export PYTHONNOUSERSITE=1 SGLANG_GEMMA4_SWA_POOL_TOKENS=65536
export PYTHONPATH="$AUDITLIB:$RUNS:$AOT:$ROOT/python:$VENV/lib/python3.12/site-packages:$ROOT/python/sglang/kernels/aot/python:$OVERLAY"
export LD_LIBRARY_PATH="$VENV/lib/python3.12/site-packages/torch/lib:/usr/local/cuda-12.9/lib64"
export SGLANG_CACHE_DIR=/data/sglang-hicache/gemma4/cache
export HF_HOME=/data/sglang-hicache/gemma4/cache/hf-home
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
export SGLANG_HUMMING_USE_F16_ACCUM=0

ARGS=(--model-path "$MODEL" --trust-remote-code --host 127.0.0.1 --port "$PORT"
      --context-length 32768 --max-running-requests 32 --mem-fraction-static .92
      --kv-cache-dtype fp8_e5m2 --attention-backend triton
      --cuda-graph-backend-decode full --cuda-graph-max-bs-decode 32 --log-level info
      --skip-server-warmup --disable-radix-cache)

for ARM in marlin humming; do
  DIR=$OUT/divergence/$ARM
  rm -rf "$DIR"; mkdir -p "$DIR"
  cp "$OUT/divergence-input.json" "$OUT/divergence/divergence-input.json" 2>/dev/null || true
  export T012_AUDIT_DIR="$DIR"
  unset T012_AUDIT_GEMM || true
  if [[ $ARM == humming ]]; then export SGLANG_CTWNA16_HUMMING=1; else unset SGLANG_CTWNA16_HUMMING || true; fi
  "$VENV/bin/python" -u -m sglang.launch_server "${ARGS[@]}" > "$DIR/server.log" 2>&1 &
  PID=$!
  ready=0
  for _ in $(seq 1 600); do
    if curl -fsS --max-time 2 "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; then ready=1; break; fi
    kill -0 "$PID" 2>/dev/null || { echo "$ARM SERVER_DIED"; tail -20 "$DIR/server.log"; exit 3; }
    sleep 1
  done
  [[ $ready == 1 ]]
  "$VENV/bin/python" "$OUT/divergence_logprob_probe.py" "$PORT" "$OUT/divergence" "$ARM" > "$DIR/logprob.log" 2>&1
  kill -TERM "$PID" 2>/dev/null || true
  for _ in $(seq 1 60); do kill -0 "$PID" 2>/dev/null || break; sleep 1; done
  kill -KILL "$PID" 2>/dev/null || true
  wait "$PID" 2>/dev/null || true
  pkill -TERM -f "sglang.srt.managers.scheduler .*--port $PORT" 2>/dev/null || true
done

"$VENV/bin/python" "$OUT/divergence_analysis.py" "$OUT/divergence" | tee "$OUT/divergence/summary.txt" || true
