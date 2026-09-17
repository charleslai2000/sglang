#!/usr/bin/env bash
# provider-common.sh — shared helpers for the RTX-3090 DEV provider.
#
# Sourced by the provider-start / provider-stop / provider-status entry
# points.  Never executed on its own.
#
# Design rules encoded here:
#   * the provider runs a pinned git commit exported into /opt, never the
#     live worktree
#   * the canonical GPU lock is held ONLY for the start/verify window and is
#     explicitly NOT inherited by the long-lived server or its log filter
#   * never signal a process we have not identity-checked
#   * fail closed: any gate failure starts nothing
#   * the API key never reaches a log, an argv, or a printed report

set -euo pipefail

_HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_TREE="$(cd "$_HERE/.." && pwd)"

# shellcheck source=/dev/null
source "$DEPLOY_TREE/conf/provider.env"

SOURCE_SHORT="$(printf '%s' "$SOURCE_COMMIT" | cut -c1-10)"
DEPLOY_DIR="${DEPLOY_DIR_OVERRIDE:-$DEPLOY_ROOT_DEFAULT}"
API_KEY_FILE="${API_KEY_FILE_OVERRIDE:-$API_KEY_FILE_DEFAULT}"
RUN_DIR="${RUN_DIR_OVERRIDE:-$RUN_DIR_DEFAULT}"

PID_FILE="$RUN_DIR/provider.pid"
SUP_PID_FILE="$RUN_DIR/provider.supervisor.pid"
CONSOLE_LOG="$RUN_DIR/server.console.log"
SUPERVISOR_LOG="$RUN_DIR/supervisor.log"
AUTH_CONFIG="$RUN_DIR/auth-config.yaml"
STATE_FILE="$RUN_DIR/provider.state"
VERIFY_DIR="$RUN_DIR/verify"

TREE_ID="$_HERE/provider-tree-id.py"
SYSPROBE="$_HERE/provider-sysprobe.py"
SMOKE="$_HERE/provider-smoke.py"
SUPERVISOR="$_HERE/provider-supervise.py"

log()  { printf '[%s] %s\n' "$(date -u +%H:%M:%S)" "$*"; }
warn() { printf '[%s] WARN: %s\n' "$(date -u +%H:%M:%S)" "$*" >&2; }
die()  { printf '[%s] FATAL: %s\n' "$(date -u +%H:%M:%S)" "$*" >&2; exit "${2:-1}"; }

# ------------------------------------------------------------------ runtime dir
# The run dir lives beside the other root-owned deploy trees, but its logs,
# pid and metrics are produced by this (unprivileged) user, so it is created
# once with sudo and then owned by the invoking user with mode 700.
provider_prepare_run_dir() {
  if [ ! -d "$RUN_DIR" ]; then
    require_sudo
    sudo -n mkdir -p "$RUN_DIR"
    sudo -n chown "$(id -u):$(id -g)" "$RUN_DIR"
    sudo -n chmod 700 "$RUN_DIR"
  fi
  if [ ! -w "$RUN_DIR" ]; then
    require_sudo
    sudo -n chown -R "$(id -u):$(id -g)" "$RUN_DIR"
    sudo -n chmod 700 "$RUN_DIR"
  fi
  mkdir -p "$VERIFY_DIR" "$RUN_DIR/metrics"
}

# ------------------------------------------------------------------ sudo
require_sudo() {
  sudo -n true 2>/dev/null \
    || die "passwordless sudo is required (the deploy target /opt is root-owned)"
}

# ------------------------------------------------------------------ API key
# The key file is root:root 0600.  Its value is read on demand, never echoed,
# never written to a file we create, and never passed as a command argument.
provider_ensure_api_key() {
  require_sudo
  local dir; dir="$(dirname "$API_KEY_FILE")"
  sudo -n test -d "$dir" || sudo -n mkdir -p "$dir"

  if sudo -n test -s "$API_KEY_FILE"; then
    local mode; mode="$(sudo -n stat -c '%a' "$API_KEY_FILE")"
    [ "$mode" = "600" ] \
      || die "API key file $API_KEY_FILE has mode $mode (want 600); refusing"
    log "API key file present and 0600: $API_KEY_FILE"
    return 0
  fi

  log "generating API key into $API_KEY_FILE (0600 root-only)"
  # The key reaches the file through a pipe, so it is never an argv element.
  python3 -c 'import secrets; print(secrets.token_urlsafe(48))' \
    | sudo -n install -m 600 -o root -g root /dev/stdin "$API_KEY_FILE" \
    || die "could not write the API key file"
  sudo -n test -s "$API_KEY_FILE" || die "API key file is empty after generation"
  [ "$(sudo -n stat -c '%a' "$API_KEY_FILE")" = "600" ] \
    || die "API key file mode is not 600 after generation"
  log "API key file created (value intentionally never displayed)"
}

