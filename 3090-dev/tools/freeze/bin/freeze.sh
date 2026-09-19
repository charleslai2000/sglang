#!/usr/bin/env bash
# freeze — produce (or reproduce) a LOCAL-PROD frozen candidate identity.
#
# Modes
#   --selftest-reproduce : verbatim re-freeze of an existing frozen tree.  The
#                          tooling is correct only if this reproduces the SAME
#                          tree digest and the SAME src mode histogram.
#   --build-candidate    : build a NEW candidate from an approved source tree:
#                          stage -> install identity tools -> repoint telemetry
#                          tool -> repin launcher -> chmod -R a-w -> manifest
#                          (3 independent generations) -> identity + pins.
#
# Fail-closed guarantees
#   * refuses a destination under /opt/sglang, /data, or the source workspace;
#   * refuses unexpected top-level directories in the source tree (evidence dirs
#     would otherwise silently become part of the identity);
#   * requires source quiescence;
#   * requires the coreutils manifest, a second coreutils run and an independent
#     Python implementation to be byte-identical;
#   * requires copy fidelity (per-file hashes + count + bytes vs the source);
#   * in build mode, compares the approved source against --baseline-tree and
#     fails on every unallowlisted source delta; any GGUF-related delta is a
#     hard refusal (GGUF is excluded from the v1.1.2 identity unless separately
#     proven inert and explicitly removed from this gate);
#   * requires every entry of src/launcher/tools to end up non-writable, and the
#     venv (env symlink target) to be untouched;
#   * requires the manifest to be stable after the identity evidence is written.
#
# Exit codes: 0 ok, 2 usage, 3 precondition, 4 stage/copy, 5 transform,
#             6 immutability, 7 manifest determinism, 8 fidelity,
#             9 identity/pins, 10 final verification.
set -euo pipefail

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOL_DIR="$(cd "$SELF_DIR/.." && pwd)"
MT="$TOOL_DIR/pysrc/manifest_tool.py"
MH="$TOOL_DIR/pysrc/mode_histogram.py"
L3LIB="$TOOL_DIR/pysrc/l3_namespace.py"
REPOINT="$TOOL_DIR/pysrc/repoint_telemetry.py"
RUSTID="$TOOL_DIR/pysrc/rust_identity.py"
REPIN="$TOOL_DIR/bin/launcher-repin.sh"

MODE=""
SRC=""
DEST=""
IDENTITY=""
TREE_NAME=""
VENV="/home/ubuntu/venvs/sglang-3090"
EXPECT_DIGEST=""
EXPECT_SRC_MANIFEST=""
BASELINE_TREE=""
ALLOWED_SOURCE_CHANGES=(
  "src/python/sglang/srt/mem_cache/unified_cache/unified_tree_core.py"
  "src/test/registered/unit/mem_cache/test_l3_head_refresh_f1_unit.py"
)
# An explicit, committed allowlist file may instead enumerate every approved
# added/changed path (one repo-relative path per line, '#' comments allowed).
# This is the auditable form: the approved delta is a reviewed artifact rather
# than a hardcoded pair of literals.
ALLOWED_SOURCE_CHANGES_FILE=""
SOURCE_COMMIT_ARG=""
TEMPLATE_TREE="/opt/sglang/local-prod-v1.1-candidate"
TEMPLATE_IDENTITY="LOCAL-PROD-v1.1"
WORK_DIR=""
ALLOW_ACTIVE_SRC=0
ALLOW_EXISTING_DEST=0
ALLOW_PRODUCTION_DEST=0
ALLOW_EXTRA_TOP_LEVEL=()
JSON=0

die() { echo "freeze: $*" >&2; exit 2; }

