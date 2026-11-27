#!/usr/bin/env bash
# T012 paired qualification: identical argv, only the post-load branch differs.
set -Eeuo pipefail
ROOT=/home/ubuntu/workspaces/3rdparty/sglang-hicache
VENV=/home/ubuntu/venvs/sglang-3090
OUT=$(cd "$(dirname "$0")" && pwd)
MODEL=/data/sglang-hicache/gemma4/model
AOT=/data/sglang-hicache/g2-quasar-runs/20261110T-g2-postrope-e5m2-quality/aot-sm86-package
OVERLAY=$ROOT/control/gemma4-w4a16-3090-performance-capacity/runs/overlay
RUNS=$ROOT/control/gemma4-w4a16-3090-performance-capacity/runs
LOCK=/tmp/f1-r16b-gpu-exclusive.lock
PORT=31412

exec 9>"$LOCK"
flock -n 9 || { echo LOCK_BUSY; exit 90; }
if ss -ltn | grep -q ":$PORT\\b"; then echo PORT_BUSY; exit 91; fi
if nvidia-smi --query-compute-apps=pid --format=csv,noheader | grep -q '[0-9]'; then
  echo GPU_BUSY; exit 92
fi

export PYTHONNOUSERSITE=1
export SGLANG_GEMMA4_SWA_POOL_TOKENS=65536
export PYTHONPATH="$OUT/auditlib:$RUNS:$AOT:$ROOT/python:$VENV/lib/python3.12/site-packages:$ROOT/python/sglang/kernels/aot/python:$OVERLAY"
export LD_LIBRARY_PATH="$VENV/lib/python3.12/site-packages/torch/lib:/usr/local/cuda-12.9/lib64"
export SGLANG_CACHE_DIR=/data/sglang-hicache/gemma4/cache
export HF_HOME=/data/sglang-hicache/gemma4/cache/hf-home
export HF_DATASETS_CACHE=/data/sglang-hicache/gemma4/cache/datasets
export SGLANG_HUMMING_USE_F16_ACCUM=0
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True

GEMM_PREFIXES="language_model.layers.0.self_attn.qkv_proj,language_model.layers.0.self_attn.o_proj,language_model.layers.0.mlp.gate_up_proj,language_model.layers.0.mlp.down_proj,language_model.layers.24.per_layer_projection,language_model.per_layer_model_projection"

cleanup_server() {
  local pid=$1
  kill -TERM "$pid" 2>/dev/null || true
  for _ in $(seq 1 60); do kill -0 "$pid" 2>/dev/null || break; sleep 1; done
  kill -KILL "$pid" 2>/dev/null || true
  wait "$pid" 2>/dev/null || true
}

RUN_START=$(date -u +%FT%TZ)
printf 'run_start=%s\n' "$RUN_START" > "$OUT/intent-status.txt"
printf 'argv=%s\n' "$OUT/launch-argv.txt" >> "$OUT/intent-status.txt"

for ARM in marlin humming; do
  DIR=$OUT/$ARM
  rm -rf "$DIR"
  mkdir -p "$DIR/audit"
  ARGS=(--model-path "$MODEL" --trust-remote-code --host 127.0.0.1 --port "$PORT"
        --context-length 32768 --max-running-requests 32 --mem-fraction-static .92
        --kv-cache-dtype fp8_e5m2 --attention-backend triton
        --cuda-graph-backend-decode full --cuda-graph-max-bs-decode 32
        --log-level info --skip-server-warmup --disable-radix-cache)
  printf '%q ' "${ARGS[@]}" > "$DIR/launch-argv.txt"
  printf '\n' >> "$DIR/launch-argv.txt"

  export T012_AUDIT_DIR="$DIR/audit"
  export T012_AUDIT_GEMM="$GEMM_PREFIXES"
  if [[ $ARM == humming ]]; then
    export SGLANG_CTWNA16_HUMMING=1
  else
    unset SGLANG_CTWNA16_HUMMING || true
  fi

  "$VENV/bin/python" -u -m sglang.launch_server "${ARGS[@]}" > "$DIR/server.log" 2>&1 &
  PID=$!
  echo "$PID" > "$DIR/server.pid"
  ready=0
  for _ in $(seq 1 600); do
    if curl -fsS --max-time 2 "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; then
      ready=1; break
    fi
    if ! kill -0 "$PID" 2>/dev/null; then echo "$ARM SERVER_DIED"; break; fi
    sleep 1
  done
  if [[ $ready != 1 ]]; then
    cleanup_server "$PID"
    pkill -TERM -f "sglang.launch_server .*--port $PORT" 2>/dev/null || true
    pkill -TERM -f "sglang.srt.managers.scheduler .*--port $PORT" 2>/dev/null || true
    printf 'arm=%s ready=0\n' "$ARM" >> "$OUT/intent-status.txt"
    exit 3
  fi
  curl -fsS "http://127.0.0.1:$PORT/model_info" > "$DIR/model-info.json"
  touch "$DIR/audit/capture-logits"
  "$VENV/bin/python" "$OUT/probe.py" "$PORT" "$DIR/probes.json" > "$DIR/probe.log" 2>&1
  rm -f "$DIR/audit/capture-logits"
  cp "$DIR/server.log" "$DIR/server-before-stop.log"
  cleanup_server "$PID"
  pkill -TERM -f "sglang.launch_server .*--port $PORT" 2>/dev/null || true
  pkill -TERM -f "sglang.srt.managers.scheduler .*--port $PORT" 2>/dev/null || true
  sleep 3
  nvidia-smi --query-gpu=timestamp,utilization.gpu,memory.used,memory.total \
    --format=csv > "$DIR/gpu-after.csv"
  printf 'arm=%s ready=1 probes=1\n' "$ARM" >> "$OUT/intent-status.txt"
done

"$VENV/bin/python" "$OUT/checkpoint_coverage.py" "$MODEL" "$OUT/checkpoint-textcore.json" \
  > "$OUT/checkpoint-coverage.log" 2>&1
set +e
"$VENV/bin/python" "$OUT/compare_arms.py" "$OUT" > "$OUT/compare.log" 2>&1
VERDICT=$?
set -e
printf 'run_end=%s\nverdict_exit=%s\n' "$(date -u +%FT%TZ)" "$VERDICT" >> "$OUT/intent-status.txt"
ss -ltnp | grep ":$PORT\\b" > "$OUT/port-after.txt" || true
nvidia-smi --query-gpu=memory.used,utilization.gpu --format=csv,noheader > "$OUT/gpu-final.csv"
printf 'PAIR_DONE verdict=%s\n' "$VERDICT"
exit "$VERDICT"
