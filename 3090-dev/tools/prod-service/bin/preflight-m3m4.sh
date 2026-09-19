#!/usr/bin/env bash
# preflight-m3m4.sh — fail-closed gate for the M3/M4 worktree-source envelopes.
#
# Usage: preflight-m3m4.sh <tree> <worktree-src>
#   <tree>          /opt/sglang/local-prod-m3m4-20260918/{M3,M4}
#   <worktree-src>  worktree repo root (M3M4_SRC_DEFAULT)
#
# Why a separate script: preflight.sh's P6 resolves sglang.__file__ with
# os.path.realpath and REQUIRES it under <tree>/src/python.  The envelope's
# src is a symlink to the worktree, so P6 would always FAIL by construction.
# This gate therefore validates the envelope + the worktree pin instead, and
# deliberately does NOT import sglang and does NOT bind any port / take any lock.
#
# Exits 0 only if every check passes.  Any failure exits non-zero and the
# caller must start nothing.

set -euo pipefail
# shellcheck source=/dev/null
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

TREE="${1:?usage: preflight-m3m4.sh <tree> <worktree-src>}"
SRC_DEFAULT="${2:?usage: preflight-m3m4.sh <tree> <worktree-src>}"
RC=0
declare -a FAILS=()
fail() { FAILS+=("$1"); RC=1; }

ROLE="$(basename "$TREE")"
log "m3m4-preflight: tree=$TREE role=$ROLE src_default=$SRC_DEFAULT"

# ---- M1 envelope layout -----------------------------------------------------
[ -d "$TREE" ]                                  || fail "M1 tree missing: $TREE"
[ -x "$(tree_launcher "$TREE")" ]               || fail "M1 launcher missing/not executable: $(tree_launcher "$TREE")"
[ -x "$(tree_python "$TREE")" ]                 || fail "M1 tree python missing: $(tree_python "$TREE")"
[ -f "$(tree_identity_json "$TREE")" ]          || fail "M1 identity.json missing: $(tree_identity_json "$TREE")"
[ -d "$TREE/src/python/sglang" ]                || fail "M1 src/python/sglang missing: $TREE/src/python/sglang"
[ -n "$(jq -r '.name // empty' "$(tree_identity_json "$TREE")" 2>/dev/null || true)" ] \
                                                || fail "M1 identity.json has no .name"
[ "${#FAILS[@]}" -eq 0 ] || { printf 'REFUSE: %s\n' "${FAILS[@]}" >&2; exit 2; }

# ---- M2 worktree pin (commit + clean python/) -------------------------------
GOT_COMMIT="$(git -C "$SRC_DEFAULT" rev-parse HEAD 2>/dev/null || true)"
if [ "$GOT_COMMIT" != "$M3M4_SRC_PIN_COMMIT" ]; then
  fail "M2 worktree commit mismatch: got=$GOT_COMMIT want=$M3M4_SRC_PIN_COMMIT"
else
  log "M2 worktree commit OK: $GOT_COMMIT"
fi
DIRTY="$(git -C "$SRC_DEFAULT" status --porcelain -- python/ 2>/dev/null || true)"
if [ -n "$DIRTY" ]; then
  fail "M2 worktree python/ is dirty (source not pinned): $DIRTY"
else
  log "M2 worktree python/ clean"
fi

# ---- M3 critical-file shas --------------------------------------------------
GOT_GGUF="$(sha256sum "$SRC_DEFAULT/python/sglang/srt/utils/hf_transformers/gguf_native.py" 2>/dev/null | cut -d' ' -f1 || true)"
if [ "$GOT_GGUF" != "$M3M4_SRC_PIN_GGUF_NATIVE_SHA" ]; then
  fail "M3 gguf_native.py sha mismatch: got=$GOT_GGUF want=$M3M4_SRC_PIN_GGUF_NATIVE_SHA"
else
  log "M3 gguf_native.py sha OK: $GOT_GGUF"
fi
GOT_Q35="$(sha256sum "$SRC_DEFAULT/python/sglang/srt/models/qwen3_5_text.py" 2>/dev/null | cut -d' ' -f1 || true)"
WANT_Q35="d51d5441064c13cb90da9af7399c067e072182e7bc8c362e72ea4ba6a11e3941"
if [ "$GOT_Q35" != "$WANT_Q35" ]; then
  fail "M3 qwen3_5_text.py sha mismatch: got=$GOT_Q35 want=$WANT_Q35"
else
  log "M3 qwen3_5_text.py sha OK: $GOT_Q35"
fi

# ---- M4 resolved source is the worktree, not a frozen tree ------------------
RESOLVED="$(realpath "$TREE/src/python" 2>/dev/null || true)"
WANT_RESOLVED="$(realpath "$SRC_DEFAULT/python" 2>/dev/null || true)"
if [ -z "$RESOLVED" ] || [ "$RESOLVED" != "$WANT_RESOLVED" ]; then
  fail "M4 src/python does not resolve to the worktree: got=$RESOLVED want=$WANT_RESOLVED"
else
  log "M4 src/python resolves to worktree: $RESOLVED"
fi
case "$RESOLVED" in
  /opt/sglang/local-prod-*) fail "M4 src/python resolves into a frozen production tree: $RESOLVED" ;;
esac

# model file present + readable (per role)
case "$ROLE" in
  M3) MODEL_FILE="${M3_MODEL_PATH:-/data/models/Qwen3.8-27B-GSQ-RCO-IQ3_S.gguf}" ;;
  M4) MODEL_FILE="${M4_MODEL_PATH:-/data/models/swift-qwen38-27b-q3_k_m/Swift-Qwen3.8-27B-Q3_K_M.gguf}" ;;
  *)  fail "M4 unknown role for model check: $ROLE"; MODEL_FILE="" ;;
esac
if [ -n "$MODEL_FILE" ]; then
  if [ ! -f "$MODEL_FILE" ]; then
    fail "M4 model file missing: $MODEL_FILE"
  elif [ ! -r "$MODEL_FILE" ]; then
    fail "M4 model file not readable: $MODEL_FILE"
  else
    log "M4 model file OK: $MODEL_FILE"
  fi
fi

# ---- M5 L3 disabled (fail-closed) + /data/l3 untouched ----------------------
L3_MODE="${SGLANG_L3_MODE:-disabled}"
if [ "$L3_MODE" != "disabled" ]; then
  fail "M5 SGLANG_L3_MODE must be 'disabled' for $ROLE; got '$L3_MODE'"
else
  log "M5 L3 mode OK: disabled"
fi
if grep -q 'l3_namespace.py' "$(tree_launcher "$TREE")" 2>/dev/null; then
  fail "M5 launcher references l3_namespace.py; worktree envelope must not gate L3"
else
  log "M5 launcher does not gate L3; /data/l3 is not touched by this path"
fi

if [ "$RC" -ne 0 ]; then
  printf '\nM3M4 PREFLIGHT FAILED:\n' >&2
  printf '  - %s\n' "${FAILS[@]}" >&2
  exit 1
fi
log "m3m4 preflight PASS: $TREE"
exit 0