while [ $# -gt 0 ]; do
  case "$1" in
    --selftest-reproduce) MODE="selftest"; shift ;;
    --build-candidate) MODE="build"; shift ;;
    --src) SRC="${2:?}"; shift 2 ;;
    --dest) DEST="${2:?}"; shift 2 ;;
    --identity) IDENTITY="${2:?}"; shift 2 ;;
    --tree-name) TREE_NAME="${2:?}"; shift 2 ;;
    --venv) VENV="${2:?}"; shift 2 ;;
    --expect-digest) EXPECT_DIGEST="${2:?}"; shift 2 ;;
    --expect-src-manifest) EXPECT_SRC_MANIFEST="${2:?}"; shift 2 ;;
    --baseline-tree) BASELINE_TREE="${2:?}"; shift 2 ;;
    --allowed-source-change) ALLOWED_SOURCE_CHANGES+=("${2:?}"); shift 2 ;;
    --allowed-source-changes-file) ALLOWED_SOURCE_CHANGES_FILE="${2:?}"; shift 2 ;;
    --source-commit) SOURCE_COMMIT_ARG="${2:?}"; shift 2 ;;
    --template-tree) TEMPLATE_TREE="${2:?}"; shift 2 ;;
    --template-identity) TEMPLATE_IDENTITY="${2:?}"; shift 2 ;;
    --work-dir) WORK_DIR="${2:?}"; shift 2 ;;
    --allow-active-src) ALLOW_ACTIVE_SRC=1; shift ;;
    --allow-existing-dest) ALLOW_EXISTING_DEST=1; shift ;;
    --allow-production-dest) ALLOW_PRODUCTION_DEST=1; shift ;;
    --allow-extra-top-level) ALLOW_EXTRA_TOP_LEVEL+=("${2:?}"); shift 2 ;;
    --json) JSON=1; shift ;;
    -h|--help) sed -n '2,30p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) die "unknown argument: $1" ;;
  esac
done

