#!/usr/bin/env bash
# common.sh — shared helpers for the prod/test service scaffold.
# Sourced, never executed.  No helper here starts a server by itself.
#
# Design rules encoded here:
#   * single exclusive GPU owner: canonical flock /tmp/opencode/gpu-3090.lock
#   * never signal an incumbent process we do not own (identity-checked first)
#   * fail closed: any preflight failure exits non-zero and starts nothing
#   * one task/run -> one unique L3 namespace; shared stores are never touched

set -euo pipefail

SCAFFOLD_ROOT="${SCAFFOLD_ROOT:-/tmp/opencode/prod-service-20260917}"
# shellcheck source=/dev/null
source "$SCAFFOLD_ROOT/conf/service.env"

mkdir -p "$PID_DIR" "$RUN_DIR" "$SCAFFOLD_ROOT/state" 2>/dev/null || true

log()  { printf '[%s] %s\n' "$(date -u +%H:%M:%S)" "$*"; }
warn() { printf '[%s] WARN: %s\n' "$(date -u +%H:%M:%S)" "$*" >&2; }
die()  { printf '[%s] FATAL: %s\n' "$(date -u +%H:%M:%S)" "$*" >&2; exit "${2:-1}"; }

# ------------------------------------------------------------------ state
# The state file is the owner-visible "who holds the GPU" record.  All writes
# take a dedicated state lock so a switch can never interleave two writers.
state_read() {
  [ -f "$STATE_FILE" ] || { echo '{}'; return 0; }
  cat "$STATE_FILE" 2>/dev/null || echo '{}'
}

state_write() {
  # args: role pid port run_id namespace tree identity note
  local role="$1" pid="$2" port="$3" run_id="$4" namespace="$5" tree="$6" identity="$7" note="${8:-}"
  local gen
  gen="$(lock_generation)"
  local tmp="$STATE_FILE.tmp.$$"
  cat >"$tmp" <<EOF
{
  "gpu": "$GPU_UUID",
  "role": "$role",
  "state": "$([ "$role" = "free" ] && echo free || echo held)",
  "pid": $([ "$pid" = "-" ] && echo null || echo "$pid"),
  "port": $([ "$port" = "-" ] && echo null || echo "$port"),
  "run_id": "$run_id",
  "l3_namespace": "$namespace",
  "tree": "$tree",
  "identity": "$identity",
  "lock_generation": $([ "$gen" = "-" ] && echo null || echo "$gen"),
  "updated_at_utc": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "note": "$note"
}
EOF
  mv -f "$tmp" "$STATE_FILE"
}

state_write_free() {
  state_write "free" "-" "-" "" "" "" "" "${1:-released}"
}