provider_read_api_key() {
  sudo -n test -s "$API_KEY_FILE" || return 1
  sudo -n cat "$API_KEY_FILE"
}

# ------------------------------------------------------------------ identity
provider_export_tree() {
  require_sudo
  sudo -n mkdir -p "$DEPLOY_DIR"

  if sudo -n test -f "$DEPLOY_DIR/MANIFEST-provider-tree.tsv"; then
    if provider_verify_tree; then
      log "deploy tree already exported and verified: $DEPLOY_DIR"
      return 0
    fi
    warn "existing deploy tree failed its identity check; re-exporting from scratch"
    sudo -n rm -rf "$DEPLOY_DIR"
    sudo -n mkdir -p "$DEPLOY_DIR"
  fi

  log "exporting pinned commit $SOURCE_SHORT into $DEPLOY_DIR"
  git -C "$REPO" cat-file -e "$SOURCE_COMMIT^{commit}" 2>/dev/null \
    || die "commit $SOURCE_COMMIT is not present in $REPO"
  # Archive the pinned commit explicitly -- not the worktree.
  git -C "$REPO" archive --format=tar "$SOURCE_COMMIT" \
    | sudo -n tar -x -C "$DEPLOY_DIR" \
    || die "git archive/extract of $SOURCE_COMMIT failed"

  # `git archive` cannot carry the gitignored build outputs that the proven
  # frozen tree also ships.  Stage them from the live worktree; they are
  # digest-pinned below so a later change in /opt is still detected.
  local rel
  for rel in "${PROVIDER_ARTIFACTS[@]}"; do
    [ -f "$REPO/$rel" ] || die "expected build artifact missing from source: $REPO/$rel"
    sudo -n install -m 644 -o root -g root "$REPO/$rel" "$DEPLOY_DIR/$rel" \
      || die "could not stage artifact $rel"
  done

  sudo -n python3 "$TREE_ID" write "$DEPLOY_DIR" "$SOURCE_COMMIT" "$REPO" \
    "${PROVIDER_ARTIFACTS[@]}" \
    || die "deploy-tree identity write FAILED; the export is not clean"
  # The deployed source is immutable: nothing should rewrite it in place.
  sudo -n chmod -R a-w "$DEPLOY_DIR/python" 2>/dev/null || true
  provider_verify_tree
}

provider_verify_tree() {
  sudo -n python3 "$TREE_ID" check "$DEPLOY_DIR" "$SOURCE_COMMIT" "$REPO" \
    "${PROVIDER_ARTIFACTS[@]}"
}

# ------------------------------------------------------------------ GPU
gpu_material_holder() {
  local line pid mem uuid
  while IFS= read -r line; do
    [ -n "$line" ] || continue
    pid="$(printf '%s' "$line" | cut -d, -f1 | tr -d ' ')"
    mem="$(printf '%s' "$line" | cut -d, -f2 | tr -d ' ')"
    uuid="$(printf '%s' "$line" | cut -d, -f3- | sed 's/^ *//')"
    [ -n "$mem" ] || continue
    if [ "$mem" -ge "$GPU_MIN_MATERIAL_MIB" ] 2>/dev/null; then
      printf '%s %sMiB %s\n' "$pid" "$mem" "$uuid"
    fi
  done <<<"$(nvidia-smi --query-compute-apps=pid,used_memory,gpu_uuid \
              --format=csv,noheader,nounits 2>/dev/null || true)"
}

gpu_pid_uuid() {
  local want="$1" line pid uuid
  while IFS= read -r line; do
    [ -n "$line" ] || continue
    pid="$(printf '%s' "$line" | cut -d, -f1 | tr -d ' ')"
    uuid="$(printf '%s' "$line" | cut -d, -f3- | sed 's/^ *//')"
    if [ "$pid" = "$want" ]; then printf '%s' "$uuid"; return 0; fi
  done <<<"$(nvidia-smi --query-compute-apps=pid,used_memory,gpu_uuid \
              --format=csv,noheader,nounits 2>/dev/null || true)"
  return 1
}

