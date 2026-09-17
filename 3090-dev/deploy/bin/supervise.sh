#!/usr/bin/env bash
# supervise.sh — long-lived GPU-lock holder + server launcher.
#
# Invoked by start.sh (never by hand unless debugging).  This is the process
# that owns the canonical flock for the ENTIRE server lifetime, exactly as the
# frozen GPU-lock rule requires:
#
#     "Every GPU-owning task must flock -n /tmp/opencode/gpu-3090.lock for its
#      entire server lifetime."
#
# It writes state/ready/<role>.ready only after /health returns 200, so
# start.sh can distinguish "launched" from "serving".
#
# Usage: supervise.sh <prod|test> <tree> <port> <run_id> <namespace> <log_dir>

set -euo pipefail
# shellcheck source=/dev/null
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

ROLE="$1"; TREE="$2"; PORT="$3"; RUN_ID="$4"; NAMESPACE="$5"; LOG_DIR="$6"
READY_DIR="$SCAFFOLD_ROOT/state/ready"
mkdir -p "$READY_DIR"
READY="$READY_DIR/$ROLE.ready"
rm -f "$READY"

CONSOLE="$LOG_DIR/server.console.log"

cleanup() {
  local rc=$?
  warn "supervisor exiting rc=$rc; releasing GPU lock"
  state_write_free "supervisor-exit"
  rm -f "$READY"
  exit "$rc"
}
trap cleanup EXIT

# ---- hold the canonical lock for the whole server lifetime -------------------
gpu_lock_acquire 9 "supervise-$ROLE-$RUN_ID" || die "could not acquire canonical GPU lock" 1
LOCK_GEN="$(lock_generation)"

# ---- launch -----------------------------------------------------------------
log "supervisor launching $ROLE on port $PORT (tree=$TREE)"
setsid env \
  SGLANG_PORT="$PORT" \
  SGLANG_PROFILE="${SGLANG_PROFILE:-perf}" \
  SGLANG_RUN_ID="$RUN_ID" \
  SGLANG_L3_ROOT="$L3_ROOT" \
  SGLANG_LOG_DIR="$LOG_DIR" \
  bash "$(tree_launcher "$TREE")" \
  >>"$CONSOLE" 2>&1 < /dev/null &
SERVER_PID=$!

echo "$SERVER_PID" >"$PID_DIR/$ROLE.pid"
echo "$RUN_ID"     >"$PID_DIR/$ROLE.run_id"
echo "$NAMESPACE"  >"$PID_DIR/$ROLE.namespace"
echo "$TREE"       >"$PID_DIR/$ROLE.tree"
echo "$$"          >"$PID_DIR/$ROLE.supervisor.pid"

state_write "$ROLE" "$SERVER_PID" "$PORT" "$RUN_ID" "$NAMESPACE" "$TREE" \
            "LOCAL-PROD-v1.1.2" "starting"

# ---- runtime environment verification ---------------------------------------
sleep 3
if ! [ -d "/proc/$SERVER_PID" ]; then
  die "launcher exited immediately; see $CONSOLE" 1
fi
PROC_PYTHONPATH="$(tr '\0' '\n' <"/proc/$SERVER_PID/environ" 2>/dev/null | sed -n 's/^PYTHONPATH=//p' || true)"
PROC_CVD="$(tr '\0' '\n' <"/proc/$SERVER_PID/environ" 2>/dev/null | sed -n 's/^CUDA_VISIBLE_DEVICES=//p' || true)"
log "/proc/$SERVER_PID/environ PYTHONPATH=$PROC_PYTHONPATH CUDA_VISIBLE_DEVICES=$PROC_CVD"
if [ "${PROC_PYTHONPATH#"$TREE/src/python"}" = "$PROC_PYTHONPATH" ]; then
  die "runtime PYTHONPATH not inside tree: '$PROC_PYTHONPATH'" 1
fi
if [ "$PROC_CVD" != "$GPU_UUID" ]; then
  die "runtime CUDA_VISIBLE_DEVICES not the 3090 UUID: '$PROC_CVD'" 1
fi

# ---- health + cold start ----------------------------------------------------
START_TS="$7"
HEALTH_DEADLINE=$(( SECONDS + 2400 ))
while [ "$SECONDS" -lt "$HEALTH_DEADLINE" ]; do
  if ! [ -d "/proc/$SERVER_PID" ]; then die "server exited during startup; see $CONSOLE" 1; fi
  code="$(CUDA_VISIBLE_DEVICES=999 curl -s -o /dev/null -w '%{http_code}' \
          --max-time 5 "http://127.0.0.1:$PORT/health" 2>/dev/null || echo 000)"
  if [ "$code" = "200" ]; then break; fi
  sleep 3
done
code="$(CUDA_VISIBLE_DEVICES=999 curl -s -o /dev/null -w '%{http_code}' \
        --max-time 5 "http://127.0.0.1:$PORT/health" 2>/dev/null || echo 000)"
[ "$code" = "200" ] || die "health timeout; see $CONSOLE" 1

END_TS="$(date +%s.%N)"
COLD_START="$(CUDA_VISIBLE_DEVICES=999 python3 -c "print(f'{$END_TS-$START_TS:.1f}')")"
log "COLD START (launch -> /health 200): ${COLD_START}s"

{
  echo "role=$ROLE"
  echo "pid=$SERVER_PID"
  echo "supervisor_pid=$$"
  echo "port=$PORT"
  echo "tree=$TREE"
  echo "run_id=$RUN_ID"
  echo "namespace=$NAMESPACE"
  echo "lock_generation=$LOCK_GEN"
  echo "cold_start_s=$COLD_START"
  echo "started_at_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
} >"$RUN_DIR/$ROLE.run"

state_write "$ROLE" "$SERVER_PID" "$PORT" "$RUN_ID" "$NAMESPACE" "$TREE" \
            "LOCAL-PROD-v1.1.2" "serving"
touch "$READY"
log "=== $ROLE UP: pid=$SERVER_PID port=$PORT cold_start=${COLD_START}s ==="

# ---- hold the lock until the server exits -----------------------------------
# `wait` blocks until the server terminates; the flock on fd 9 is held the
# whole time.  SIGTERM to the supervisor is forwarded to the server by the
# stop script, which then waits for this process to release the lock.
wait "$SERVER_PID" || true
log "$ROLE server exited; supervisor releasing lock"
exit 0
