#!/usr/bin/env bash
# launcher-repin — render, statically audit and DRY-RUN-verify launcher/launch.sh
# for a new LOCAL-PROD identity.
#
# The v1 -> v1.1 incident: the v1.1 candidate shipped a launcher that was a
# byte-for-byte copy of v1's, so launching it would have silently evaluated the
# models on v1 source.  This tool makes that class of error impossible:
#   * it renders from a template, so the tree path / identity / stream pin are
#     substituted, never hand-edited;
#   * it rejects any launcher that references a different /opt/sglang tree;
#   * it rejects a byte copy of the v1 or v1.1 launcher;
#   * it proves the launcher's own fail-closed gate passes and that the exec'd
#     argv is what we think it is, via a dry-run that never starts a server and
#     never binds a port.
#
# Exit codes
#   0  OK
#   2  usage error
#   20 render failure
#   21 bash -n failure
#   22 static audit failure
#   23 launcher is a byte copy of a known older launcher (not a repin)
#   24 dry-run failed
#   25 dry-run had side effects (must be none)
#   26 install/write failure
set -euo pipefail

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOL_DIR="$(cd "$SELF_DIR/.." && pwd)"
TEMPLATE="$TOOL_DIR/templates/launch.sh.tmpl"
AUDIT="$TOOL_DIR/lib/audit_launcher.py"
L3LIB="$TOOL_DIR/lib/l3_namespace.py"

TREE=""
IDENTITY=""
MODE=""
REF_LAUNCHER="/opt/sglang/local-prod-v1.1-candidate/launcher/launch.sh"
V1_LAUNCHER="/opt/sglang/local-prod-v1/launcher/launch.sh"
RUN_ID="selftest-repin-$(date -u +%Y%m%dT%H%M%SZ)-$$"
SCRATCH="$TOOL_DIR/selftest/repin-working"
DO_DRY_RUN=1

die() { echo "launcher-repin: $*" >&2; exit 2; }

while [ $# -gt 0 ]; do
  case "$1" in
    --tree) TREE="${2:?}"; shift 2 ;;
    --identity) IDENTITY="${2:?}"; shift 2 ;;
    --write) MODE="write"; shift ;;
    --verify-only) MODE="verify"; shift ;;
    --verify-installed) MODE="verify-installed"; shift ;;
    --ref-launcher) REF_LAUNCHER="${2:?}"; shift 2 ;;
    --v1-launcher) V1_LAUNCHER="${2:?}"; shift 2 ;;
    --run-id) RUN_ID="${2:?}"; shift 2 ;;
    --scratch) SCRATCH="${2:?}"; shift 2 ;;
    --no-dry-run) DO_DRY_RUN=0; shift ;;
    -h|--help) sed -n '2,20p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) die "unknown argument: $1" ;;
  esac
done

