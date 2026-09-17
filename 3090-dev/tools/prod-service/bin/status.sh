#!/usr/bin/env bash
# status.sh — owner-visible GPU ownership + service state.
#
# Usage: status.sh [--json]
#
# Read-only.  Never signals anything and never takes the lock.

set -euo pipefail
# shellcheck source=/dev/null
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

JSON=0
[ "${1:-}" = "--json" ] && JSON=1

probe_health() {
  local port="$1"
  local code
  code="$(CUDA_VISIBLE_DEVICES=999 curl -s -o /dev/null -w '%{http_code}' \
          --max-time 3 "http://127.0.0.1:$port/health" 2>/dev/null || echo 000)"
  [ "$code" = "200" ] && echo up || echo down
}

svc_json() {
  local role="$1" port="$2"
  local pid="-" run="-" ns="-" tree="-" health="down"
  [ -f "$PID_DIR/$role.pid" ] && pid="$(cat "$PID_DIR/$role.pid")"
  [ -f "$PID_DIR/$role.run_id" ] && run="$(cat "$PID_DIR/$role.run_id")"
  [ -f "$PID_DIR/$role.namespace" ] && ns="$(cat "$PID_DIR/$role.namespace")"
  [ -f "$PID_DIR/$role.tree" ] && tree="$(cat "$PID_DIR/$role.tree")"
  local alive=false
  [ "$pid" != "-" ] && [ -d "/proc/$pid" ] && alive=true
  [ "$alive" = "true" ] && health="$(probe_health "$port")"
  jq -n --arg role "$role" --arg port "$port" --arg pid "$pid" \
        --arg run "$run" --arg ns "$ns" --arg tree "$tree" \
        --argjson alive "$alive" --arg health "$health" \
        '{role:$role, port:($port|tonumber), pid:($pid|if .=="-" then null else tonumber end),
          alive:$alive, health:$health, run_id:$run, l3_namespace:$ns, tree:$tree}'
}

LOCK_HELD="$(lock_is_held)"
# Normalise the holder to a single JSON object; never hand jq a double brace.
LOCK_HOLDER="$(lock_holder_json | jq -c . 2>/dev/null || true)"
[ -n "$LOCK_HOLDER" ] || LOCK_HOLDER='{}'
case "$LOCK_HELD" in true|false) ;; *) LOCK_HELD="null" ;; esac
MATERIAL="$(gpu_material_holder)"
GPU_LINE="$(nvidia-smi --query-gpu=memory.used,utilization.gpu --format=csv,noheader 2>/dev/null || echo '?')"
STATE="$(state_read)"

if [ "$JSON" = "1" ]; then
  jq -n \
    --argjson state "$STATE" \
    --argjson lock_held "$([ "$LOCK_HELD" = "true" ] && echo true || echo false)" \
    --argjson lock_holder "$LOCK_HOLDER" \
    --arg gpu "$GPU_LINE" \
    --argjson prod "$(svc_json prod "$PROD_PORT")" \
    --argjson test "$(svc_json test "$TEST_PORT")" \
    --arg gate_port "$GATE_PORT" \
    '{state:$state, canonical_lock:{path:"'"$GPU_LOCK"'", held:$lock_held, holder:$lock_holder},
      gpu_used_util:$gpu, services:{prod:$prod, test:$test},
      gate_port_reserved:($gate_port|tonumber)}'
  exit 0
fi

echo "=================================================================="
echo " RTX 3090 exclusive-owner status   $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "=================================================================="
echo " GPU:            $GPU_UUID"
echo " GPU used/util:  $GPU_LINE"
echo " Canonical lock: $GPU_LOCK"
echo "   held:         $LOCK_HELD"
echo "   holder:       $LOCK_HOLDER"
if [ -n "$MATERIAL" ]; then
  echo " Material app:   $MATERIAL"
else
  echo " Material app:   none (>=2 GiB)"
fi
echo "------------------------------------------------------------------"
printf ' %-6s %-6s %-8s %-7s %-7s %s\n' ROLE PORT PID ALIVE HEALTH TREE
for role in prod test; do
  case "$role" in prod) port="$PROD_PORT" ;; test) port="$TEST_PORT" ;; esac
  pid="-"; [ -f "$PID_DIR/$role.pid" ] && pid="$(cat "$PID_DIR/$role.pid")"
  alive="no"; [ "$pid" != "-" ] && [ -d "/proc/$pid" ] && alive="yes"
  health="down"; [ "$alive" = "yes" ] && health="$(probe_health "$port")"
  tree="-"; [ -f "$PID_DIR/$role.tree" ] && tree="$(cat "$PID_DIR/$role.tree")"
  printf ' %-6s %-6s %-8s %-7s %-7s %s\n' "$role" "$port" "$pid" "$alive" "$health" "$tree"
done
echo "------------------------------------------------------------------"
echo " Gate harness port $GATE_PORT is RESERVED; these scripts never use it."
echo " Owner state file: $STATE_FILE"
echo "   $STATE"
echo "=================================================================="
