#!/usr/bin/env bash
# negative-tests — prove the freeze/identity tooling FAILS CLOSED.
#
# Every case mutates only throwaway copies under selftest/.  Nothing under
# /opt/sglang, /data, /var/log or the source workspace is touched.
set -uo pipefail

TOOL_DIR="/tmp/opencode/v1.1.2-freeze-20260917"
CAND="$TOOL_DIR/selftest/candidate-selftest-1"
NEG_ROOT="$TOOL_DIR/selftest/negative"
NEG="$NEG_ROOT/tree"
SCRATCH="$NEG_ROOT/scratch"
IDENTITY="LOCAL-PROD-v1.1.2-SELFTEST-DO-NOT-PROMOTE"
V11_LAUNCHER="/opt/sglang/local-prod-v1.1-candidate/launcher/launch.sh"

PASS=0; FAIL=0
expect() { # expect <label> <expected_rc> <actual_rc>
  if [ "$2" = "$3" ]; then echo "  PASS  $1 (rc=$3)"; PASS=$((PASS+1));
  else echo "  FAIL  $1 (expected rc=$2, got $3)"; FAIL=$((FAIL+1)); fi
}

echo "== preparing throwaway mutation copy (rsync -a, ~2G) =="
rm -rf "$NEG_ROOT"; mkdir -p "$SCRATCH"
rsync -a "$CAND"/ "$NEG"/

alloc() { python3 "$TOOL_DIR/lib/l3_namespace.py" --allocate --task-id "$1" --root "$2" \
            --expect-tree-digest "$3" --json >/dev/null 2>&1; }
STREAM="$(python3 "$TOOL_DIR/lib/manifest_tool.py" src-stream --tree "$CAND")"

# ---------------------------------------------------------------- N1
echo "== N1: caller not bound (PYTHONPATH unset) -> preflight refuses =="
RUN=n1-run-$$
alloc "$RUN" "$SCRATCH/l3" "$STREAM"
out="$(env -i PATH=/usr/bin:/bin HOME="$HOME" "$TOOL_DIR/bin/preflight.sh" \
        --tree "$CAND" --pid self --run-id "$RUN" --l3-root "$SCRATCH/l3" 2>&1)"; rc=$?
expect "preflight unbound caller" 2 "$rc"

# ---------------------------------------------------------------- N2
echo "== N2: namespace never allocated -> preflight refuses =="
out="$(PYTHONPATH="$CAND/src/python" "$TOOL_DIR/bin/preflight.sh" \
        --tree "$CAND" --pid self --run-id "n2-never-allocated-$$" \
        --l3-root "$SCRATCH/l3" 2>&1)"; rc=$?
expect "unallocated namespace" 11 "$rc"

# ---------------------------------------------------------------- N3
echo "== N3: tampered external pin -> preflight refuses =="
python3 - <<'PY'
import json
p="/tmp/opencode/v1.1.2-freeze-20260917/selftest/negative/pins-tampered.json"
d=json.load(open("/tmp/opencode/v1.1.2-freeze-20260917/selftest/candidate-selftest-1/manifest/identity-pins.json"))
d["tree_manifest_sha256"]="0"*64
open(p,"w").write(json.dumps(d))
PY
RUN=n3-run-$$
alloc "$RUN" "$SCRATCH/l3" "$STREAM"
out="$(PYTHONPATH="$CAND/src/python" "$TOOL_DIR/bin/preflight.sh" \
        --tree "$CAND" --pid self --run-id "$RUN" --l3-root "$SCRATCH/l3" \
        --pins "$NEG_ROOT/pins-tampered.json" --no-launcher-check 2>&1)"; rc=$?
expect "tampered pin file" 10 "$rc"

# ---------------------------------------------------------------- N4
echo "== N4: stale launcher (rendered for v1.1) installed in the tree -> repin refuses =="
# render a launcher that binds the OLD tree, then install it into the throwaway copy
mkdir -p "$SCRATCH/stale"
sed -e "s#@@TREE@@#/opt/sglang/local-prod-v1.1-candidate#g" \
    -e "s#@@IDENTITY@@#LOCAL-PROD-v1.1#g" \
    -e "s#@@TREE_NAME@@#local-prod-v1.1-candidate#g" \
    -e "s#@@SRC_STREAM_SHA256@@#2c061dfcad8cc219e5c35b74e752a9694ce7a3747c8cf4542eff02463e77617e#g" \
    "$TOOL_DIR/templates/launch.sh.tmpl" > "$SCRATCH/stale/launch.sh"
grep -q '@@' "$SCRATCH/stale/launch.sh" && { echo "  FAIL  stale launcher render left tokens"; FAIL=$((FAIL+1)); }
chmod u+w "$NEG/launcher" "$NEG/launcher/launch.sh"
cp "$SCRATCH/stale/launch.sh" "$NEG/launcher/launch.sh"
chmod 0555 "$NEG/launcher/launch.sh"
out="$("$TOOL_DIR/bin/launcher-repin.sh" --verify-installed --tree "$NEG" \
        --identity "$IDENTITY" --run-id "n4-$$" 2>&1)"; rc=$?
expect "stale launcher rejected by repin --verify-installed" 22 "$rc"
echo "$out" | grep -q "foreign tree literal" && echo "         (reason: foreign tree literal detected)" || true

# ---------------------------------------------------------------- N5
echo "== N5: in-tree engine edited after repin -> preflight refuses =="
chmod u+w "$NEG/tools"
chmod u+w "$NEG/tools/preflight_identity.py"
echo "tampered" > "$NEG/tools/preflight_identity.py"
out="$(PYTHONPATH="$NEG/src/python" "$TOOL_DIR/bin/preflight.sh" \
        --tree "$NEG" --pid self --run-id "n5-$$" --l3-root "$SCRATCH/l3" \
        --pins "$NEG/manifest/identity-pins.json" 2>&1)"; rc=$?