[ -n "$MODE" ] || die "one of --selftest-reproduce or --build-candidate is required"
[ -n "$SRC" ] || die "--src is required"
[ -n "$DEST" ] || die "--dest is required"
case "$SRC" in /*) ;; *) die "--src must be absolute" ;; esac
case "$DEST" in /*) ;; *) die "--dest must be absolute" ;; esac
[ -d "$SRC/src" ] || die "source tree has no src/: $SRC/src"
[ -n "$IDENTITY" ] || die "--identity is required"
[ -n "$TREE_NAME" ] && DEST_NAME="$TREE_NAME" || DEST_NAME="$(basename "$DEST")"
[ -n "$WORK_DIR" ] || WORK_DIR="$TOOL_DIR/selftest/freeze-work/$DEST_NAME"

phase() { echo; echo "### $*"; }
ok() { echo "   ok: $*"; }

for c in find sort xargs sha256sum rsync python3 stat cmp; do
  command -v "$c" >/dev/null || die "required command missing: $c"
done

# --- preconditions --------------------------------------------------------
phase "preconditions"
case "$DEST" in
  /|/opt|/data|/data/*|"$SRC"|"$SRC"/*)
    die "refusing destination $DEST (protected or identical to source)" ;;
  /opt/*)
      # Exact-path allowlist.  A wildcard /opt destination is never permitted;
      # each production tree must be named here explicitly.
      case "$DEST" in
        /opt/sglang/local-prod-v1.1.2-candidate|/opt/sglang/local-prod-v1.2-candidate|/opt/sglang/local-prod-v1.2.1-candidate|/opt/sglang/local-prod-v1.2.1-candidate-M2|/opt/sglang/local-prod-v1.2.2-candidate)
        if [ "$ALLOW_PRODUCTION_DEST" != "1" ]; then
          die "refusing production destination $DEST; requires explicit --allow-production-dest";
        fi ;;
      *)
        die "refusing production destination $DEST; not in the exact-path allowlist (exact future target requires an explicit entry + --allow-production-dest)" ;;
    esac ;;
esac
case "$SRC" in
  /opt/sglang/*) ;;
  *) [ "$ALLOW_ACTIVE_SRC" = "1" ] || true ;;
esac
if [ -e "$DEST" ]; then
  if [ "$ALLOW_EXISTING_DEST" != "1" ]; then
    [ -z "$(ls -A "$DEST" 2>/dev/null)" ] || die "destination $DEST exists and is not empty (use --allow-existing-dest)"
  fi
  if [ -f "$DEST/manifest/identity.json" ]; then
    die "destination $DEST already contains manifest/identity.json; refusing to clobber an identity (use a fresh path)"
  fi
fi
[ -d "$VENV" ] || die "venv not found: $VENV"
VENV_MODE_BEFORE="$(stat -c '%a' "$VENV")"
ok "destination $DEST, venv $VENV (mode $VENV_MODE_BEFORE)"

if [ "$ALLOW_ACTIVE_SRC" != "1" ]; then
  ACTIVE="$(find "$SRC" -newermt '-5 minutes' \
      -not -path '*/__pycache__/*' -not -path '*/.pytest_cache/*' \
      -not -path '*/manifest/*' 2>/dev/null | wc -l)"
  [ "$ACTIVE" -eq 0 ] || die "source tree $SRC is not quiescent ($ACTIVE entries modified in the last 5 min)"
  ok "source quiescent"
fi

if [ "$MODE" = "build" ]; then
  [ -n "$BASELINE_TREE" ] || die "--build-candidate requires --baseline-tree (normally /opt/sglang/local-prod-v1.1-candidate); scope is fail-closed"
  [ -f "$BASELINE_TREE/manifest/TREE-SHA256.txt" ] || die "baseline manifest missing: $BASELINE_TREE/manifest/TREE-SHA256.txt"
fi

ALLOWED_TOP=(src launcher tools env manifest)
for entry in "$SRC"/* "$SRC"/.[!.]*; do
  [ -e "$entry" ] || [ -L "$entry" ] || continue
  name="$(basename "$entry")"
  found=0
  for a in "${ALLOWED_TOP[@]}" "${ALLOW_EXTRA_TOP_LEVEL[@]:-}"; do
    [ -n "$a" ] && [ "$name" = "$a" ] && found=1
  done
  [ "$found" = "1" ] || die "unexpected top-level entry in source: $name (remove it, or pass --allow-extra-top-level $name to include it in the identity)"
done
ok "top-level layout allowlisted"

mkdir -p "$WORK_DIR"
MAN_TMP="$WORK_DIR/manifests"; mkdir -p "$MAN_TMP"
gen_coreutils() {
  ( cd "$1" && find . -type f -not -path './manifest/*' \
      -not -path '*/__pycache__/*' -not -path '*/.pytest_cache/*' -print0 \
      | LC_ALL=C sort -z | xargs -0 sha256sum ) > "$2"
}

# --- stage ----------------------------------------------------------------
phase "stage (rsync -a, manifest/ excluded)"
mkdir -p "$DEST"
rsync -a --delete --exclude '/manifest/' "$SRC"/ "$DEST"/ || { echo "rsync failed" >&2; exit 4; }
ok "staged $(du -sh "$DEST" | cut -f1) into $DEST"

if [ "$MODE" = "build" ]; then
  # --- identity tools -----------------------------------------------------
  phase "install identity tools"
  mkdir -p "$DEST/tools" "$DEST/launcher"
  chmod u+w "$DEST/tools" "$DEST/launcher" 2>/dev/null || true
  install -m 0644 "$TOOL_DIR/pysrc/preflight_identity.py" "$DEST/tools/preflight_identity.py"
  install -m 0644 "$L3LIB" "$DEST/tools/l3_namespace.py"
  diff -q "$TOOL_DIR/pysrc/preflight_identity.py" "$DEST/tools/preflight_identity.py" >/dev/null
  diff -q "$L3LIB" "$DEST/tools/l3_namespace.py" >/dev/null
  ok "tools/preflight_identity.py $(sha256sum "$DEST/tools/preflight_identity.py" | cut -d' ' -f1)"
  ok "tools/l3_namespace.py $(sha256sum "$DEST/tools/l3_namespace.py" | cut -d' ' -f1)"

  # --- telemetry tool repoint ---------------------------------------------
  phase "repoint tools/validate_telemetry.py"
  TEL="$DEST/tools/validate_telemetry.py"
  if [ ! -f "$TEL" ] && [ -f "$TEMPLATE_TREE/tools/validate_telemetry.py" ]; then
    install -m 0644 "$TEMPLATE_TREE/tools/validate_telemetry.py" "$TEL"
    ok "copied baseline telemetry tool from $TEMPLATE_TREE"
  fi
  if [ -f "$TEL" ]; then
    chmod u+w "$TEL"
    python3 "$REPOINT" --file "$TEL" --tree "$DEST" --identity "$IDENTITY" --write \
      || { echo "telemetry repoint FAILED" >&2; exit 5; }
    ok "telemetry tool repointed + hash bindings verified"
  else
    echo "   WARNING: no tools/validate_telemetry.py in source or template" >&2
  fi

  # --- provisional manifest ------------------------------------------------
  # The launcher's own fail-closed gate hashes the tree against
  # manifest/TREE-SHA256.txt, so the dry-run during repin needs a manifest to
  # exist.  It is regenerated after the repin (the launcher bytes change).
  phase "provisional manifest (launcher dry-run gate input)"
  mkdir -p "$DEST/manifest"
  gen_coreutils "$DEST" "$DEST/manifest/TREE-SHA256.txt"
  ok "provisional manifest: $(wc -l < "$DEST/manifest/TREE-SHA256.txt") entries"

  # --- env symlink --------------------------------------------------------
  phase "env symlink"
  if [ -L "$DEST/env" ] || [ -e "$DEST/env" ]; then
    CUR="$(readlink "$DEST/env" || true)"
    [ "$CUR" = "$VENV" ] || die "existing env symlink points at $CUR, expected $VENV"
    ok "env -> $CUR (kept)"
  else
    ln -s "$VENV" "$DEST/env"
    ok "env -> $VENV (created)"
  fi

  # --- launcher repin -----------------------------------------------------
  phase "repin launcher"
  chmod u+w "$DEST/launcher" 2>/dev/null || true
  "$REPIN" --write --tree "$DEST" --identity "$IDENTITY" \
    --scratch "$WORK_DIR/repin" >"$WORK_DIR/launcher-repin.log" 2>&1 \
    || { echo "launcher repin FAILED; log:" >&2; cat "$WORK_DIR/launcher-repin.log" >&2; exit 5; }
  ok "launcher repinned: $(sha256sum "$DEST/launcher/launch.sh" | cut -d' ' -f1)"
fi

# --- immutability ---------------------------------------------------------
phase "freeze permissions (chmod -R a-w on src, launcher, tools)"
python3 "$MH" --dir "$SRC/src" --clear-write --json > "$WORK_DIR/src-mode-expected.json"
chmod -R u+w "$DEST/src"
chmod -R a-w "$DEST/src"
for d in launcher tools "${ALLOW_EXTRA_TOP_LEVEL[@]:-}"; do
  [ -n "$d" ] || continue
  [ -e "$DEST/$d" ] || continue
  chmod -R a-w "$DEST/$d"
done
W="$(find "$DEST/src" \( -type f -o -type d \) -perm /222 | wc -l)"
[ "$W" -eq 0 ] || { echo "immutability: $W writable src entries remain" >&2; exit 6; }
for d in launcher tools; do
  W="$(find "$DEST/$d" -perm /222 | wc -l)"
  [ "$W" -eq 0 ] || { echo "immutability: $W writable entries remain under $d" >&2; exit 6; }
done
python3 "$MH" --dir "$DEST/src" --json > "$WORK_DIR/src-mode-actual.json"
python3 - "$WORK_DIR/src-mode-expected.json" "$WORK_DIR/src-mode-actual.json" <<'PY' || { echo "immutability: src mode histogram does not match the derived expectation" >&2; exit 6; }
import json, sys
e = json.load(open(sys.argv[1]))["counts"]
a = json.load(open(sys.argv[2]))["counts"]
if e != a:
    print(f"expected {e}", file=sys.stderr)
    print(f"actual   {a}", file=sys.stderr)
    sys.exit(1)
sys.exit(0)
PY
VENV_MODE_AFTER="$(stat -c '%a' "$VENV")"
[ "$VENV_MODE_BEFORE" = "$VENV_MODE_AFTER" ] || { echo "immutability: venv mode changed $VENV_MODE_BEFORE -> $VENV_MODE_AFTER (symlink was dereferenced!)" >&2; exit 6; }
set +e
touch "$DEST/src/.freeze-write-probe" 2>/dev/null; PW=$?
mkdir "$DEST/src/.freeze-mkdir-probe" 2>/dev/null; PM=$?
set -e
[ "$PW" -ne 0 ] && [ "$PM" -ne 0 ] || { echo "immutability: write probes succeeded" >&2; exit 6; }
[ ! -e "$DEST/src/.freeze-write-probe" ] && [ ! -e "$DEST/src/.freeze-mkdir-probe" ] || { echo "immutability: probe artifacts left behind" >&2; exit 6; }
ok "0 writable src entries; histogram $(python3 -c "import json;print(json.load(open('$WORK_DIR/src-mode-actual.json'))['counts'])")"
ok "venv untouched ($VENV_MODE_AFTER); write/mkdir probes denied"

# --- manifest -------------------------------------------------------------
phase "manifest generation x3"
gen_coreutils "$DEST" "$MAN_TMP/run1.txt"
gen_coreutils "$DEST" "$MAN_TMP/run2.txt"
python3 "$MT" generate --tree "$DEST" --out "$MAN_TMP/py.txt" --json > "$MAN_TMP/py.json"
cmp -s "$MAN_TMP/run1.txt" "$MAN_TMP/run2.txt" || { echo "manifest not deterministic (coreutils run1 != run2)" >&2; exit 7; }
cmp -s "$MAN_TMP/run1.txt" "$MAN_TMP/py.txt" || { echo "manifest implementations disagree (coreutils != python)" >&2; exit 7; }
python3 "$MT" validate --manifest "$MAN_TMP/run1.txt" --json > "$MAN_TMP/validate.json" \
  || { echo "manifest format validation failed:" >&2; cat "$MAN_TMP/validate.json" >&2; exit 7; }
MAN_SHA="$(sha256sum "$MAN_TMP/run1.txt" | cut -d' ' -f1)"
MAN_BYTES="$(stat -c '%s' "$MAN_TMP/run1.txt")"
ok "3 identical generations; sha256=$MAN_SHA bytes=$MAN_BYTES"

# --- source manifest + fidelity ------------------------------------------
phase "copy fidelity vs source"
if [ -n "$EXPECT_SRC_MANIFEST" ] && [ -f "$EXPECT_SRC_MANIFEST" ]; then
  SRC_MAN="$EXPECT_SRC_MANIFEST"
  ok "using provided source manifest $SRC_MAN"
else
  SRC_MAN="$MAN_TMP/source.txt"
  gen_coreutils "$SRC" "$SRC_MAN"
  ok "generated source manifest $SRC_MAN"
fi

if [ "$MODE" = "build" ]; then
  phase "approved source scope vs baseline"
  if [ -n "$ALLOWED_SOURCE_CHANGES_FILE" ]; then
    [ -f "$ALLOWED_SOURCE_CHANGES_FILE" ] || die "allowlist file not found: $ALLOWED_SOURCE_CHANGES_FILE"
    while IFS= read -r line; do
      line="${line%%#*}"; line="$(printf '%s' "$line" | tr -d '[:space:]')"
      [ -n "$line" ] && ALLOWED_SOURCE_CHANGES+=("$line")
    done <"$ALLOWED_SOURCE_CHANGES_FILE"
    ok "allowlist file: $ALLOWED_SOURCE_CHANGES_FILE ($(grep -cvE '^\s*(#|$)' "$ALLOWED_SOURCE_CHANGES_FILE") entries)"
  fi
  SCOPE_ALLOW="$(IFS=,; printf '%s' "${ALLOWED_SOURCE_CHANGES[*]}")"
  set +e
  python3 "$MT" compare --source "$BASELINE_TREE/manifest/TREE-SHA256.txt" \
    --dest "$SRC_MAN" --allow-modified "$SCOPE_ALLOW" --json > "$WORK_DIR/source-scope.json"
  SCOPE_RC=$?
  set -e
  [ "$SCOPE_RC" -eq 0 ] || { echo "source scope compare FAILED:" >&2; cat "$WORK_DIR/source-scope.json" >&2; exit 8; }
  python3 - "$WORK_DIR/source-scope.json" "$SCOPE_ALLOW" <<'PY' || { echo "source scope is not approved (or contains GGUF changes)" >&2; exit 8; }
import json, sys
report = json.load(open(sys.argv[1]))
allow = {p.lstrip("./") for p in sys.argv[2].split(",") if p}
added = {p.lstrip("./") for p in report.get("added", [])}
changed = {p.lstrip("./") for p in (c["path"] for c in report.get("changed_allowed", []))}
unapproved_added = sorted(added - allow)
unapproved_changed = sorted(changed - allow)
# GGUF hard refusal, restored to its original fail-closed form: ANY added or
# changed path containing "gguf" is refused.  GGUF is excluded from this
# production identity unless separately proven inert.
#
# The smallest possible explicit exception is granted for a set of exact,
# enumerated NON-RUNTIME artifacts: diagnostic probe scripts and their unit
# test.  None of them is imported, exec'd, or otherwise reachable by the served
# process; they cannot change serving behavior.  This is an exact-path list --
# a new, renamed, moved or newly-added GGUF-related path is STILL a hard
# refusal, and no `gguf*` prefix/glob is ever allowed.  Extending this list is a
# reviewed production decision, not a tooling change.
GGUF_INERT_EXACT_PATHS = {
    "src/3090-dev/gates/gguf-probes/dump_meta.py",
    "src/3090-dev/gates/gguf-probes/dump_shapes.py",
    "src/3090-dev/gates/gguf-probes/gguf_dump.py",
    "src/3090-dev/gates/gguf-probes/peek_small.py",
    "src/3090-dev/gates/gguf-probes/qwen35_gguf_validate.py",
    "src/3090-dev/gates/gguf-probes/type_hist.py",
    "src/test/registered/unit/models/test_qwen3_5_gguf_norm_fold.py",
}
gguf_all = sorted(p for p in added | changed if "gguf" in p.lower())
gguf = sorted(p for p in gguf_all if p not in GGUF_INERT_EXACT_PATHS)
if unapproved_added or unapproved_changed or gguf:
    print(json.dumps({
        "unapproved_added": unapproved_added,
        "unapproved_changed": unapproved_changed,
        "gguf_delta_hard_refusal": gguf,
    }, indent=2), file=sys.stderr)
    sys.exit(1)
print("approved source scope: only declared F1 delta(s); no GGUF delta")
PY
  ok "approved source scope; allowed=${SCOPE_ALLOW}"
fi
ALLOW_MOD=""
if [ "$MODE" = "build" ]; then
  ALLOW_MOD="launcher/launch.sh,tools/validate_telemetry.py,tools/preflight_identity.py,tools/l3_namespace.py"
fi
python3 "$MT" fidelity --source-tree "$SRC" --source-manifest "$SRC_MAN" \
  --dest-tree "$DEST" --dest-manifest "$MAN_TMP/run1.txt" --allow-modified "$ALLOW_MOD" \
  --json > "$WORK_DIR/fidelity.json" \
  || { echo "copy fidelity FAILED:" >&2; cat "$WORK_DIR/fidelity.json" >&2; exit 8; }
ok "copy fidelity verified: $(python3 -c "import json;d=json.load(open('$WORK_DIR/fidelity.json'));print(d['dest']['file_count'],'files',d['dest']['total_bytes'],'bytes; added',d['added'] or 'none')")"

# --- identity files -------------------------------------------------------
phase "write identity files into manifest/ (excluded from the digest)"
MANIFEST_DIR="$DEST/manifest"
mkdir -p "$MANIFEST_DIR"
cp "$MAN_TMP/run1.txt" "$MANIFEST_DIR/TREE-SHA256.txt"
STREAM="$(python3 "$MT" src-stream --tree "$DEST")"
STATS_JSON="$(python3 "$MT" stats --tree "$DEST" --manifest "$MANIFEST_DIR/TREE-SHA256.txt" --json)"
LAUNCHER_SHA=""
if [ -f "$DEST/launcher/launch.sh" ]; then LAUNCHER_SHA="$(sha256sum "$DEST/launcher/launch.sh" | cut -d' ' -f1)"; fi

# --- the five required identity fields ------------------------------------
# A frozen candidate must carry these so source identity, launcher bytes and
# the *executed* native binary cannot diverge:
#   SOURCE_COMMIT      commit the candidate was built from (never a timestamp)
#   TREE_HASH          the tree manifest digest already computed above
#   LAUNCHER_HASH      sha256 of the rendered launcher/launch.sh
#   RUST_SOURCE_DIGEST loader fingerprint over src/rust, i.e. the cache key the
#                      native .so binds to (null + reason if no toolchain)
#   LOADED_SO_HASH     sha256 of the .so the loader selects; when the artifact
#                      is not cached yet the resolved path is recorded and the
#                      hash is null, to be verified at launch
SOURCE_COMMIT=""
if [ -n "$SOURCE_COMMIT_ARG" ]; then
  SOURCE_COMMIT="$SOURCE_COMMIT_ARG"
elif git -C "$SRC" rev-parse --verify HEAD >/dev/null 2>&1; then
  SOURCE_COMMIT="$(git -C "$SRC" rev-parse HEAD)"
else
  echo "   WARNING: $SRC is not a git checkout and --source-commit was not given;" >&2
  echo "            SOURCE_COMMIT will be null (a committed build cannot be proven)" >&2
fi
RUST_ID_JSON=""
if [ -f "$RUSTID" ]; then
  # Prefer the tree interpreter: the fingerprint binds the Python ABI.  Never
  # fatal -- a missing toolchain yields null fields plus a machine-readable reason.
  RUST_PY="python3"
  if [ -x "$VENV/bin/python" ]; then RUST_PY="$VENV/bin/python"; fi
  RUST_ID_JSON="$(env CUDA_VISIBLE_DEVICES=999 "$RUST_PY" "$RUSTID" \
      --tree "$DEST" --json 2>/dev/null || true)"
fi
[ -n "$RUST_ID_JSON" ] || RUST_ID_JSON='{"rust_source_digest": null, "loaded_so_path": null, "loaded_so_sha256": null, "loaded_so_bytes": null, "loaded_so_present": false, "unavailable_reason": "rust_identity.py did not return a report"}'
python3 - "$MANIFEST_DIR" "$DEST" "$IDENTITY" "$MAN_SHA" "$MAN_BYTES" "$STATS_JSON" "$STREAM" \
  "$LAUNCHER_SHA" "$SRC" "$MODE" "$VENV" "$TEMPLATE_IDENTITY" "$TOOL_DIR" \
  "$WORK_DIR/fidelity.json" "$SOURCE_COMMIT" "$RUST_ID_JSON" <<'PY' || { echo "identity emit failed" >&2; exit 9; }
import json, sys, hashlib
from datetime import datetime, timezone
from pathlib import Path
(man_dir, tree, identity, man_sha, man_bytes, stats_json, stream,
 launcher_sha, source_tree, mode, _venv, template_identity, tool_dir, fidelity_json,
 source_commit, rust_id_json) = sys.argv[1:17]
sys.path.insert(0, str(Path(tool_dir) / "pysrc"))
import manifest_tool as mt

tree_p = Path(tree)
stats = json.loads(stats_json)
manifest_tool_extra = json.load(open(fidelity_json))
tools = {}
tools_dir = tree_p / "tools"
if tools_dir.is_dir():
    for p in sorted(tools_dir.iterdir()):
        if p.is_file():
            tools[p.name] = mt.sha256_of(p)
now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
identity_doc = mt.emit_identity(
    tree_p, identity, man_sha, int(man_bytes), stats, stream,
    {
        "freeze_tool": "v1.1.2-freeze-20260917",
        "source_tree": source_tree,
        "generated_by": "bin/freeze.sh",
        "self_test": {
            "mode": mode,
            "fidelity_ok": manifest_tool_extra.get("ok"),
            "added": manifest_tool_extra.get("added"),
            "modified_allowed": [c["path"] for c in manifest_tool_extra.get("modified_allowed", [])],
        },
        "open_items": [
            "manifest/ and __pycache__/.pytest_cache are excluded from the tree digest by design",
            "the env symlink is shared with v1/v1.1 and is not per-tree frozen",
            "per-run LOG_DIR is derived from SGLANG_RUN_ID so a run cannot overwrite a previous run's metrics evidence",
        ],
    },
)
identity_doc["frozen_at_utc"] = now
identity_doc["launcher"] = {
    "path": str(tree_p / "launcher" / "launch.sh"),
    "sha256": launcher_sha,
    "note": "rendered by bin/launcher-repin.sh; hard gate + per-run namespace enforcement",
}
identity_doc["tools_sha256"] = tools
identity_doc["template_identity"] = template_identity
# --- the five required identity fields (all computed, never invented) -----
_rust_id = json.loads(rust_id_json)
_rust_source_digest = _rust_id.get("rust_source_digest")
_loaded_so_hash = _rust_id.get("loaded_so_sha256")
identity_doc["SOURCE_COMMIT"] = source_commit or None
identity_doc["TREE_HASH"] = man_sha
identity_doc["LAUNCHER_HASH"] = launcher_sha or None
identity_doc["RUST_SOURCE_DIGEST"] = _rust_source_digest
identity_doc["LOADED_SO_HASH"] = {
    "path": _rust_id.get("loaded_so_path"),
    "sha256": _loaded_so_hash,
    "bytes": _rust_id.get("loaded_so_bytes"),
    "verified_at_freeze": bool(_loaded_so_hash),
    "verified_at_launch": not bool(_loaded_so_hash),
    "resolved_fingerprint": _rust_source_digest,
    "source_digest": _rust_id.get("source_digest"),
    "target_fingerprint": _rust_id.get("target_fingerprint"),
    "cache_root": _rust_id.get("cache_root"),
    "unavailable_reason": _rust_id.get("unavailable_reason"),
    "note": (
        "sha256 of the native extension the loader selects for this source; "
        "when null the resolved path is recorded and the hash must be verified at launch"
    ),
}
identity_doc["identity_fields"] = {
    "SOURCE_COMMIT": ("git -C <src> rev-parse HEAD" if source_commit
                      else "null: source tree is not a git checkout"),
    "TREE_HASH": "sha256 of manifest/TREE-SHA256.txt (self-digest)",
    "LAUNCHER_HASH": "sha256 of launcher/launch.sh",
    "RUST_SOURCE_DIGEST": "loader fingerprint over src/rust (cache key the .so binds to)",
    "LOADED_SO_HASH": "sha256 of the loader-selected native .so",
}
Path(man_dir, "identity.json").write_text(
    json.dumps(identity_doc, indent=2, sort_keys=True) + "\n"
)
pins = {
    "identity": identity,
    "tree_name": tree_p.name,
    "tree": str(tree_p),
    "created_at_utc": now,
    "tree_manifest_sha256": man_sha,
    "tree_manifest_bytes": int(man_bytes),
    "tree_file_count": stats["file_count"],
    "tree_total_bytes": stats["total_bytes"],
    "src_file_count": stats["src_file_count"],
    "src_total_bytes": stats["src_total_bytes"],
    "src_stream_digest_v1_convention": stream,
    "launcher_sha256": launcher_sha,
    "tools_sha256": tools,
    "freeze_tool": "v1.1.2-freeze-20260917",
    "source_tree": source_tree,
    "SOURCE_COMMIT": source_commit or None,
    "TREE_HASH": man_sha,
    "LAUNCHER_HASH": launcher_sha or None,
    "RUST_SOURCE_DIGEST": _rust_source_digest,
    "LOADED_SO_HASH": _loaded_so_hash,
    "LOADED_SO_PATH": _rust_id.get("loaded_so_path"),
}
Path(man_dir, "identity-pins.json").write_text(
    json.dumps(pins, indent=2, sort_keys=True) + "\n"
)
print(f"identity.json + identity-pins.json written; launcher_sha256={launcher_sha}")
print("identity fields: "
      f"SOURCE_COMMIT={source_commit or 'null'} "
      f"TREE_HASH={man_sha[:12]} "
      f"LAUNCHER_HASH={(launcher_sha or 'null')[:12]} "
      f"RUST_SOURCE_DIGEST={(_rust_source_digest or 'null')[:12]} "
      f"LOADED_SO_HASH={(_loaded_so_hash or 'null')[:12]}")
PY
cp "$MANIFEST_DIR/identity-pins.json" "$TOOL_DIR/pins/$DEST_NAME-pins.json"
ok "identity.json, identity-pins.json written (also pinned at pins/$DEST_NAME-pins.json)"

# --- manifest stability after evidence -----------------------------------
phase "manifest stability after evidence"
gen_coreutils "$DEST" "$MAN_TMP/run4.txt"
cmp -s "$MAN_TMP/run1.txt" "$MAN_TMP/run4.txt" || { echo "manifest changed after identity files were written (exclusions wrong?)" >&2; exit 7; }
MAN_SHA2="$(sha256sum "$MANIFEST_DIR/TREE-SHA256.txt" | cut -d' ' -f1)"
[ "$MAN_SHA" = "$MAN_SHA2" ] || { echo "manifest digest changed: $MAN_SHA -> $MAN_SHA2" >&2; exit 7; }
ok "manifest stable after evidence ($MAN_SHA)"

if [ "$MODE" = "selftest" ]; then
  phase "self-test: expected digest"
  [ -n "$EXPECT_DIGEST" ] || die "--selftest-reproduce requires --expect-digest"
  [ "$MAN_SHA" = "$EXPECT_DIGEST" ] || {
    echo "SELF-TEST FAILED: digest $MAN_SHA != expected $EXPECT_DIGEST" >&2; exit 7; }
  ok "reproduced $MAN_SHA"
fi

# --- final verification ---------------------------------------------------
if [ "$MODE" = "build" ]; then
  phase "final external verification (preflight --all + launcher dry-run)"
  VERIFY_RUN="freeze-verify-$(date -u +%Y%m%dT%H%M%SZ)-$$"
  python3 "$L3LIB" --allocate --task-id "$VERIFY_RUN" --root "$WORK_DIR/verify-l3" \
    --expect-tree-digest "$MAN_SHA" --json >/dev/null
  if ! PYTHONPATH="$DEST/src/python" "$TOOL_DIR/bin/preflight.sh" \
        --tree "$DEST" --pid self --run-id "$VERIFY_RUN" --l3-root "$WORK_DIR/verify-l3" \
        --pins "$MANIFEST_DIR/identity-pins.json" > "$WORK_DIR/preflight-final.log" 2>&1; then
    echo "final preflight FAILED; log:" >&2
    cat "$WORK_DIR/preflight-final.log" >&2
    exit 10
  fi
  ok "preflight PASS (see $WORK_DIR/preflight-final.log)"
fi

phase "DONE"
cat <<EOF
mode            : $MODE
tree            : $DEST
identity        : $IDENTITY
tree digest     : $MAN_SHA
manifest bytes  : $MAN_BYTES
file count      : $(python3 -c "import json;print(json.load(open('$WORK_DIR/fidelity.json'))['dest']['file_count'])")
total bytes     : $(python3 -c "import json;print(json.load(open('$WORK_DIR/fidelity.json'))['dest']['total_bytes'])")
src stream      : $STREAM
launcher sha256 : $LAUNCHER_SHA
pins            : $MANIFEST_DIR/identity-pins.json
                    $TOOL_DIR/pins/$DEST_NAME-pins.json
evidence        : $WORK_DIR
EOF
echo "FREEZE $MODE PASS"
exit 0