provider_gpu_ordinal() {
  local out rc=0
  # Run through the venv interpreter: it is the one that will run the server,
  # and it is the one with torch and pynvml available.  CUDA must NOT be
  # masked here -- the probe has to enumerate the real device list to find
  # the ordinal for this UUID.
  out="$(env -u CUDA_VISIBLE_DEVICES "$VENV_PY" "$SYSPROBE" gpu-ordinal "$GPU_UUID" 2>&1)" || rc=$?
  [ "$rc" -eq 0 ] || die "cannot resolve the CUDA ordinal for $GPU_UUID: $out"
  # The probe may interleave a diagnostic note; the ordinal is the last line.
  local ordinal; ordinal="$(printf '%s\n' "$out" | tail -1)"
  case "$ordinal" in
    ''|*[!0-9]*) die "CUDA ordinal probe returned a non-numeric result: $out" ;;
  esac
  printf '%s' "$ordinal"
}

# ------------------------------------------------------------------ port
provider_port_is_free() {
  python3 "$SYSPROBE" port-free "$BIND_HOST" "$BIND_PORT" >/dev/null 2>&1
}

provider_port_owner() {
  ss -ltnp 2>/dev/null | awk -v p=":$BIND_PORT" '$4 ~ p {print; found=1} END{exit !found}'
}

# ------------------------------------------------------------------ canonical lock
# Acquired for the start/verify window only.  The running server and its log
# filter must never hold it, otherwise a main-line experiment could not take
# the GPU while the provider idles.
gpu_lock_acquire() {
  eval "exec 9<>\"\$GPU_LOCK\""
  local deadline=$(( SECONDS + LOCK_WAIT_S )) holder
  while :; do
    if eval "flock -n 9"; then
      holder="$(tail -1 "$GPU_LOCK" 2>/dev/null || true)"
      log "canonical GPU lock acquired (previous record: ${holder:-none})"
      return 0
    fi
    if [ "$SECONDS" -ge "$deadline" ]; then
      holder="$(tail -1 "$GPU_LOCK" 2>/dev/null || true)"
      warn "canonical GPU lock busy after ${LOCK_WAIT_S}s; holder=${holder:-unknown}"
      warn "the main line has priority; NOT signalling the incumbent; failing closed"
      return 1
    fi
    sleep 2
  done
}

gpu_lock_release() { eval "exec 9>&-" 2>/dev/null || true; }

gpu_lock_state() {
  CUDA_VISIBLE_DEVICES=999 python3 "$SYSPROBE" lock-state "$GPU_LOCK"
}

# ------------------------------------------------------------------ process
pid_alive() {
  local pid="$1"
  [ -n "$pid" ] && [ -d "/proc/$pid" ] || return 1
  local st; st="$(awk '{print $3}' "/proc/$pid/stat" 2>/dev/null || echo Z)"
  [ "$st" != "Z" ]
}

pid_cmdline() { tr '\0' ' ' <"/proc/$pid/cmdline" 2>/dev/null || true; }

pid_environ() { tr '\0' '\n' <"/proc/$pid/environ" 2>/dev/null || true; }

# A pid we are willing to signal must be OUR launch_server on OUR port,
# importing from OUR deploy tree.  The deploy path is not in the command line
# (it travels via PYTHONPATH), so the environment is checked too.
pid_is_our_server() {
  local pid="$1" cl env
  pid_alive "$pid" || return 1
  cl="$(pid_cmdline "$pid")"
  [ -n "$cl" ] || return 1
  case "$cl" in *sglang.launch_server*) ;; *) return 1 ;; esac
  case "$cl" in *"--port $BIND_PORT "*) ;; *) return 1 ;; esac
  env="$(pid_environ "$pid")"
  case "$env" in *"PYTHONPATH=$DEPLOY_DIR/python"*) ;; *) return 1 ;; esac
  return 0
}

# ------------------------------------------------------------------ HTTP
provider_health_code() {
  curl -s -o /dev/null -w '%{http_code}' --max-time 5 \
    "http://$BIND_HOST:$BIND_PORT/health" 2>/dev/null || echo 000
}

# ------------------------------------------------------------------ state
state_write() {
  local role="$1" pid="$2" health="$3" note="${4:-}"
  provider_prepare_run_dir
  local pidjson; [ "$pid" = "-" ] && pidjson="null" || pidjson="$pid"
  printf '{\n  "role": "%s",\n  "pid": %s,\n  "port": %s,\n  "host": "%s",\n  "served_model_name": "%s",\n  "source_commit": "%s",\n  "deploy_dir": "%s",\n  "health": "%s",\n  "l3": "off",\n  "updated_at_utc": "%s",\n  "note": "%s"\n}\n' \
    "$role" "$pidjson" "$BIND_PORT" "$BIND_HOST" "$SERVED_MODEL_NAME" \
    "$SOURCE_COMMIT" "$DEPLOY_DIR" "$health" \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$note" >"$STATE_FILE.tmp.$$"
  mv -f "$STATE_FILE.tmp.$$" "$STATE_FILE"
}

