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

ROLE="${1:?usage: start.sh <prod|test|m2|m3|m4> [tree]}"
TREE_OVERRIDE="${2:-}"

case "$ROLE" in
  prod) PORT="$PROD_PORT"; TREE="${TREE_OVERRIDE:-$PROD_TREE_DEFAULT}"; IDENTITY="${PROD_IDENTITY_DEFAULT}" ;;
  test) PORT="$TEST_PORT"; TREE="${TREE_OVERRIDE:-$TEST_TREE_DEFAULT}"; IDENTITY="LOCAL-PROD-v1.1.2" ;;
  m2)
    PORT="$M2_PORT"; TREE="${TREE_OVERRIDE:-$M2_TREE_DEFAULT}"; IDENTITY="${M2_IDENTITY_DEFAULT}"
    # M2 is a no-L3 model.  The M2 launcher REQUIRES SGLANG_L3_MODE=disabled and
    # has no default, so this export makes the disabled choice explicit here; a
    # missing/foreign value fails closed in the launcher rather than skipping L3.
    export SGLANG_L3_MODE="${SGLANG_L3_MODE:-$M2_L3_MODE}"
    export SGLANG_MODEL_PATH="${SGLANG_MODEL_PATH:-$M2_MODEL_PATH}"
    ;;
  m3|m4)
    if [ "$ROLE" = "m3" ]; then
      PORT="$M3_PORT"; TREE="${TREE_OVERRIDE:-$M3_TREE_DEFAULT}"; IDENTITY="${M3_IDENTITY_DEFAULT}"
      export SGLANG_MODEL_PATH="${SGLANG_MODEL_PATH:-$M3_MODEL_PATH}"
      export SGLANG_MAX_TOTAL_TOKENS="${SGLANG_MAX_TOTAL_TOKENS:-$M3_MAX_TOTAL_TOKENS}"
    else
      PORT="$M4_PORT"; TREE="${TREE_OVERRIDE:-$M4_TREE_DEFAULT}"; IDENTITY="${M4_IDENTITY_DEFAULT}"
      export SGLANG_MODEL_PATH="${SGLANG_MODEL_PATH:-$M4_MODEL_PATH}"
      export SGLANG_MAX_TOTAL_TOKENS="${SGLANG_MAX_TOTAL_TOKENS:-$M4_MAX_TOTAL_TOKENS}"
    fi
    # M3/M4 = GGUF 且无 L3 后端：与 m2 一样显式关闭，launcher 无默认值即 fail-closed。
    export SGLANG_L3_MODE="${SGLANG_L3_MODE:-disabled}"
    ;;
  *) die "unknown role '$ROLE' (want prod|test|m2|m3|m4)" 2 ;;
esac
if [ "$PORT" = "$GATE_PORT" ]; then die "refusing to use the gate-harness port $GATE_PORT" 2; fi

log "=== start role=$ROLE port=$PORT tree=$TREE ==="

# ---- 1. preflight -----------------------------------------------------------
if [ "$ROLE" = "m3" ] || [ "$ROLE" = "m4" ]; then
  "$SCAFFOLD_ROOT/bin/preflight-m3m4.sh" "$TREE" "$M3M4_SRC_DEFAULT" || die "m3m4 preflight failed; not starting" 1
else
  "$SCAFFOLD_ROOT/bin/preflight.sh" "$TREE" || die "preflight failed; not starting" 1
fi

# ---- 1b. dry run: stop BEFORE any exclusive/binding side effect -------------
# A dry run validates the preflight above and then stops: it does NOT take the
# canonical lock, does NOT probe/bind the port, does NOT allocate an L3
# namespace and does NOT launch a process.  It therefore exits BEFORE the
# material-holder gate, which legitimately fails closed while another role
# (e.g. M2) serves :30000.  The non-dry-run path below is unchanged.
if [ "${START_DRY_RUN:-0}" = "1" ]; then
  log "DRY RUN: preflight passed; NOT launching, NOT taking the lock, NOT binding the port, no namespace allocated"
  log "DRY RUN: would run: supervise.sh $ROLE $TREE $PORT <fresh-run-id> <namespace> <logdir>"
  exit 0
fi

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
# M2 is a no-L3 model: no namespace is allocated and /data/l3 is never touched.
# prod/test keep the original allocation path byte-for-byte (below).
if [ "$ROLE" = "m2" ] || [ "$ROLE" = "m3" ] || [ "$ROLE" = "m4" ]; then
  NAMESPACE=""
  log "L3 DISABLED for $ROLE (SGLANG_L3_MODE=$SGLANG_L3_MODE): no namespace allocated; /data/l3 untouched"
else
NAMESPACE="$(allocate_namespace "$TREE" "$RUN_ID")" || die "L3 namespace allocation failed" 1
log "L3 namespace (unique, never cleared): $NAMESPACE"
case "$NAMESPACE" in
  "$RESERVED_L3_STORE"*) die "refusing to use the shared production store $RESERVED_L3_STORE" 1 ;;
esac
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
