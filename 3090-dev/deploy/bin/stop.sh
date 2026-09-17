#!/usr/bin/env bash
# stop.sh — stop a service we own and release the GPU.
#
# Usage: stop.sh <prod|test|all>
#
# Safety: the server pid is identity-checked (must be a launch_server for this
# tree on this port) before any signal.  A pid we do not recognise is NOT
# signalled and the script exits non-zero.  Never uses broad pkill patterns.

set -euo pipefail
# shellcheck source=/dev/null
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

TARGET="${1:?usage: stop.sh <prod|test|all>}"
RC=0

stop_one() {
  local role="$1"
  local pidfile="$PID_DIR/$role.pid"
  [ -f "$pidfile" ] || { log "$role: no pid file; nothing to stop"; return 0; }
  local pid; pid="$(cat "$pidfile")"
  local tree=""; [ -f "$PID_DIR/$role.tree" ] && tree="$(cat "$PID_DIR/$role.tree")"
  local port
  case "$role" in prod) port="$PROD_PORT" ;; test) port="$TEST_PORT" ;; *) port="-" ;; esac

  # Supervisor holds the lock; stop it first so it releases the flock, then
  # ensure the server is gone.
  local suppfile="$PID_DIR/$role.supervisor.pid"
  if [ -f "$suppfile" ]; then
    local sp; sp="$(cat "$suppfile")"
    if [ -d "/proc/$sp" ] && pid_matches "$sp" "supervise.sh" "$role"; then
      log "$role: terminating supervisor pid=$sp (SIGTERM)"
      kill -TERM "$sp" 2>/dev/null || true
    fi
  fi

  if stop_owned_server "$pid" "$tree" "$port"; then
    log "$role: stopped"
  else
    warn "$role: stop did not complete cleanly"
    RC=1
  fi

  if [ -f "$suppfile" ]; then
    local sp2; sp2="$(cat "$suppfile")"
    local d=$(( SECONDS + 60 ))
    while [ -d "/proc/$sp2" ] && [ "$SECONDS" -lt "$d" ]; do sleep 2; done
  fi

  rm -f "$pidfile" "$suppfile" "$PID_DIR/$role.run_id" \
        "$PID_DIR/$role.namespace" "$PID_DIR/$role.tree" \
        "$SCAFFOLD_ROOT/state/ready/$role.ready"
  return 0
}

case "$TARGET" in
  prod) stop_one prod ;;
  test) stop_one test ;;
  all)  stop_one test; stop_one prod ;;
  *) die "unknown target '$TARGET' (want prod|test|all)" 2 ;;
esac

# If nothing is left running, publish a free state.
if [ -z "$(gpu_material_holder)" ] && [ "$(lock_is_held)" != "true" ]; then
  state_write_free "stopped"
  log "GPU released; state published as free"
else
  state_write_free "stopped-but-lock-or-app-remains"
fi
exit "$RC"
