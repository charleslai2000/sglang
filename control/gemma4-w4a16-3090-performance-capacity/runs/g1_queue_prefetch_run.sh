#!/usr/bin/env bash
# Controlled queue-prefetch experiment (item 1): fixed working set, Host staging
# headroom, prefetch ON vs OFF, optional nsys cudaProfilerApi capture range.
set -Eeuo pipefail
ROOT=/home/ubuntu/workspaces/3rdparty/sglang-hicache
QC_OUT=${QC_OUT:?QC_OUT required}
QC_MODE=${QC_MODE:-on}          # on | off
QC_DEPTHS=${QC_DEPTHS:-64,128,256}
QC_CHURN=${QC_CHURN:-131072}
QC_NSYS=${QC_NSYS:-0}
QC_PROFILE=${QC_PROFILE:-0}
QC_PROFILE_SECONDS=${QC_PROFILE_SECONDS:-0}
QC_FLUSH=${QC_FLUSH:-0}
PORT=${QC_PORT:-31401}
LOCK=/tmp/f1-r16b-gpu-exclusive.lock

mkdir -p "$QC_OUT"
if ls "$QC_OUT"/wave-*.json >/dev/null 2>&1; then
  echo "OUTPUT_NOT_EMPTY" | tee "$QC_OUT/exit.txt"; exit 98
fi
# The inner service launcher takes $LOCK itself and refuses when it is busy, so
# this wrapper must not hold it: doing so made the service exit with its own
# GPU_LOCK_BUSY and the run failed as SERVER_FAILED.
if ss -ltn "( sport = :$PORT )" 2>/dev/null | grep -q LISTEN; then
  echo "PORT_BUSY:$PORT" | tee "$QC_OUT/exit.txt"; exit 91
fi
if pgrep -f 'sglang.launch_server' >/dev/null; then
  echo "GPU_PROCESS_BUSY" | tee "$QC_OUT/exit.txt"; exit 92
fi

case "$QC_MODE" in
  on)  EXTRA="--hicache-restore-wait-timeout-s 600" ;;
  off) EXTRA="--hicache-restore-wait-timeout-s 600 --enable-ready-horizon --ready-horizon-frontier-n 0" ;;
  *) echo "BAD_MODE:$QC_MODE" | tee "$QC_OUT/exit.txt"; exit 95 ;;
esac

{
  echo "mode=$QC_MODE depths=$QC_DEPTHS churn=$QC_CHURN nsys=$QC_NSYS profile=$QC_PROFILE"
  echo "head=$(git -C "$ROOT" rev-parse HEAD)"
  echo "extra_server_args=$EXTRA"
  echo "started=$(date -Is)"
} | tee "$QC_OUT/plan.txt"

export G1_PROD_OUT="$QC_OUT" G1_PROD_PORT=$PORT G1_PROD_KV=fp8_e5m2 G1_PROD_CONTEXT=131072 \
  G1_PROD_MAX_TOTAL_TOKENS=139264 G1_PROD_MEM_FRACTION=.90 G1_PROD_GRAPH_BS=32 \
  G1_PROD_RADIX=on G1_PROD_HICACHE=on G1_PROD_HICACHE_SIZE=8 G1_PROD_WARMUP=off \
  G1_PROD_EXPORT_REQUEST_METRICS=on G1_PROD_L3_DIR=$QC_OUT/l3-extent \
  G1_PROD_EXTENT_SIZE=67108864 G1_PROD_EXTENT_FILE_SIZE=34359738368 \
  G1_PROD_EXTENT_MAX_SIZE=34359738368 G1_PROD_EXTENT_MIN_FREE_SPACE=1073741824 \
  G1_PROD_EXTRA_SERVER_ARGS="$EXTRA" \
  SGLANG_TREE_LIFECYCLE_TRACE=1 G1_P0_EXPORT_TREE_EVENTS=1 \
  SGLANG_ENABLE_METRICS_DEVICE_TIMER=1

SERVER="$ROOT/control/gemma4-w4a16-3090-performance-capacity/runs/run_g1_prod_e5m2.sh"
PROBE_ARGS=(--metrics-dir "$QC_OUT/request-metrics" --extent-dir "$QC_OUT/l3-extent"
            --server-log "$QC_OUT/server.log" --out "$QC_OUT"
            --depths "$QC_DEPTHS" --churn-tokens "$QC_CHURN")
[ "$QC_PROFILE" = 1 ] && PROBE_ARGS+=(--start-profile --stop-profile --profile-seconds "$QC_PROFILE_SECONDS")
[ "$QC_FLUSH" = 1 ] && PROBE_ARGS+=(--flush-before-wave)

if [ "$QC_NSYS" = 1 ]; then
  mkdir -p "$QC_OUT/nsys"
  NSYS=(nsys profile --force-overwrite true -t cuda,nvtx
        --capture-range=cudaProfilerApi --capture-range-end=stop
        --cuda-flush-interval=1000 --sample=none --cpuctxsw=none
        -o "$QC_OUT/nsys/queue")
  "${NSYS[@]}" "$SERVER" >"$QC_OUT/launcher.log" 2>&1 &
else
  "$SERVER" >"$QC_OUT/launcher.log" 2>&1 &
fi
LAUNCHER=$!
cleanup() {
  kill -TERM "$LAUNCHER" 2>/dev/null || true
  wait "$LAUNCHER" 2>/dev/null || true
  pkill -TERM -f "port $PORT" 2>/dev/null || true
}
trap cleanup EXIT

for _ in $(seq 1 2400); do
  curl -fsS "http://127.0.0.1:$PORT/health" >/dev/null 2>&1 && break
  kill -0 "$LAUNCHER" 2>/dev/null || { echo SERVER_FAILED | tee "$QC_OUT/exit.txt"; exit 2; }
  sleep 1
done

set +e
timeout -k 60 5400 python3 "$(dirname "$0")/g1_queue_prefetch_probe.py" "${PROBE_ARGS[@]}"
PROBE=$?
python3 "$(dirname "$0")/g1_queue_prefetch_analyze.py" --run "$QC_OUT" --server-log "$QC_OUT/server.log"
ANALYZE=$?
echo "probe_exit=$PROBE analyze_exit=$ANALYZE" | tee "$QC_OUT/exit.txt"
exit 0
