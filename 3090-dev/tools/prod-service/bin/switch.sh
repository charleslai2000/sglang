#!/usr/bin/env bash
# switch.sh — explicit GPU handoff between production and test.
#
# Usage: switch.sh <prod|test|m2|m3|m4>
#
# THE CENTRAL CONSTRAINT: this host has exactly ONE RTX 3090 (24576 MiB).
# Production at 64K fp8 needs ~18.7 GiB; test needs a comparable amount.  Two
# concurrent servers would need ~37 GiB > 24576 MiB, so they CANNOT both serve.
# This script therefore enforces a single exclusive GPU owner with an explicit
# stop -> release -> start handoff.  It never runs two servers at once.
#
# Steps
#   1. read current owner from the state file
#   2. if the target is already the owner and healthy -> no-op
#   3. stop the current owner (identity-checked) and WAIT for the lock to free
#   4. verify the GPU is materially free
#   5. start the target (which acquires the lock and allocates its own namespace)
#
# Cost: the handoff pays one full cold start for the target service.  See the
# README for the measured cold-start time.

set -euo pipefail
# shellcheck source=/dev/null
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

TARGET="${1:?usage: switch.sh <prod|test|m2|m3|m4>}"
case "$TARGET" in prod|test|m2|m3|m4) ;; *) die "unknown target '$TARGET' (want prod|test|m2|m3|m4)" 2 ;; esac

CURRENT="$(state_read | jq -r '.role // "free"')"
log "current GPU owner: $CURRENT -> requested: $TARGET"

if [ "$CURRENT" = "$TARGET" ]; then
  if [ -f "$PID_DIR/$TARGET.pid" ] && [ -d "/proc/$(cat "$PID_DIR/$TARGET.pid" 2>/dev/null)" ]; then
    log "$TARGET already owns the GPU; no switch needed"
    "$SCAFFOLD_ROOT/bin/status.sh"
    exit 0
  fi
  log "$TARGET is recorded owner but no live process; starting it"
fi

# ---- 1. stop the incumbent --------------------------------------------------
if [ "$CURRENT" != "free" ] && [ "$CURRENT" != "null" ]; then
  log "stopping current owner '$CURRENT' to release the GPU"
  "$SCAFFOLD_ROOT/bin/stop.sh" "$CURRENT" || warn "stop of '$CURRENT' reported a problem; continuing to verify"
else
  # No state owner, but something may still hold the lock/GPU.
  if [ "$(lock_is_held)" = "true" ]; then
    warn "state says free but the canonical lock is held:"
    warn "  holder=$(lock_holder_json)"
    die "an unknown GPU owner holds the canonical lock; refusing to start. Report BLOCKED-on-resource." 1
  fi
fi

# ---- 2. wait for the lock to free ------------------------------------------
log "waiting for the canonical lock to be released (bounded ${GPU_LOCK_TIMEOUT_S}s)"
DEADLINE=$(( SECONDS + GPU_LOCK_TIMEOUT_S ))
while [ "$(lock_is_held)" = "true" ] && [ "$SECONDS" -lt "$DEADLINE" ]; do
  sleep "$GPU_LOCK_POLL_S"
done
if [ "$(lock_is_held)" = "true" ]; then
  die "canonical lock still held after ${GPU_LOCK_TIMEOUT_S}s: $(lock_holder_json). Not signalling the incumbent." 1
fi
log "canonical lock free"

# ---- 3. GPU materially free ------------------------------------------------
MATERIAL="$(gpu_material_holder)"
if [ -n "$MATERIAL" ]; then
  die "GPU still has a material compute holder after handoff:
$MATERIAL" 1
fi
log "GPU materially free ($(nvidia-smi --query-gpu=memory.used,utilization.gpu --format=csv,noheader))"

# ---- 4. start the target ---------------------------------------------------
log "starting '$TARGET' (this pays one cold start)"
"$SCAFFOLD_ROOT/bin/start.sh" "$TARGET"
log "=== switch complete: GPU owner is now '$TARGET' ==="
"$SCAFFOLD_ROOT/bin/status.sh"
