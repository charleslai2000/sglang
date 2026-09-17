#!/usr/bin/env bash
# start.sh — start ONE service (prod or test) under the exclusive GPU owner model.
#
# Usage: start.sh <prod|test> [tree]
#
# Environment:
#   START_DRY_RUN=1   run preflight + GPU/port/namespace checks, then stop
#                     BEFORE launching anything (no process, no lock held,
#                     no port bound).  The allocated namespace claim is left
#                     in place so the real start can resume it by run id.
#
# Sequence (fail closed at every step; nothing is started before all pass):
#   1. preflight the tree (identity + launcher gates)
#   2. refuse if any material GPU holder exists (>=2 GiB compute app)
#   3. refuse if the port is not free
#   4. allocate a UNIQUE L3 namespace via the tree's own policy tool
#   5. hand off to bin/supervise.sh, which holds the canonical GPU lock for the
#      whole server lifetime, launches the frozen launcher, verifies
#      /proc/<pid>/environ, waits for /health 200 and records cold-start time
#
# The canonical lock is acquired by the supervisor so it cannot be released
# early; start.sh waits for state/ready/<role>.ready and reports the outcome.

set -euo pipefail
# shellcheck source=/dev/null
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

ROLE="${1:?usage: start.sh <prod|test> [tree]}"
TREE_OVERRIDE="${2:-}"

case "$ROLE" in
  prod) PORT="$PROD_PORT"; TREE="${TREE_OVERRIDE:-$PROD_TREE_DEFAULT}"; IDENTITY="${PROD_IDENTITY_DEFAULT}" ;;
  test) PORT="$TEST_PORT"; TREE="${TREE_OVERRIDE:-$TEST_TREE_DEFAULT}"; IDENTITY="LOCAL-PROD-v1.1.2" ;;
  *) die "unknown role '$ROLE' (want prod|test)" 2 ;;
esac
if [ "$PORT" = "$GATE_PORT" ]; then die "refusing to use the gate-harness port $GATE_PORT" 2; fi

log "=== start role=$ROLE port=$PORT tree=$TREE ==="

# ---- 1. preflight -----------------------------------------------------------
"$SCAFFOLD_ROOT/bin/preflight.sh" "$TREE" || die "preflight failed; not starting" 1

# ---- 2. no material GPU holder ---------------------------------------------
HOLDER="$(gpu_material_holder)"
if [ -n "$HOLDER" ]; then
  die "GPU has a material compute holder; stop it first (this script never signals it):
$HOLDER" 1
fi
RESIDUAL="$(gpu_compute_apps)"
[ -n "$RESIDUAL" ] && log "note: residual CUDA context present (<2 GiB, not a blocker): $RESIDUAL"

# ---- 3. port free -----------------------------------------------------------
if ! port_is_free "$PORT" >/dev/null 2>&1; then
  die "port $PORT is already bound; refusing to start" 1
fi
log "port $PORT free"

# ---- 4. unique L3 namespace -------------------------------------------------
RUN_ID="$(new_run_id "$ROLE")"
NAMESPACE="$(allocate_namespace "$TREE" "$RUN_ID")" || die "L3 namespace allocation failed" 1
log "L3 namespace (unique, never cleared): $NAMESPACE"
case "$NAMESPACE" in
  "$RESERVED_L3_STORE"*) die "refusing to use the shared production store $RESERVED_L3_STORE" 1 ;;
esac

if [ "${START_DRY_RUN:-0}" = "1" ]; then
  log "DRY RUN: all start preconditions passed; NOT launching and NOT taking the lock"
  log "DRY RUN: would run: supervise.sh $ROLE $TREE $PORT $RUN_ID $NAMESPACE <logdir>"
  log "DRY RUN: namespace claim left in place at $NAMESPACE (resume with same run id)"
  exit 0
fi

# ---- 5. hand off to the supervisor -----------------------------------------
LOG_DIR="$LOG_ROOT/$RUN_ID"
mkdir -p "$LOG_DIR"
READY="$SCAFFOLD_ROOT/state/ready/$ROLE.ready"
rm -f "$READY"

START_TS="$(date +%s.%N)"
setsid bash "$SCAFFOLD_ROOT/bin/supervise.sh" \
  "$ROLE" "$TREE" "$PORT" "$RUN_ID" "$NAMESPACE" "$LOG_DIR" "$START_TS" \
  >>"$LOG_DIR/supervisor.log" 2>&1 < /dev/null &
SUP_PID=$!
log "supervisor pid=$SUP_PID (holds the canonical GPU lock for the server lifetime)"

# Wait for ready, bounded by the supervisor's own health timeout.
DEADLINE=$(( SECONDS + 2500 ))
while [ "$SECONDS" -lt "$DEADLINE" ]; do
  if [ -f "$READY" ]; then
    log "=== $ROLE UP ==="
    cat "$RUN_DIR/$ROLE.run"
    exit 0
  fi
  if ! [ -d "/proc/$SUP_PID" ]; then
    die "supervisor exited before the service became ready; see $LOG_DIR" 1
  fi
  sleep 3
done
die "timed out waiting for $ROLE to become ready; see $LOG_DIR" 1