expect "tampered in-tree engine" 14 "$rc"

# ---------------------------------------------------------------- N6
echo "== N6: one byte changed in src -> preflight refuses (manifest mismatch) =="
chmod u+w "$NEG/tools/preflight_identity.py"
cp "$CAND/tools/preflight_identity.py" "$NEG/tools/preflight_identity.py"
chmod u+w "$NEG/src/python/sglang/srt/mem_cache/storage/extent/extent_file_backend.py" 2>/dev/null || \
  chmod u+w "$(dirname "$NEG/src/python/sglang/srt/mem_cache/storage/extent/extent_file_backend.py")"
printf '\n# negative-test tamper\n' >> "$NEG/src/python/sglang/srt/mem_cache/storage/extent/extent_file_backend.py"
out="$(PYTHONPATH="$NEG/src/python" "$TOOL_DIR/bin/preflight.sh" \
        --tree "$NEG" --pid self --run-id "n6-$$" --l3-root "$SCRATCH/l3" \
        --pins "$NEG/manifest/identity-pins.json" 2>&1)"; rc=$?
expect "tampered src content" 3 "$rc"

# ---------------------------------------------------------------- N7
echo "== N7: repin refuses to bless a byte copy of an older launcher =="
out="$("$TOOL_DIR/bin/launcher-repin.sh" --write --tree "$CAND" --identity "$IDENTITY" \
        --scratch "$SCRATCH/bytecopy" \
        --v1-launcher "$SCRATCH/bytecopy/launch.sh.rendered" \
        --ref-launcher "$SCRATCH/bytecopy/launch.sh.rendered" 2>&1)"; rc=$?
expect "byte-copy guard" 23 "$rc"

# ---------------------------------------------------------------- N8
echo "== N8: launcher whose PYTHONPATH points at the WIP workspace -> dry-run gate refuses =="
# This is exactly the editable-install landmine.  The launcher must NOT pass.
sed 's#^export PYTHONPATH="\$SRC/python"$#export PYTHONPATH=/home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt/python#' \
    "$CAND/launcher/launch.sh" > "$SCRATCH/launch.wrongpath.sh"
chmod 0755 "$SCRATCH/launch.wrongpath.sh"
grep -q '^export PYTHONPATH=/home/ubuntu/workspaces' "$SCRATCH/launch.wrongpath.sh" \
  && echo "         (mutated PYTHONPATH present)" || echo "         (WARN: sed did not match)"
RUN=n8-run-$$
alloc "$RUN" "$SCRATCH/l3" "$STREAM"
out="$(env -i PATH=/usr/bin:/bin HOME="$HOME" SGLANG_RUN_ID="$RUN" \
        SGLANG_L3_ROOT="$SCRATCH/l3" SGLANG_LOG_DIR="$SCRATCH/n8-log" \
        SGLANG_LAUNCH_DRY_RUN=1 /bin/bash "$SCRATCH/launch.wrongpath.sh" 2>&1)"; rc=$?
if [ "$rc" -ne 0 ]; then echo "  PASS  wrong-PYTHONPATH dry-run refused (rc=$rc)"; PASS=$((PASS+1));
else echo "  FAIL  wrong-PYTHONPATH dry-run accepted"; FAIL=$((FAIL+1)); fi
echo "$out" | grep -q "resolved OUTSIDE the designated frozen tree" \
  && echo "         (reason: sglang resolved outside the designated tree)" || true

# ---------------------------------------------------------------- N9
echo "== N9: launcher with a stale src-stream pin -> dry-run gate refuses =="
sed 's#^EXPECTED_SRC_STREAM_SHA256="[0-9a-f]*"$#EXPECTED_SRC_STREAM_SHA256="0000000000000000000000000000000000000000000000000000000000000000"#' \
    "$CAND/launcher/launch.sh" > "$SCRATCH/launch.badpin.sh"
chmod 0755 "$SCRATCH/launch.badpin.sh"
RUN=n9-run-$$
alloc "$RUN" "$SCRATCH/l3" "$STREAM"
out="$(env -i PATH=/usr/bin:/bin HOME="$HOME" SGLANG_RUN_ID="$RUN" \
        SGLANG_L3_ROOT="$SCRATCH/l3" SGLANG_LOG_DIR="$SCRATCH/n9-log" \
        SGLANG_LAUNCH_DRY_RUN=1 /bin/bash "$SCRATCH/launch.badpin.sh" 2>&1)"; rc=$?
expect "stale src-stream pin" 12 "$rc"

# ---------------------------------------------------------------- N10
echo "== N10: missing tree manifest -> preflight refuses =="
mv "$NEG/manifest/TREE-SHA256.txt" "$NEG/manifest/TREE-SHA256.txt.aside"
out="$(PYTHONPATH="$NEG/src/python" "$TOOL_DIR/bin/preflight.sh" \
        --tree "$NEG" --pid self --run-id "n10-$$" --l3-root "$SCRATCH/l3" \
        --pins "$NEG/manifest/identity-pins.json" 2>&1)"; rc=$?
expect "missing manifest" 5 "$rc"
mv "$NEG/manifest/TREE-SHA256.txt.aside" "$NEG/manifest/TREE-SHA256.txt"

echo
echo "== negative-test summary: $PASS passed, $FAIL failed =="
[ "$FAIL" -eq 0 ]
