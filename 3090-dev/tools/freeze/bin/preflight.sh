#!/usr/bin/env bash
# preflight — external, independent source-identity + namespace gate for a
# LOCAL-PROD frozen tree.  This is the gate a harness runs BEFORE launching.
#
# It composes, and fails closed on any mismatch:
#   1. the reviewed reusable engine (verbatim, sha256-pinned) for
#      (a) sglang.__file__ resolves inside the intended tree,
#      (b) the tree manifest digest matches identity.json,
#      (c) key-file (default: ALL) hashes match TREE-SHA256.txt,
#      (d) /proc/<pid>/environ shows the intended PYTHONPATH;
#   2. the EXTERNAL pin file written at freeze time (manifest digest, launcher
#      sha256, src stream digest) - so identity.json cannot vouch for itself;
#   3. the per-run L3 namespace policy (run-unique, never shared);
#   4. the launcher repin audit + dry-run (the launcher really execs this tree).
#
# NOTE: with --pid self the caller must already bind the tree
# (PYTHONPATH=<tree>/src/python).  That is deliberate: preflight must not
# manufacture the very binding it is verifying.  With --pid <server-pid> the
# probe is bound explicitly while the target's /proc/<pid>/environ is checked
# independently.
#
# Exit codes
#   0  PASS
#   2  usage / caller not bound to the tree
#   3  manifest structure/self-digest/key-hash failure (engine)
#   4  runtime process confirmation failure (engine)
#   5  tree layout missing (engine)
#   6  engine usage error
#   10 external pin mismatch
#   11 namespace policy violation
#   12 launcher repin audit / dry-run failure
#   13 pin file missing or invalid (use --allow-unpinned to downgrade)
#   14 in-tree engine/tool hash mismatch (tree has been edited after repin)
set -euo pipefail

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOL_DIR="$(cd "$SELF_DIR/.." && pwd)"
ENGINE_PIN="$TOOL_DIR/pins/reused-preflight_identity.sha256"
L3LIB="$TOOL_DIR/lib/l3_namespace.py"
MT="$TOOL_DIR/lib/manifest_tool.py"
REPIN="$TOOL_DIR/bin/launcher-repin.sh"
WORK="$TOOL_DIR/selftest/preflight-work"
mkdir -p "$WORK"

TREE=""
PIDSPEC="self"
RUN_ID="${SGLANG_RUN_ID:-}"
L3_ROOT="${SGLANG_L3_ROOT:-/data/l3}"
IDENTITY=""
PINS=""
ALL=1
ALLOW_UNPINNED=0
LAUNCHER_CHECK=1
JSON=0
KEY_FILES=()

die() { echo "preflight: $*" >&2; exit 2; }
note() { echo "preflight: $*" >&2; }

while [ $# -gt 0 ]; do
  case "$1" in
    --tree) TREE="${2:?}"; shift 2 ;;
    --pid) PIDSPEC="${2:?}"; shift 2 ;;
    --run-id) RUN_ID="${2:?}"; shift 2 ;;
    --l3-root) L3_ROOT="${2:?}"; shift 2 ;;
    --identity) IDENTITY="${2:?}"; shift 2 ;;
    --pins) PINS="${2:?}"; shift 2 ;;
    --key-file) ALL=0; KEY_FILES+=("${2:?}"); shift 2 ;;
    --allow-unpinned) ALLOW_UNPINNED=1; shift ;;
    --no-launcher-check) LAUNCHER_CHECK=0; shift ;;
    --json) JSON=1; shift ;;
    -h|--help) sed -n '2,32p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) die "unknown argument: $1" ;;
  esac
done

