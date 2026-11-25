#!/usr/bin/env bash
# Hold the project GPU lock around one verified service + driver invocation.
set -Eeuo pipefail
ROOT=/home/ubuntu/workspaces/3rdparty/sglang-hicache
RUNS=$ROOT/control/gemma4-w4a16-3090-performance-capacity/runs
DATA=/data/sglang-hicache/gemma4
VENV=/home/ubuntu/venvs/sglang-3090
OUT=${G1_EXEC_OUT:?set G1_EXEC_OUT}
PORT=${G1_PROD_PORT:-31401}
LOCK=/tmp/f1-r16b-gpu-exclusive.lock
mkdir -p "$OUT"
exec 9>"$LOCK"
flock -n 9 || { echo GPU_LOCK_BUSY >&2; exit 90; }
if ss -ltn | grep -q ":$PORT\\b"; then echo "PORT_BUSY:$PORT" >&2; exit 91; fi
if nvidia-smi --query-compute-apps=pid --format=csv,noheader | grep -q '[0-9]'; then echo GPU_PROCESS_BUSY >&2; exit 92; fi
export G1_PROD_OUT="$OUT/service" G1_PROD_PORT="$PORT" G1_GPU_LOCK_HELD=1
export G1_PROD_KV=fp8_e5m2 G1_PROD_CONTEXT=${G1_PROD_CONTEXT:-131072}
export G1_PROD_MAX_RUNNING=${G1_PROD_MAX_RUNNING:-32} G1_PROD_MEM_FRACTION=${G1_PROD_MEM_FRACTION:-.90}
export G1_PROD_GRAPH_BS=${G1_PROD_GRAPH_BS:-32} G1_PROD_RADIX=on
export G1_PROD_HICACHE=${G1_PROD_HICACHE:-on} G1_PROD_HICACHE_SIZE=${G1_PROD_HICACHE_SIZE:-2}
export G1_PROD_L3_DIR="$OUT/service/l3-extent" G1_PROD_WARMUP=${G1_PROD_WARMUP:-off}
export SGLANG_TREE_LIFECYCLE_TRACE=${G1_TRACE:-0} G1_P0_EXPORT_TREE_EVENTS=${G1_TRACE:-0}
# Close FD 9 in the child launcher. This wrapper alone owns the flock until its
# cleanup has reaped the full child tree, including the CUDA service/monitor.
"$RUNS/run_g1_prod_e5m2.sh" 9>&- > "$OUT/launcher.log" 2>&1 &
LAUNCHER=$!
cleanup() {
  rc=$?
  trap - EXIT INT TERM
  if kill -0 "$LAUNCHER" 2>/dev/null; then
    kill -TERM "$LAUNCHER" 2>/dev/null || true
    for _ in $(seq 1 90); do kill -0 "$LAUNCHER" 2>/dev/null || break; sleep 1; done
    kill -KILL "$LAUNCHER" 2>/dev/null || true
    wait "$LAUNCHER" 2>/dev/null || true
  fi
  nvidia-smi --query-gpu=timestamp,utilization.gpu,memory.used --format=csv,noheader > "$OUT/gpu-after-wrapper.csv" 2>&1 || true
  ss -ltnp | grep ":$PORT\\b" > "$OUT/port-after-wrapper.txt" 2>&1 || true
  exit "$rc"
}
trap cleanup EXIT
trap 'exit 143' TERM
trap 'exit 130' INT
READY=0
for _ in $(seq 1 1200); do
  if curl -fsS "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; then READY=1; break; fi
  if ! kill -0 "$LAUNCHER" 2>/dev/null; then wait "$LAUNCHER" || true; echo LAUNCHER_EXITED >&2; exit 2; fi
  sleep 1
done
[[ $READY == 1 ]] || { echo SERVICE_READINESS_TIMEOUT >&2; exit 3; }
printf 'service_ready=1\n' > "$OUT/runner.status"
DRIVER=(--url "http://127.0.0.1:$PORT" --action "${G1_DRIVER_ACTION:-warm}" \
  --fixture "${G1_DRIVER_FIXTURE:?set G1_DRIVER_FIXTURE}" --out "$OUT/client" \
  --count "${G1_DRIVER_COUNT:-32}" --max-parallel "${G1_DRIVER_PARALLEL:-32}" \
  --new-tokens "${G1_DRIVER_NEW_TOKENS:-256}")
if [[ -n ${G1_DRIVER_PROMPTS:-} ]]; then DRIVER+=(--prompt-file "$G1_DRIVER_PROMPTS"); fi
if [[ -n ${G1_DRIVER_RESTORE_INDICES:-} ]]; then DRIVER+=(--restore-indices "$G1_DRIVER_RESTORE_INDICES"); fi
if [[ -n ${G1_DRIVER_REPEAT_INDICES:-} ]]; then DRIVER+=(--repeat-indices "$G1_DRIVER_REPEAT_INDICES"); fi
"$VENV/bin/python" "$RUNS/g1_shared_prefix_hicache.py" "${DRIVER[@]}" \
  > "$OUT/client.stdout" 2> "$OUT/client.stderr" || { cat "$OUT/client.stderr" >&2; exit 4; }
printf 'client_complete=1\n' >> "$OUT/runner.status"
# Default is a bounded one-shot run: return after the driver and let cleanup
# stop the service/reap the launcher. Long-lived sessions are opt-in only.
if [[ ${G1_KEEP_SERVICE:-0} == 1 ]]; then
  while [[ ! -e "$OUT/stop" ]]; do
    if ! kill -0 "$LAUNCHER" 2>/dev/null; then wait "$LAUNCHER" || true; exit 5; fi
    sleep 1
  done
fi
exit 0