# ------------------------------------------------------------------ GPU lock
# Bounded, non-blocking acquisition.  We NEVER signal the incumbent: if the
# lock cannot be taken within the bounded window the caller must fail closed.
# Usage: gpu_lock_acquire <fd-number> <owner-label>
# Returns 0 on success; the caller then owns the lock on that fd until exit.
gpu_lock_acquire() {
  local fd="$1" owner="$2"
  # Guard: the canonical path is fixed and must not be redirected.  A test or
  # caller that wants an isolated lock must pass GPU_LOCK_FOR_TESTS explicitly,
  # which is only honoured when it is NOT the canonical path's directory tree.
  local lock_path="$GPU_LOCK"
  if [ -n "${GPU_LOCK_FOR_TESTS:-}" ] && [ "${GPU_LOCK_FOR_TESTS}" != "$GPU_LOCK" ]; then
    case "$GPU_LOCK_FOR_TESTS" in
      /tmp/opencode/prod-service-20260917/*) lock_path="$GPU_LOCK_FOR_TESTS" ;;
      *) die "refusing GPU_LOCK_FOR_TESTS outside the scaffold scratch root: $GPU_LOCK_FOR_TESTS" 2 ;;
    esac
    warn "using TEST lock path (not canonical): $lock_path"
  fi
  # Open read-write WITHOUT truncation: truncating on open would wipe the
  # incumbent's visible holder record before we own the lock.  The inode is
  # preserved (never replaced by mv), which is what flock mutual exclusion
  # depends on.
  eval "exec $fd<>\"\$lock_path\""
  local deadline=$(( SECONDS + GPU_LOCK_TIMEOUT_S ))
  local attempt=0
  while :; do
    attempt=$(( attempt + 1 ))
    if eval "flock -n $fd"; then
      local prev gen
      prev="$(cat "$lock_path" 2>/dev/null | tail -1 || true)"
      gen="$(printf '%s' "$prev" | jq -r '.generation // 0' 2>/dev/null || echo 0)"
      [ -n "$gen" ] || gen=0
      # We now own the lock, so we are the only writer.  Truncate the same
      # inode, then write the new record through the locked fd.
      : >"$lock_path"
      printf '{"owner": "%s", "pid": %d, "generation": %d, "acquired": "%s"}\n' \
        "$owner" "$$" "$(( gen + 1 ))" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
        | eval "cat >&$fd"
      log "canonical GPU lock ACQUIRED generation=$(( gen + 1 )) owner=$owner pid=$$"
      return 0
    fi
    if [ "$SECONDS" -ge "$deadline" ]; then
      local holder; holder="$(cat "$lock_path" 2>/dev/null | tail -1 || true)"
      warn "canonical GPU lock still busy after ${GPU_LOCK_TIMEOUT_S}s; incumbent holder=$holder"
      warn "not signalling the incumbent; failing closed"
      return 1
    fi
    local holder; holder="$(cat "$lock_path" 2>/dev/null | tail -1 || true)"
    log "lock busy (attempt $attempt, ${SECONDS}s elapsed) holder=$holder"
    sleep "$GPU_LOCK_POLL_S"
  done
}

# Read the lock generation without taking the lock.
effective_lock_path() {
  if [ -n "${GPU_LOCK_FOR_TESTS:-}" ] && [ "${GPU_LOCK_FOR_TESTS}" != "$GPU_LOCK" ]; then
    case "$GPU_LOCK_FOR_TESTS" in
      /tmp/opencode/prod-service-20260917/*) printf '%s' "$GPU_LOCK_FOR_TESTS"; return 0 ;;
    esac
  fi
  printf '%s' "$GPU_LOCK"
}

lock_generation() {
  local holder; holder="$(cat "$(effective_lock_path)" 2>/dev/null | tail -1 || true)"
  printf '%s' "$holder" | jq -r '.generation // "-"' 2>/dev/null || echo "-"
}

lock_holder_json() {
  cat "$(effective_lock_path)" 2>/dev/null | tail -1 || echo '{}'
}

# Fresh-process probe: is the lock currently held by somebody else?
lock_is_held() {
  local probe
  probe="$(CUDA_VISIBLE_DEVICES=999 python3 - "$(effective_lock_path)" <<'PY' 2>/dev/null || echo '{"locked":null}'
import fcntl, json, os, sys
fd = os.open(sys.argv[1], os.O_RDWR | os.O_CREAT | os.O_CLOEXEC, 0o644)
locked = False
try:
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
except OSError:
    locked = True
if not locked:
    try: fcntl.flock(fd, fcntl.LOCK_UN)
    except OSError: pass
os.close(fd)
print(json.dumps({"locked": locked}))
PY
)"
  printf '%s' "$probe" | jq -r '.locked // "null"'
}

# ------------------------------------------------------------------ process identity
# Verify a PID really is the process we think it is before signalling it.
# Returns 0 only if cmdline contains every expected token.
pid_matches() {
  local pid="$1"; shift
  [ -d "/proc/$pid" ] || return 1
  local cmdline
  cmdline="$(tr '\0' ' ' <"/proc/$pid/cmdline" 2>/dev/null || true)"
  [ -n "$cmdline" ] || return 1
  local tok
  for tok in "$@"; do
    case "$cmdline" in
      *"$tok"*) ;;
      *) return 1 ;;
    esac
  done
  return 0
}

pid_holds_lock() {
  local pid="$1"
  [ -d "/proc/$pid" ] || return 1
  ls -l "/proc/$pid/fd" 2>/dev/null | grep -q "$(basename "$GPU_LOCK")"
}

# Stop a server we own.  Identity-checked; SIGTERM then bounded SIGKILL.
# Usage: stop_owned_server <pid> <tree> <port>
stop_owned_server() {
  local pid="$1" tree="$2" port="$3"
  if [ -z "$pid" ] || [ "$pid" = "null" ]; then
    log "no server pid recorded; nothing to stop"
    return 0
  fi
  if [ ! -d "/proc/$pid" ]; then
    log "pid $pid already gone"
    return 0
  fi
  if ! pid_matches "$pid" "launch_server" "--port" "$port"; then
    warn "pid $pid does not match expected launch_server --port $port; NOT signalling it"
    warn "cmdline: $(tr '\0' ' ' <"/proc/$pid/cmdline" 2>/dev/null | cut -c1-200)"
    return 3
  fi
  case "$(tr '\0' ' ' <"/proc/$pid/cmdline" 2>/dev/null || true)" in
    *"$tree"*) ;;
    *) warn "pid $pid does not reference tree $tree; NOT signalling it"; return 3 ;;
  esac

  log "stopping owned server pid=$pid (SIGTERM, graceful)"
  kill -TERM "$pid" 2>/dev/null || true
  local deadline=$(( SECONDS + 240 ))
  while [ -d "/proc/$pid" ] && [ "$SECONDS" -lt "$deadline" ]; do sleep 2; done
  if [ -d "/proc/$pid" ]; then
    warn "pid $pid did not exit within 240s; SIGKILL"
    kill -KILL "$pid" 2>/dev/null || true
    deadline=$(( SECONDS + 60 ))
    while [ -d "/proc/$pid" ] && [ "$SECONDS" -lt "$deadline" ]; do sleep 2; done
  fi
  if [ -d "/proc/$pid" ]; then
    warn "pid $pid still present after SIGKILL"
    return 4
  fi
  log "server pid=$pid stopped"
  return 0
}

# ------------------------------------------------------------------ GPU / ports
port_is_free() {
  local port="$1"
  CUDA_VISIBLE_DEVICES=999 python3 - "$port" <<'PY'
import socket, sys
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
try:
    s.bind(("127.0.0.1", int(sys.argv[1])))
except OSError:
    print("busy"); raise SystemExit(1)
finally:
    s.close()
print("free")
PY
}

wait_port_free() {
  local port="$1" timeout_s="${2:-300}"
  local deadline=$(( SECONDS + timeout_s ))
  while [ "$SECONDS" -lt "$deadline" ]; do
    if port_is_free "$port" >/dev/null 2>&1; then return 0; fi
    sleep 3
  done
  port_is_free "$port" >/dev/null 2>&1
}

# GPU is "free enough" when no compute app holds >= 2 GiB.  A residual CUDA
# context below 1 GiB at 0% util is explicitly NOT a blocker (owner policy).
gpu_compute_apps() {
  nvidia-smi --query-compute-apps=pid,used_memory,process_name \
    --format=csv,noheader,nounits 2>/dev/null || true
}

gpu_material_holder() {
  local line pid mem name
  while IFS= read -r line; do
    [ -n "$line" ] || continue
    pid="$(printf '%s' "$line" | cut -d, -f1 | tr -d ' ')"
    mem="$(printf '%s' "$line" | cut -d, -f2 | tr -d ' ')"
    name="$(printf '%s' "$line" | cut -d, -f3- | sed 's/^ //')"
    [ -n "$mem" ] || continue
    if [ "$mem" -ge 2048 ] 2>/dev/null; then
      printf '%s %s %s\n' "$pid" "$mem" "$name"
    fi
  done <<<"$(gpu_compute_apps)"
}

# ------------------------------------------------------------------ run ids / namespaces
new_run_id() {
  # <role>-<utc>-<pid>  — matches [A-Za-z0-9][A-Za-z0-9._-]* and is unique.
  printf '%s-%s-%s' "$1" "$(date -u +%Y%m%dT%H%M%SZ)" "$$"
}

# Allocate a unique L3 namespace using the frozen tree's own policy tool.
# Refuses reserved/shared stores.  Prints the namespace path on success.
allocate_namespace() {
  local tree="$1" run_id="$2"
  local root="$L3_ROOT"
  if [ -n "${L3_ROOT_FOR_TESTS:-}" ] && [ "${L3_ROOT_FOR_TESTS}" != "$L3_ROOT" ]; then
    case "$L3_ROOT_FOR_TESTS" in
      /tmp/opencode/prod-service-20260917/*) root="$L3_ROOT_FOR_TESTS" ;;
      *) die "refusing L3_ROOT_FOR_TESTS outside the scaffold scratch root" 2 ;;
    esac
    warn "using TEST L3 root (not production): $root"
  fi
  local out rc=0
  out="$(CUDA_VISIBLE_DEVICES=999 PYTHONDONTWRITEBYTECODE=1 \
        "$tree/env/bin/python" "$tree/tools/l3_namespace.py" \
        --allocate --task-id "$run_id" --root "$root" --json 2>&1)" || rc=$?
  if [ "$rc" -ne 0 ]; then
    warn "L3 namespace allocation failed (rc=$rc): $out"
    return "$rc"
  fi
  printf '%s' "$out" | jq -r '.namespace'
}

validate_namespace() {
  local tree="$1" run_id="$2" ns="$3"
  local root="$L3_ROOT"
  if [ -n "${L3_ROOT_FOR_TESTS:-}" ] && [ "${L3_ROOT_FOR_TESTS}" != "$L3_ROOT" ]; then
    case "$L3_ROOT_FOR_TESTS" in
      /tmp/opencode/prod-service-20260917/*) root="$L3_ROOT_FOR_TESTS" ;;
    esac
  fi
  CUDA_VISIBLE_DEVICES=999 PYTHONDONTWRITEBYTECODE=1 \
    "$tree/env/bin/python" "$tree/tools/l3_namespace.py" \
    --validate --task-id "$run_id" --root "$root" --path "$ns" --json >/dev/null 2>&1
}

# ------------------------------------------------------------------ tree identity
tree_launcher()      { printf '%s/launcher/launch.sh' "$1"; }
tree_python()        { printf '%s/env/bin/python' "$1"; }
tree_identity_json() { printf '%s/manifest/identity.json' "$1"; }
tree_identity_pins() { printf '%s/manifest/identity-pins.json' "$1"; }

# Digest recorded for the tree manifest, tolerating both identity.json layouts.
tree_recorded_digest() {
  local tree="$1"
  local j="$tree/manifest/identity.json"
  local pins="$tree/manifest/identity-pins.json"
  if [ -f "$pins" ]; then
    jq -r '.tree_manifest_sha256 // empty' "$pins" 2>/dev/null && return 0
  fi
  [ -f "$j" ] || return 1
  jq -r '(.tree.tree_manifest_digest_sha256 // .tree_manifest_sha256 // empty)' "$j" 2>/dev/null
}

tree_recorded_launcher_sha() {
  local tree="$1"
  local j="$tree/manifest/identity.json"
  local pins="$tree/manifest/identity-pins.json"
  if [ -f "$pins" ]; then
    jq -r '.launcher_sha256 // empty' "$pins" 2>/dev/null && return 0
  fi
  [ -f "$j" ] || return 1
  jq -r '(.launcher.sha256 // .launcher_sha256 // empty)' "$j" 2>/dev/null
}

# Does this tree's launcher enforce the fail-closed source-identity gate?
tree_has_identity_gate() {
  grep -q 'preflight_identity.py' "$(tree_launcher "$1")" 2>/dev/null
}

tree_has_namespace_gate() {
  grep -q 'l3_namespace.py' "$(tree_launcher "$1")" 2>/dev/null
}