[ -n "$TREE" ] || die "--tree is required"
[ -n "$RUN_ID" ] || die "--run-id (or SGLANG_RUN_ID) is required: the per-run L3 namespace check is mandatory"
case "$TREE" in /*) ;; *) die "--tree must be absolute" ;; esac
[ -d "$TREE/src" ] || { echo "preflight: tree layout missing: $TREE/src" >&2; exit 5; }

# --- 0. caller binding ----------------------------------------------------
if [ "$PIDSPEC" = "self" ]; then
  case "${PYTHONPATH:-}" in
    *"$TREE/src/python"*) ;;
    *) die "caller is not bound to the tree: PYTHONPATH must contain $TREE/src/python (the venv editable install otherwise resolves sglang to the live WIP workspace)" ;;
  esac
fi

# --- 1. in-tree tools present and unmodified since repin ------------------
ENGINE="$TREE/tools/preflight_identity.py"
if [ ! -f "$ENGINE" ]; then
  echo "preflight: in-tree engine missing: $ENGINE" >&2
  exit 14
fi
EXPECTED_ENGINE="$(awk '{print $1}' "$ENGINE_PIN")"
ACTUAL_ENGINE="$(sha256sum "$ENGINE" | cut -d' ' -f1)"
if [ "$EXPECTED_ENGINE" != "$ACTUAL_ENGINE" ]; then
  echo "preflight: in-tree engine hash mismatch (tree edited after repin?)" >&2
  echo "  pinned $EXPECTED_ENGINE" >&2
  echo "  actual $ACTUAL_ENGINE" >&2
  exit 14
fi
if [ ! -f "$TREE/tools/l3_namespace.py" ]; then
  echo "preflight: in-tree l3_namespace.py missing" >&2
  exit 14
fi
if ! diff -q "$L3LIB" "$TREE/tools/l3_namespace.py" >/dev/null; then
  echo "preflight: in-tree l3_namespace.py differs from the policy implementation" >&2
  exit 14
fi

# --- 2. engine: identity + manifest + /proc environ ------------------------
ENGINE_ARGS=(--tree "$TREE" --pid "$PIDSPEC")
if [ "$ALL" = "1" ]; then
  ENGINE_ARGS+=(--all)
else
  for kf in "${KEY_FILES[@]}"; do
    [ -n "$kf" ] || continue
    ENGINE_ARGS+=(--key-file "$kf")
  done
fi
ENGINE_ENV=(env PYTHONDONTWRITEBYTECODE=1 CUDA_VISIBLE_DEVICES=999)
if [ "$PIDSPEC" != "self" ]; then
  # bind the probe explicitly when verifying a foreign process
  ENGINE_ENV+=(PYTHONPATH="$TREE/src/python")
fi
set +e
ENGINE_JSON="$("${ENGINE_ENV[@]}" "$TREE/env/bin/python" "$ENGINE" "${ENGINE_ARGS[@]}" --json 2>&1)"
ENGINE_RC=$?
set -e
if [ "$ENGINE_RC" -ne 0 ]; then
  echo "preflight: source-identity engine FAILED (exit $ENGINE_RC)" >&2
  echo "$ENGINE_JSON" >&2
  exit "$ENGINE_RC"
fi

# --- 3. external pins -----------------------------------------------------
MANIFEST="$TREE/manifest/TREE-SHA256.txt"
if [ ! -f "$MANIFEST" ]; then
  echo "preflight: manifest missing: $MANIFEST" >&2
  exit 3
fi
MANIFEST_SHA="$(sha256sum "$MANIFEST" | cut -d' ' -f1)"
STREAM="$(python3 "$MT" src-stream --tree "$TREE")"
LAUNCHER="$TREE/launcher/launch.sh"
LAUNCHER_SHA=""
if [ -f "$LAUNCHER" ]; then
  LAUNCHER_SHA="$(sha256sum "$LAUNCHER" | cut -d' ' -f1)"
fi

if [ -z "$PINS" ]; then
  for cand in "$TREE/manifest/identity-pins.json" "$TOOL_DIR/pins/$(basename "$TREE")-pins.json"; do
    if [ -f "$cand" ]; then PINS="$cand"; break; fi
  done
fi
if [ -z "$PINS" ] || [ ! -f "$PINS" ]; then
  if [ "$ALLOW_UNPINNED" = "1" ]; then
    note "WARNING: no external pin file found; external pin check SKIPPED (--allow-unpinned)"
  else
    echo "preflight: no external pin file for $TREE (looked for manifest/identity-pins.json and pins/$(basename "$TREE")-pins.json)" >&2
    echo "preflight: pass --pins <file> or --allow-unpinned" >&2
    exit 13
  fi
else
  PINS_RC=0
  PINS_OUT="$(python3 - "$PINS" "$MANIFEST_SHA" "$LAUNCHER_SHA" "$STREAM" <<'PY'
import json, sys
pins_path, manifest_sha, launcher_sha, stream = sys.argv[1:5]
pins = json.load(open(pins_path))
bad = []
for key, actual in (
    ("tree_manifest_sha256", manifest_sha),
    ("src_stream_digest_v1_convention", stream),
    ("launcher_sha256", launcher_sha),
):
    if key not in pins:
        bad.append(f"{key}: missing from pin file")
    elif pins[key] != actual:
        bad.append(f"{key}: expected {pins[key]} got {actual}")
if bad:
    print("PIN MISMATCH", file=sys.stderr)
    for b in bad:
        print("  " + b, file=sys.stderr)
    sys.exit(1)
print(json.dumps({"pins": pins_path, "ok": True}))
PY
)" || PINS_RC=$?
  if [ "$PINS_RC" -ne 0 ]; then
    echo "preflight: external pin mismatch (exit 10)" >&2
    if [ -n "$PINS_OUT" ]; then echo "$PINS_OUT" >&2; fi
    exit 10
  fi
fi

# --- 4. namespace policy --------------------------------------------------
NS_ARGS=(--validate --task-id "$RUN_ID" --root "$L3_ROOT" --json)
NS_RC=0
NS_OUT="$(python3 "$L3LIB" "${NS_ARGS[@]}" --expect-tree-digest "$MANIFEST_SHA")" || NS_RC=$?
if [ "$NS_RC" -ne 0 ]; then
  echo "preflight: L3 namespace policy violation (exit 11; helper exit $NS_RC)" >&2
  echo "$NS_OUT" >&2
  exit 11
fi

# --- 5. launcher repin audit + dry run ------------------------------------
if [ "$LAUNCHER_CHECK" = "1" ]; then
  if [ ! -f "$LAUNCHER" ]; then
    echo "preflight: launcher missing: $LAUNCHER" >&2
    exit 12
  fi
  if [ -z "$IDENTITY" ]; then
    IDENTITY="$(python3 -c "import json,sys;print(json.load(open(sys.argv[1])).get('name',''))" "$TREE/manifest/identity.json" 2>/dev/null || true)"
  fi
  if [ -z "$IDENTITY" ]; then
    echo "preflight: cannot determine identity name; pass --identity" >&2
    exit 2
  fi
  REPIN_LOG="$WORK/repin-verify-$$.log"
  if ! "$REPIN" --verify-installed --tree "$TREE" --identity "$IDENTITY" \
        --run-id "preflight-$(date -u +%Y%m%dT%H%M%SZ)-$$" >"$REPIN_LOG" 2>&1; then
    echo "preflight: launcher repin audit/dry-run FAILED (exit 12); log:" >&2
    cat "$REPIN_LOG" >&2
    exit 12
  fi
fi

# --- summary --------------------------------------------------------------
REPORT="$(printf '{"gate":"preflight","tree":"%s","run_id":"%s","l3_root":"%s","l3_namespace":"%s/%s","manifest_sha256":"%s","src_stream_digest_v1_convention":"%s","launcher_sha256":"%s","pins":"%s","engine_exit":"%s","result":"PASS"}' \
  "$TREE" "$RUN_ID" "$L3_ROOT" "$L3_ROOT" "$RUN_ID" "$MANIFEST_SHA" "$STREAM" "$LAUNCHER_SHA" "${PINS:-none}" "$ENGINE_RC")"
if [ "$JSON" = "1" ]; then
  echo "$REPORT"
else
  echo "PREFLIGHT PASS: $REPORT"
fi
exit 0