[ -n "$TREE" ] || die "--tree is required"
[ -n "$IDENTITY" ] || die "--identity is required"
[ -n "$MODE" ] || die "one of --write, --verify-only or --verify-installed is required"
case "$TREE" in /*) ;; *) die "--tree must be absolute" ;; esac
[ -d "$TREE/src" ] || die "no such tree src: $TREE/src"
[ -f "$TEMPLATE" ] || die "template missing: $TEMPLATE"

TREE_NAME="$(basename "$TREE")"
mkdir -p "$SCRATCH"
RENDERED="$SCRATCH/launch.sh.rendered"
LAUNCHER_TARGET="$TREE/launcher/launch.sh"

echo "== launcher-repin: tree=$TREE identity=$IDENTITY mode=$MODE =="

# --- 1. compute the src-subtree stream digest (v1 convention) --------------
STREAM_SHA="$( cd "$TREE/src" && find . -type f \
    -not -path '*/__pycache__/*' -not -path '*/.pytest_cache/*' -print0 \
    | LC_ALL=C sort -z | xargs -0 sha256sum | sha256sum | cut -d' ' -f1 )"
echo "   src_stream_sha256=$STREAM_SHA"

# --- 2. render (or audit the file already installed in the tree) ----------
if [ "$MODE" = "verify-installed" ]; then
  AUDIT_FILE="$LAUNCHER_TARGET"
  [ -f "$AUDIT_FILE" ] || { echo "no installed launcher to verify: $AUDIT_FILE" >&2; exit 22; }
  echo "   auditing INSTALLED launcher $AUDIT_FILE"
else
  python3 - "$TEMPLATE" "$RENDERED" "$TREE" "$IDENTITY" "$TREE_NAME" "$STREAM_SHA" <<'PY' || { echo "render failed" >&2; exit 20; }
import sys
tmpl, out, tree, identity, tree_name, stream = sys.argv[1:7]
text = open(tmpl).read()
for token, value in (
    ("@@TREE@@", tree),
    ("@@IDENTITY@@", identity),
    ("@@TREE_NAME@@", tree_name),
    ("@@SRC_STREAM_SHA256@@", stream),
):
    text = text.replace(token, value)
left = [l for l in text.splitlines() if "@@" in l]
if left:
    print("unsubstituted tokens remain: " + "; ".join(left), file=sys.stderr)
    sys.exit(1)
open(out, "w").write(text)
PY
  chmod 0755 "$RENDERED"
  echo "   rendered -> $RENDERED"
  AUDIT_FILE="$RENDERED"
fi

# --- 3. syntax ------------------------------------------------------------
bash -n "$AUDIT_FILE" || { echo "bash -n FAILED for $AUDIT_FILE" >&2; exit 21; }
echo "   bash -n: OK"

# --- 4. static audit ------------------------------------------------------
REF_ARG=()
if [ -f "$REF_LAUNCHER" ]; then REF_ARG=(--ref-launcher "$REF_LAUNCHER"); fi
if ! python3 "$AUDIT" --launcher "$AUDIT_FILE" --tree "$TREE" --identity "$IDENTITY" \
      --expect-stream "$STREAM_SHA" "${REF_ARG[@]}"; then
  echo "static audit FAILED" >&2
  exit 22
fi

# --- 5. not a byte copy of a known older launcher -------------------------
NEW_SHA="$(sha256sum "$AUDIT_FILE" | cut -d' ' -f1)"
for old in "$V1_LAUNCHER" "$REF_LAUNCHER"; do
  if [ -f "$old" ]; then
    old_sha="$(sha256sum "$old" | cut -d' ' -f1)"
    if [ "$NEW_SHA" = "$old_sha" ]; then
      echo "REPIN FAILED: rendered launcher is a byte copy of $old" >&2
      exit 23
    fi
  fi
done
echo "   launcher_sha256=$NEW_SHA"

# --- 6. dry-run: gate passes, argv is known, nothing starts ---------------
if [ "$DO_DRY_RUN" = "1" ]; then
  for tool in "$TREE/tools/preflight_identity.py" "$TREE/tools/l3_namespace.py"; do
    [ -f "$tool" ] || { echo "dry-run impossible: identity tool missing: $tool" >&2; exit 24; }
  done
  DRY_ROOT="$SCRATCH/dry-run-l3"
  DRY_LOG="$SCRATCH/dry-run-log-$RUN_ID"
  rm -rf "$DRY_ROOT" "$DRY_LOG"
  python3 "$L3LIB" --allocate --task-id "$RUN_ID" --root "$DRY_ROOT" \
    --expect-tree-digest "$STREAM_SHA" --json >/dev/null

  # 6a. negative: a shared/reserved run id must be refused before any gate work
  set +e
  REFUSE_OUT="$(env -i PATH=/usr/bin:/bin HOME="${HOME:-/home/ubuntu}" \
      SGLANG_RUN_ID="local-prod-v1.1" SGLANG_L3_ROOT="$DRY_ROOT" \
      SGLANG_LOG_DIR="$DRY_LOG" SGLANG_LAUNCH_DRY_RUN=1 \
      /bin/bash "$AUDIT_FILE" 2>&1)"
  REFUSE_RC=$?
  set -e
  if [ "$REFUSE_RC" -ne 4 ]; then
    echo "dry-run negative test FAILED: shared run id should exit 4, got $REFUSE_RC" >&2
    echo "$REFUSE_OUT" >&2
    exit 24
  fi
  echo "   dry-run negative (shared namespace refused): OK (exit 4)"

  # 6b. positive dry-run
  set +e
  DRY_OUT="$(env -i PATH=/usr/bin:/bin HOME="${HOME:-/home/ubuntu}" \
      SGLANG_RUN_ID="$RUN_ID" SGLANG_L3_ROOT="$DRY_ROOT" \
      SGLANG_LOG_DIR="$DRY_LOG" SGLANG_LAUNCH_DRY_RUN=1 \
      /bin/bash "$AUDIT_FILE" 2>&1)"
  DRY_RC=$?
  set -e
  if [ "$DRY_RC" -ne 0 ]; then
    echo "dry-run FAILED (exit $DRY_RC)" >&2
    echo "$DRY_OUT" >&2
    exit 24
  fi
  printf '%s\n' "$DRY_OUT" > "$SCRATCH/dry-run-$RUN_ID.log"
  grep -q "^DRY-RUN OK identity=$IDENTITY tree=$TREE run_id=$RUN_ID " <<<"$DRY_OUT" \
    || { echo "dry-run identity line mismatch" >&2; printf '%s\n' "$DRY_OUT" >&2; exit 24; }
  grep -q "^DRY-RUN src_stream_sha256=$STREAM_SHA$" <<<"$DRY_OUT" \
    || { echo "dry-run stream digest mismatch" >&2; exit 24; }
  grep -q "^DRY-RUN argv: $TREE/env/bin/python -u -m sglang.launch_server" <<<"$DRY_OUT" \
    || { echo "dry-run argv does not exec the intended tree interpreter" >&2; printf '%s\n' "$DRY_OUT" >&2; exit 24; }
  if grep -qE "local-prod-v1(\.1)?/" <<<"$DRY_OUT"; then
    echo "dry-run argv references a foreign tree" >&2; exit 24
  fi
  if [ -e "$DRY_LOG" ]; then
    echo "dry-run created LOG_DIR ($DRY_LOG): side effect forbidden" >&2
    exit 25
  fi
  echo "   dry-run: OK (gates ran, argv verified, no side effects)"
fi

# --- 7. install (only after audit+dry-run passed) -------------------------
if [ "$MODE" = "write" ]; then
  if [ -f "$LAUNCHER_TARGET" ]; then
    PRE_SHA="$(sha256sum "$LAUNCHER_TARGET" | cut -d' ' -f1)"
    cp -p "$LAUNCHER_TARGET" "$SCRATCH/launch.sh.pre-repin-$RUN_ID"
    echo "   pre-repin launcher preserved: $SCRATCH/launch.sh.pre-repin-$RUN_ID ($PRE_SHA)"
  fi
  install -m 0555 "$RENDERED" "$LAUNCHER_TARGET" || { echo "install failed" >&2; exit 26; }
  echo "   installed -> $LAUNCHER_TARGET (mode $(stat -c '%a' "$LAUNCHER_TARGET"))"
fi

echo "LAUNCHER-REPIN PASS: $TREE launcher_sha256=$NEW_SHA"
exit 0