# ------------------------------------------------------------------ argv
# This provider must own its argv: the frozen production launcher hard-exports
# SGLANG_HICACHE_EXTENT_*, passes --hicache-storage-backend extent and runs
# three L3 namespace gates.  L3/Extent is OFF here, so that launcher is not
# reusable.  Everything else is the recorded-good serving profile.
provider_build_argv() {
  PROVIDER_ARGV=(
    -m sglang.launch_server
    --model-path "$MODEL_PATH"
    --host "$BIND_HOST" --port "$BIND_PORT"
    --served-model-name "$SERVED_MODEL_NAME"
    --tp-size "$TP_SIZE"
    --mem-fraction-static "$MEM_FRACTION_STATIC"
    --max-total-tokens "$MAX_TOTAL_TOKENS"
    --kv-cache-dtype "$KV_CACHE_DTYPE"
    --attention-backend "$ATTENTION_BACKEND"
    --linear-attn-prefill-backend "$LINEAR_ATTN_PREFILL_BACKEND"
    --linear-attn-decode-backend "$LINEAR_ATTN_DECODE_BACKEND"
    --mamba-radix-cache-strategy "$MAMBA_RADIX_CACHE_STRATEGY"
    --mamba-ssm-dtype "$MAMBA_SSM_DTYPE"
    # L1 radix cache stays on (default); Host/L2 HiCache on; L3/Extent OFF.
    --enable-hierarchical-cache
    --hicache-write-policy "$HICACHE_WRITE_POLICY"
    --hicache-size "$L2_GB"
    --enable-ready-horizon
    --reasoning-parser "$REASONING_PARSER"
    --tool-call-parser "$TOOL_CALL_PARSER"
    --enable-metrics
    --export-metrics-to-file
    --export-metrics-to-file-dir "$VERIFY_DIR/metrics"
    # The validated profile keeps the decode CUDA graph on and disables only
    # the prefill graph.
    --disable-prefill-cuda-graph
  )
}

# ------------------------------------------------------------------ launch
# Launch detached under the supervisor, which owns the server and writes its
# console log through the API-key redactor.
#
# Authentication reaches the server WITHOUT ever touching a command line.
# sglang exposes no environment variable and no --api-key-file for this value
# (only --api-key, which lands in /proc/<pid>/cmdline, mode 0444), but it does
# merge `--config <yaml>` into the resolved arguments.  Verified on this tree:
# the --config route yields a resolved_dict() identical to passing --api-key
# on argv.  The supervisor therefore writes a 0600 YAML containing only
# `api-key`, passes --config, and deletes the file after the server exits.
# The key is therefore absent from the launcher argv, the supervisor argv, the
# server argv, and every process environment.
#
# The caller must hold the canonical lock; neither the supervisor nor the
# server may inherit it (fd 9 is closed for both).
provider_start_server() {
  local ordinal="$1"
  provider_prepare_run_dir
  mkdir -p "$VERIFY_DIR/metrics"
  rm -f "$PID_FILE" "$SUP_PID_FILE"
  rm -f "$AUTH_CONFIG"

  # Rotate the console log.  The startup gates scan this file for evidence
  # (fp8 KV allocation, CUDA-graph capture), so an appended log from a
  # previous run would let a broken start "pass" on stale evidence.  Each run
  # gets a fresh file; prior logs are kept for forensics.
  if [ -s "$CONSOLE_LOG" ]; then
    local stamp; stamp="$(date -u +%Y%m%dT%H%M%SZ)"
    mv -f "$CONSOLE_LOG" "$RUN_DIR/server.console.$stamp.log"
    log "archived the previous console log as server.console.$stamp.log"
  fi
  : >"$CONSOLE_LOG"
  chmod 600 "$CONSOLE_LOG"
  rm -f "$SUPERVISOR_LOG"

  (
    cd /tmp   # avoid cwd shadowing `import sglang`
    umask 077
    export PYTHONPATH="$DEPLOY_DIR/python"
    export PYTHONDONTWRITEBYTECODE=1
    export CUDA_HOME=/usr/local/cuda-12.9
    export PATH="$CUDA_HOME/bin:$PATH"
    # NVML index and CUDA ordinal are inverted on this box.  Pin the ordinal
    # resolved from the UUID (CUDA_VISIBLE_DEVICES=GPU-<uuid> is not valid).
    export CUDA_VISIBLE_DEVICES="$ordinal"
    # L3/Extent is OFF: never let these leak in from the caller's shell.
    local v
    for v in $L3_FORBIDDEN_ENV; do unset "$v" || true; done

    # setsid + fully detached stdio: the supervisor outlives this launcher and
    # never holds its stdout, so provider-start output can be piped.
    setsid python3 "$SUPERVISOR" \
      --log "$CONSOLE_LOG" \
      --key-file "$API_KEY_FILE" \
      --pid-file "$PID_FILE" \
      --auth-config "$AUTH_CONFIG" \
      -- "$VENV_PY" -P -u "${PROVIDER_ARGV[@]}" \
      9>&- >>"$SUPERVISOR_LOG" 2>&1 </dev/null &
    echo "$!" >"$SUP_PID_FILE"
  )

  # Wait for the supervisor to record the server pid.
  local deadline=$(( SECONDS + 60 ))
  while [ ! -s "$PID_FILE" ] && [ "$SECONDS" -lt "$deadline" ]; do sleep 1; done
  [ -s "$PID_FILE" ] || die "the supervisor did not record a server pid; see $SUPERVISOR_LOG"
  log "launched pid=$(cat "$PID_FILE") on $BIND_HOST:$BIND_PORT (CUDA ordinal $ordinal)"
}

