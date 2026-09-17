#!/usr/bin/env bash
# preflight.sh — fail-closed source-identity + environment gate.
#
# Usage: preflight.sh <tree> <cpu-only?>
#   <tree>      absolute path to the frozen tree
#   <cpu-only?> "cpu" to also force CUDA_VISIBLE_DEVICES=999 for any import
#
# Exits 0 only if EVERY check passes.  Any failure exits non-zero and the
# caller must start nothing.  This script never starts a server and never
# binds a port.
#
# Checks
#   P1 tree layout (+ identity manifest present)
#   P2 recorded manifest digest matches the manifest bytes
#   P3 recorded launcher sha256 matches the launcher bytes
#   P4 launcher enforces the source-identity gate (v1.1.2+) — else REFUSE
#   P5 launcher enforces the per-run L3 namespace gate (v1.1.2+) — else REFUSE
#   P6 PYTHONPATH binding: sglang.__file__ resolves INSIDE <tree>/src/python
#   P7 reserved L3 store is present and must never be the run's target

set -euo pipefail
# shellcheck source=/dev/null
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

TREE="${1:?usage: preflight.sh <tree> [cpu]}"
CPU="${2:-}"
RC=0
declare -a FAILS=()

fail() { FAILS+=("$1"); RC=1; }

log "preflight: tree=$TREE"

# ---- P1 layout --------------------------------------------------------------
[ -d "$TREE" ]            || fail "P1 tree missing: $TREE"
[ -x "$(tree_launcher "$TREE")" ] || fail "P1 launcher missing/not executable: $(tree_launcher "$TREE")"
[ -x "$(tree_python "$TREE")" ]   || fail "P1 tree python missing: $(tree_python "$TREE")"
[ -f "$(tree_identity_json "$TREE")" ] || fail "P1 identity.json missing: $(tree_identity_json "$TREE")"
[ -d "$TREE/src/python/sglang" ]        || fail "P1 src/python/sglang missing: $TREE/src/python/sglang"
[ -f "$TREE/manifest/TREE-SHA256.txt" ] || fail "P1 manifest/TREE-SHA256.txt missing"
[ "${#FAILS[@]}" -eq 0 ] || { printf 'REFUSE: %s\n' "${FAILS[@]}" >&2; exit 2; }

# ---- P2 manifest digest -----------------------------------------------------
REC_DIGEST="$(tree_recorded_digest "$TREE" || true)"
ACT_DIGEST="$(sha256sum "$TREE/manifest/TREE-SHA256.txt" | cut -d' ' -f1)"
if [ -z "$REC_DIGEST" ]; then
  fail "P2 identity.json does not record a tree manifest digest"
elif [ "$REC_DIGEST" != "$ACT_DIGEST" ]; then
  fail "P2 manifest digest mismatch: recorded=$REC_DIGEST actual=$ACT_DIGEST"
else
  log "P2 manifest digest OK: $ACT_DIGEST"
fi

# ---- P3 launcher sha --------------------------------------------------------
REC_LAUNCH="$(tree_recorded_launcher_sha "$TREE" || true)"
ACT_LAUNCH="$(sha256sum "$(tree_launcher "$TREE")" | cut -d' ' -f1)"
if [ -z "$REC_LAUNCH" ]; then
  fail "P3 identity.json does not record a launcher sha256"
elif [ "$REC_LAUNCH" != "$ACT_LAUNCH" ]; then
  fail "P3 launcher sha mismatch: recorded=$REC_LAUNCH actual=$ACT_LAUNCH"
else
  log "P3 launcher sha OK: $ACT_LAUNCH"
fi

# ---- P4/P5 launcher gate capability ----------------------------------------
# A tree whose launcher lacks the identity gate can silently run the wrong
# source (the v1 -> v1.1 failure mode).  Refuse it for production.
if tree_has_identity_gate "$TREE"; then
  log "P4 launcher enforces the source-identity gate"
else
  fail "P4 launcher does NOT enforce the source-identity gate (untrusted for production): $TREE"
fi
if tree_has_namespace_gate "$TREE"; then
  log "P5 launcher enforces the per-run L3 namespace gate"
else
  fail "P5 launcher does NOT enforce the per-run L3 namespace gate: $TREE"
fi

# ---- P6 PYTHONPATH binding (the editable-install landmine) ------------------
# Without PYTHONPATH, `import sglang` falls through to the venv editable
# binding, which points at the STALE live WIP workspace.  Demonstrate both:
#   * WITHOUT PYTHONPATH the resolution is (or may be) outside the tree
#   * WITH PYTHONPATH it is inside
bind_check() {
  local extra_env="$1"
  # shellcheck disable=SC2086
  env $extra_env CUDA_VISIBLE_DEVICES=999 PYTHONDONTWRITEBYTECODE=1 \
      "$(tree_python "$TREE")" -c \
      'import os,sys; import sglang; print(os.path.realpath(sglang.__file__))' 2>/dev/null
}

BOUND="$(bind_check "PYTHONPATH=$TREE/src/python")" || BOUND=""
if [ -z "$BOUND" ]; then
  fail "P6 could not import sglang with PYTHONPATH=$TREE/src/python"
elif [ "${BOUND#"$TREE/src/python/"}" = "$BOUND" ]; then
  fail "P6 sglang resolved OUTSIDE the tree: $BOUND (expected under $TREE/src/python)"
else
  log "P6 sglang.__file__ OK: $BOUND"
fi

UNBOUND="$(bind_check "")" || UNBOUND=""
if [ -n "$UNBOUND" ] && [ "${UNBOUND#"$TREE/src/python/"}" = "$UNBOUND" ]; then
  warn "P6 LANDMINE CONFIRMED: without PYTHONPATH, import sglang resolves to $UNBOUND"
  warn "   This is the stale workspace copy.  The launcher sets PYTHONPATH itself;"
  warn "   never invoke launch_server directly without it."
fi

# ---- P7 reserved store ------------------------------------------------------
if [ -d "$RESERVED_L3_STORE" ]; then
  log "P7 shared production L3 store present and MUST NOT be cleared: $RESERVED_L3_STORE"
else
  warn "P7 shared production L3 store not present: $RESERVED_L3_STORE"
fi

if [ "$RC" -ne 0 ]; then
  printf '\nPREFLIGHT FAILED:\n' >&2
  printf '  - %s\n' "${FAILS[@]}" >&2
  exit 1
fi
log "preflight PASS: $TREE"
exit 0