# ------------------------------------------------------------------ stop
# Graceful stop of the server we own, then WAIT until the GPU really shows the
# process gone.  This is the step that frees the device for the main line.
provider_stop_server() {
  local pid="" rc=0
  [ -f "$PID_FILE" ] && pid="$(cat "$PID_FILE" 2>/dev/null || true)"

  if [ -z "$pid" ] || ! [ -d "/proc/$pid" ]; then
    log "no live provider process recorded (pid=${pid:-none})"
  elif pid_is_our_server "$pid"; then
    log "stopping provider pid=$pid (SIGTERM, graceful)"
    kill -TERM "$pid" 2>/dev/null || true
    local deadline=$(( SECONDS + STOP_TIMEOUT_S ))
    while pid_alive "$pid" && [ "$SECONDS" -lt "$deadline" ]; do sleep 2; done
    if pid_alive "$pid"; then
      warn "pid $pid survived ${STOP_TIMEOUT_S}s; SIGKILL"
      kill -KILL "$pid" 2>/dev/null || true
      deadline=$(( SECONDS + 60 ))
      while pid_alive "$pid" && [ "$SECONDS" -lt "$deadline" ]; do sleep 2; done
    fi
    pid_alive "$pid" && { warn "pid $pid still present after SIGKILL"; rc=1; }
  else
    warn "recorded pid $pid is not our launch_server on port $BIND_PORT; NOT signalling it"
    warn "cmdline: $(pid_cmdline "$pid" | cut -c1-200)"
    rc=3
  fi

  local gpu_deadline=$(( SECONDS + 120 )) remaining
  while [ "$SECONDS" -lt "$gpu_deadline" ]; do
    [ -z "$(gpu_material_holder)" ] && break
    sleep 2
  done
  remaining="$(gpu_material_holder)"
  if [ -n "$remaining" ]; then
    warn "GPU still reports a material compute holder (>= ${GPU_MIN_MATERIAL_MIB}MiB):"
    warn "$remaining"
    rc=1
  else
    log "GPU released: no material compute holder and no provider process"
  fi

  # Stop the supervisor too: it holds the server's stdout pipe and would
  # otherwise linger after the server exits.
  local sup=""
  [ -f "$SUP_PID_FILE" ] && sup="$(cat "$SUP_PID_FILE" 2>/dev/null || true)"
  if [ -n "$sup" ] && pid_alive "$sup" && pid_matches_supervisor "$sup"; then
    log "stopping supervisor pid=$sup"
    kill -TERM "$sup" 2>/dev/null || true
  fi

  rm -f "$PID_FILE" "$SUP_PID_FILE" "$AUTH_CONFIG"
  state_write "free" "-" "down" "stopped"
  return "$rc"
}

# The supervisor is identified by its own script path plus our run dir, so we
# never signal an unrelated python process.
pid_matches_supervisor() {
  local pid="$1" cl
  pid_alive "$pid" || return 1
  cl="$(pid_cmdline "$pid")"
  case "$cl" in *provider-supervise.py*) ;; *) return 1 ;; esac
  case "$cl" in *"$RUN_DIR"*) ;; *) return 1 ;; esac
  return 0
}
