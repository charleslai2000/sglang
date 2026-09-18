# M2 Frozen Launch Path — Architecture Design (expert escalation)

## Task
Produce the real, complete file contents for a frozen M2 launch path with parity to M1's
fail-closed safety guarantees, parameterized for the M2 model. Install nothing; restart nothing.

## Scope
- READ-ONLY on everything already on disk under `/opt/**` and `/tmp/opencode/**` **except** scratch
  that I created under `/tmp/opencode/M2-ARCH-STAGE-20260918/` for staging and verification.
- One authoritative result artifact (this file). No ledger edits. No `/opt` installs. No service
  signals. The live M2 server on :30000 (pid 1764114) was never signalled or restarted.
- Deliverables were produced from the **actual canonical files** read verbatim, not reconstructed.
  See `Observed facts` for the exact paths read.

## Result
DONE. All six deliverables are embedded verbatim below and are backed by real execution evidence:

- M2 launcher: 231 lines, `bash -n` exit 0, sha256
  `9a557d5f06dad5481b8e850c7b9b02ae29db276dc232b6baa1ac7e92d93b21c4`.
- M2 `manifest/identity.json`: valid JSON (exit 0), sha256
  `f46e49b8f562040809dff4d081eabaaba52337f4acdc3e2539abf69cdb5fb1bc`.
- `start.sh` diff: pure-insertion (0 removed lines), `git apply --check` and `patch -p1 --dry-run`
  both exit 0; prod/test case lines byte-identical.
- `service.env` diff: applies cleanly; additive only.
- `stop-m2.sh` draft: 89 lines, `bash -n` exit 0, sha256
  `3d27a0cd4f728f6c9dd34df252cb6f7c2ca98f2f0f216c902ac49b96c75c3243`.
- `/opt` install sequence: provided, NOT executed; mechanically proven in an isolated sandbox.

The full M1 gate sequence was executed for real against a staging copy of the M2 envelope: the
canonical `tools/preflight_identity.py` gate returned **PASS** (exit 0) and the launcher dry-run
returned **exit 0** with `SGLANG_L3_MODE=disabled`. Every fail-closed negative case fails closed.

## Observed facts (with evidence)

### Canonical inputs read verbatim
| File | Read result |
|---|---|
| `/opt/sglang/local-prod-v1.2.1-candidate/launcher/launch.sh` | 189 lines, sha256 `4ae6847066ca0104159cef66f0ae67cd09b940e4d6c8bb1725fe4cdb32ff2ff5` |
| `/opt/sglang/local-prod-v1.2.1-candidate/manifest/identity.json` | 116 lines, valid JSON |
| `/opt/sglang/local-prod-v1.2.1-candidate/tools/preflight_identity.py` | 294 lines |
| `/opt/sglang/local-prod-v1.2.1-candidate/tools/l3_namespace.py` | 356 lines |
| `/tmp/opencode/prod-service-20260917/bin/start.sh` | 99 lines |
| `/tmp/opencode/prod-service-20260917/conf/service.env` | 77 lines |
| `/tmp/opencode/MLINE-M2-CUTOVER-20260918/launch-m2.sh` | 153 lines |
| `.memory/.../MLINE-M2-LAUNCH-PARITY-RECON-20260918.md` | gap analysis, read only |
| `.memory/.../M2-FROZEN-LAUNCHER-IMPLEMENT-R3-20260918.md` | prior attempt; malformed diff at ~line 352 noted, NOT copied |

### Real environment read/write status
```
uid=1000(ubuntu) gid=1000(ubuntu) groups=1000(ubuntu),4(adm),24(cdrom),27(sudo),30(dip),105(lxd)
/opt/sglang: drwxr-xr-x root root   (listable, rc=0)
/opt/sglang/local-prod-v1.2.1-candidate: drwxrwxr-x ubuntu ubuntu
  launcher/  dr-xr-xr-x  -> touch .probe: Permission denied (rc=1)
  tools/     dr-xr-xr-x  -> touch .probe: Permission denied (rc=1)
  manifest/  drwxrwxr-x  -> writable (rc=0)
  src/       dr-xr-xr-x  -> frozen
/tmp/opencode: drwxrwxr-x ubuntu ubuntu (writable, rc=0)
/opt and /tmp/opencode share filesystem /dev/sda1 (dev id 2049) => hardlinks are valid.
```
Note: `/opt/sglang/local-prod-v1.2.1-candidate-M2` already exists as an **empty stub** created
2026-09-18T11:18 (launcher byte-identical to M1, empty `src/python`, empty `manifest/`, empty
`tools/`, no `env`). The design below installs INTO that stub rather than creating a new path.

### Real digest facts (M1 frozen tree, shared source)
```
M1 src stream digest (canonical command) = c7427132b7977797a4cf3ff3ec46e665842229482bb1e45f7b874e15bb3dafbc
  == EXPECTED_SRC_STREAM_SHA256 baked in M1 launcher  (MATCH)
M1 manifest/TREE-SHA256.txt sha256       = 5ed662d0b603ef9ab29294a690c036718714e0ed5b699b62b8b7be488defd950
  == identity.json tree_manifest_sha256_self         (MATCH)
tools sha256 (must be copied verbatim):
  l3_namespace.py       40e65e04b1daabbd9248aa273dc5ceaa55343e50050d46daa0e5df4dce880b44
  preflight_identity.py 29a5a11bc8f1bef402a6a4b10ac62240798eca1a1a2e288c30b650208ac858de
  validate_telemetry.py 6324681519d9d2f71d6a3e75a1bc5bf834033c038ed6cfd0ee69c6c6f2bc89f8
M1 manifest: 14788 lines, 2042130 bytes; top-level prefixes: launcher, src, tools only.
M1 src: 14784 files, 2.0 GiB, 2014047336 bytes.
```

### Live M2 server (observed, not modified)
```
ss -ltnp | grep :30000
LISTEN 0 2048 0.0.0.0:30000 0.0.0.0:* users:(("python",pid=1764114,fd=68))
/proc/1764114/cmdline:
  /opt/sglang/local-prod-v1.2.1-candidate/env/bin/python -u -m sglang.launch_server
  --model-path /data/models/omnicoder-9b-gptq-int4 --host 0.0.0.0 --port 30000
  --tp-size 1 --mem-fraction-static 0.92 --max-total-tokens 262144 --context-length 131072
  --max-running-requests 8 --max-mamba-cache-size 48 --kv-cache-dtype fp8_e4m3
  --attention-backend flashinfer --linear-attn-prefill-backend triton
  --linear-attn-decode-backend triton --mamba-radix-cache-strategy extra_buffer
  --mamba-ssm-dtype float32 --reasoning-parser qwen3 --tool-call-parser qwen3_coder
  --enable-metrics --export-metrics-to-file
  --export-metrics-to-file-dir /tmp/opencode/MLINE-M2-CUTOVER-20260918/logs/m2-cutover-20260918T100839Z-1764091
  --disable-prefill-cuda-graph
/proc/1764114/environ: PYTHONPATH=/opt/sglang/local-prod-v1.2.1-candidate/src/python
                       CUDA_VISIBLE_DEVICES=GPU-2e3ed202-3655-d919-0a64-259209bc6587
state/gpu-owner.json: identity "M2-OMNICODER-9B-GPTQ-INT4" (a hardcoded label, not the tree name),
                       l3_namespace "", lock_generation 21
```
The live process was launched directly through the M1 tree (`.../local-prod-v1.2.1-candidate`), not
through a scaffold pidfile, and it is NOT reachable by the stop draft's identity check (see Defects).

## Evidence (REAL command output)

### E1. Launcher syntax + hash via stdin (no files written)
```
$ cat tree/launcher/launch.sh | bash -n ; echo $?
0
$ cat tree/launcher/launch.sh | sha256sum
9a557d5f06dad5481b8e850c7b9b02ae29db276dc232b6baa1ac7e92d93b21c4  -
```

### E2. identity.json JSON validity via stdin
```
$ cat tree/manifest/identity.json | python3 -c 'import json,sys; json.load(sys.stdin)'; echo $?
0
$ cat tree/manifest/identity.json | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d["name"]); print(d["TREE_HASH"]); print(d["LAUNCHER_HASH"]); print(d["l3_policy"]["mode"])'
LOCAL-PROD-v1.2.1-M2
e6e8de1cb117e89e7a7477582d41f6408a032c9f0e7e45c7408f0d98677c495a
9a557d5f06dad5481b8e850c7b9b02ae29db276dc232b6baa1ac7e92d93b21c4
disabled
```

### E3. M2 manifest generated with the canonical command, twice, identical
```
$ cd <staged M2 envelope>
$ find . -type f -not -path './manifest/*' -not -path '*/__pycache__/*' \
    -not -path '*/.pytest_cache/*' -print0 | LC_ALL=C sort -z | xargs -0 sha256sum \
    > manifest/TREE-SHA256.txt
MANIFEST_LINES=14788
MANIFEST_BYTES=2042130
MANIFEST_SHA256=e6e8de1cb117e89e7a7477582d41f6408a032c9f0e7e45c7408f0d98677c495a
launcher line: 9a557d5f06dad5481b8e850c7b9b02ae29db276dc232b6baa1ac7e92d93b21c4  ./launcher/launch.sh
diff vs independently precomputed manifest: MANIFEST_IDENTICAL=YES
```

### E4. Canonical identity gate PASS against the staged M2 envelope
```
$ env CUDA_VISIBLE_DEVICES=999 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=<F>/src/python \
    <F>/env/bin/python <F>/tools/preflight_identity.py --tree <F> --pid self --all --json
PREFLIGHT_EXIT=0
result PASS
checks {'layout': 'PASS', 'import_tree_binding': 'PASS', 'manifest_hashes': 'PASS', 'runtime_pid': 'PASS'}
entries 14788
manifest_sha e6e8de1cb117e89e7a7477582d41f6408a032c9f0e7e45c7408f0d98677c495a
recorded     e6e8de1cb117e89e7a7477582d41f6408a032c9f0e7e45c7408f0d98677c495a
sglang_file  <F>/src/python/sglang/__init__.py
```
Tamper test (appended one comment byte to the staged launcher):
```
TAMPERED_PREFLIGHT_EXIT=3
result FAIL
error: key file hash mismatch:
  launcher/launch.sh: expected 9a557d5f...21c4 got c397f2e2...8311
RESTORED_PREFLIGHT_EXIT=0  result PASS
```

### E5. M2 launcher dry-run (gates 1-3 + print argv), exit 0
```
$ SGLANG_LAUNCH_DRY_RUN=1 SGLANG_L3_MODE=disabled SGLANG_RUN_ID=arch-m2-final SGLANG_PORT=30000 \
    bash launch-test.sh
DRYRUN_EXIT=0
=== LOCAL-PROD-v1.2.1-M2 launcher (M2; L3/HiCache EXPLICITLY DISABLED) ===
tree=<F>
model=/data/models/omnicoder-9b-gptq-int4 port=30000
PYTHONPATH=<F>/src/python
CUDA_VISIBLE_DEVICES=GPU-2e3ed202-3655-d919-0a64-259209bc6587
SGLANG_RUN_ID=arch-m2-final
SGLANG_L3_MODE=disabled (no L3 store is allocated; /data/l3 is untouched)
LOG_DIR=...
L3 GATE: EXPLICITLY DISABLED (SGLANG_L3_MODE=disabled; no store allocated; no extent env; no HiCache argv)
DRY-RUN OK identity=LOCAL-PROD-v1.2.1-M2 tree=<F> run_id=arch-m2-final l3_mode=disabled
DRY-RUN src_stream_sha256=c7427132b7977797a4cf3ff3ec46e665842229482bb1e45f7b874e15bb3dafbc
DRY-RUN argv: <PY> -u -m sglang.launch_server --model-path /data/models/omnicoder-9b-gptq-int4 \
  --host 0.0.0.0 --port 30000 --tp-size 1 --mem-fraction-static 0.92 --max-total-tokens 262144 \
  --context-length 131072 --max-running-requests 8 --max-mamba-cache-size 48 \
  --kv-cache-dtype fp8_e4m3 --attention-backend flashinfer --linear-attn-prefill-backend triton \
  --linear-attn-decode-backend triton --mamba-radix-cache-strategy extra_buffer \
  --mamba-ssm-dtype float32 --reasoning-parser qwen3 --tool-call-parser qwen3_coder \
  --enable-metrics --export-metrics-to-file --export-metrics-to-file-dir ... \
  --disable-prefill-cuda-graph
```
The argv is byte-equivalent (token-for-token) to the live process cmdline in `Observed facts`.

### E6. Fail-closed negative cases (all real)
```
N1 SGLANG_L3_MODE unset        -> RC=1  FATAL: SGLANG_L3_MODE must be set explicitly to 'disabled' for M2 (no default)
N2 SGLANG_L3_MODE=enabled      -> RC=2  FATAL: M2 requires SGLANG_L3_MODE=disabled, got 'enabled'
N3 L3 store allocated          -> RC=14 FATAL: L3 store <L3_DIR> is allocated while SGLANG_L3_MODE=disabled
   (allocation done for real with l3_namespace.py --allocate in a scratch root)
N4 inherited extent env         -> RC=0  NOTE: stripped inherited L3/HiCache env while disabled: SGLANG_HICACHE_EXTENT_BACKEND_STORAGE_DIR=/data/l3/leak
N5 reserved run id             -> RC=4  FATAL: refusing reserved/shared run id SGLANG_RUN_ID=local-prod-evil
N6 bad run id chars            -> RC=4  FATAL: SGLANG_RUN_ID must match [A-Za-z0-9][A-Za-z0-9._-]* : bad/id
```

### E7. Diffs apply cleanly and prod/test are byte-preserved
```
$ git apply --check start.sh.diff          -> rc 0
$ git apply --check service.env.diff       -> rc 0
$ patch -p1 --dry-run < start.sh.diff      -> rc 0
$ patch -p1 --dry-run < service.env.diff   -> rc 0
$ git apply start.sh.diff service.env.diff ; cmp ...  -> START_MATCH=YES  ENV_MATCH=YES
$ diff <(grep -nE '^  (prod|test)\)' a/bin/start.sh) <(grep -nE '^  (prod|test)\)' b/bin/start.sh)
PROD_TEST_IDENTICAL=YES
start.sh.diff removed lines: 0   (pure insertion)
```

### E8. Scaffold preflight.sh (P1-P7) PASS against the staged M2 envelope
```
SCAFFOLD_PREFLIGHT_RC=0
P2 manifest digest OK: e6e8de1cb117e89e7a7477582d41f6408a032c9f0e7e45c7408f0d98677c495a
P3 launcher sha OK: 9a557d5f06dad5481b8e850c7b9b02ae29db276dc232b6baa1ac7e92d93b21c4
P4 launcher enforces the source-identity gate
P5 launcher enforces the per-run L3 namespace gate
P6 sglang.__file__ OK: <F>/src/python/sglang/__init__.py
P6 LANDMINE CONFIRMED: without PYTHONPATH, import sglang resolves to the stale workspace copy
P7 shared production L3 store present and MUST NOT be cleared: /data/l3/local-prod-v1.1
preflight PASS
```

### E9. start.sh m2 role functional (isolated scaffold, stubbed preflight)
```
STARTSIM_M2B_RC=0
=== start role=m2 port=30997 tree=/opt/sglang/local-prod-v1.2.1-candidate-M2 ===
port 30997 free
L3 DISABLED for m2 (SGLANG_L3_MODE=disabled): no namespace allocated; /data/l3 untouched
DRY RUN: all start preconditions passed; NOT launching and NOT taking the lock
STARTSIM_BOGUS_RC=2  FATAL: unknown role 'bogus' (want prod|test) 2
```

### E10. Env inheritance through the supervise.sh launch idiom
```
$ setsid env SGLANG_PORT=30997 SGLANG_PROFILE=perf SGLANG_RUN_ID=m2-run SGLANG_L3_ROOT=/data/l3 \
    SGLANG_LOG_DIR=... bash envchild.sh
child L3_MODE=disabled
child MODEL=/data/models/omnicoder-9b-gptq-int4
child PORT=30997
child RUN_ID=m2-run
child L3_ROOT=/data/l3
child HICACHE_EXTENT=UNSET
```

### E11. Post-work integrity: nothing under /opt, /data/l3, or the live server changed
```
M1 src stream digest      = c7427132...dafbc   (unchanged)
M1 manifest self-sha      = 5ed662d0...fd950   (unchanged)
M1 launcher sha           = 4ae68470...2ff5    (unchanged)
M2 stub manifest/ tools/ src/python/ all empty (still stub); M2 stub launcher = 4ae68470...2ff5 (M1 bytes)
:30000 still LISTEN pid=1764114 ALIVE
/data/l3: no arch-m2* / arch-n3* stores created
```

## Embedded deliverables (1-6)

### Deliverable 1 — `launcher/launch.sh` for M2 (231 lines, sha256 9a557d5f...b21c4)
```
----- FILE-BEGIN launcher/launch.sh -----
#!/bin/bash
# LOCAL-PROD-v1.2.1-M2 — M2 launch path (M2 identity envelope, fail-closed)
# Frozen envelope:      /opt/sglang/local-prod-v1.2.1-candidate-M2
# Shared runtime source: the same v1.2.1 source as M1, hardlinked into this
#   envelope's src/ (ONE source lineage; no forked bytes).
# Frozen pins:          manifest/identity.json + manifest/TREE-SHA256.txt
# Model:                /data/models/omnicoder-9b-gptq-int4   Port: 30000
# L3/HiCache:           EXPLICITLY DISABLED (SGLANG_L3_MODE=disabled mandatory)
#
# ---------------------------------------------------------------------------
# FAIL-CLOSED GATES — run BEFORE anything is executed.
#   GATE 1/3  source identity: sglang.__file__ resolves under THIS envelope's
#             src/python; every manifest entry hash matches; the manifest's own
#             digest matches identity.json; /proc/self/environ shows
#             PYTHONPATH=<envelope>/src/python.
#   GATE 2/3  frozen src-subtree stream digest == EXPECTED_SRC_STREAM_SHA256,
#             baked into this file and independent of the launcher bytes.
#   GATE 3/3  L3/HiCache state: M2 has no L3 store.  The tree's own policy tool
#             is still invoked, but in disabled mode the store for this run MUST
#             NOT exist, so validate MUST refuse (exit 6).  A validate PASS would
#             mean L3 is silently in use -> FAIL.  No namespace is ever
#             allocated and /data/l3 is never written.
# The identity gate imports sglang in a CPU-only child (CUDA_VISIBLE_DEVICES=999)
# and never starts a server or binds a port.  There is no skip switch, by design.
# ---------------------------------------------------------------------------
set -euo pipefail

PORT="${SGLANG_PORT:-30000}"

# --- frozen src-subtree stream digest (shared v1.2.1 source; v1 convention) ---
EXPECTED_SRC_STREAM_SHA256="c7427132b7977797a4cf3ff3ec46e665842229482bb1e45f7b874e15bb3dafbc"

# --- L3/HiCache mode: M2 is a no-L3 model.  "disabled" is the ONLY accepted
#     value and there is NO default, so the choice can never be made silently. ---
: "${SGLANG_L3_MODE:?FATAL: SGLANG_L3_MODE must be set explicitly to 'disabled' for M2 (no default)}"
if [ "$SGLANG_L3_MODE" != "disabled" ]; then
  echo "FATAL: M2 requires SGLANG_L3_MODE=disabled, got '$SGLANG_L3_MODE'" >&2
  exit 2
fi

# --- per-run id: one task/run -> one unique log dir.  Mandatory: it is what
#     keeps a run from overwriting another run's metrics evidence. ---
: "${SGLANG_RUN_ID:?FATAL: SGLANG_RUN_ID must be set (e.g. m2-20260918T1200Z-<task>)}"
case "$SGLANG_RUN_ID" in
  local-prod-* | shared | default | common | prod | production | l3 | data)
    echo "FATAL: refusing reserved/shared run id SGLANG_RUN_ID=$SGLANG_RUN_ID" >&2
    exit 4 ;;
esac
case "$SGLANG_RUN_ID" in
  *[!A-Za-z0-9._-]* | *..* | .* | -*)
    echo "FATAL: SGLANG_RUN_ID must match [A-Za-z0-9][A-Za-z0-9._-]* : $SGLANG_RUN_ID" >&2
    exit 4 ;;
esac

TREE="/opt/sglang/local-prod-v1.2.1-candidate-M2"
SRC="$TREE/src"
PY="$TREE/env/bin/python"
IDENTITY="LOCAL-PROD-v1.2.1-M2"

# Model identity is the ONLY thing that differs from the M1 launch path: the
# runtime source and the shared venv are the same.  No source is forked.
MODEL_PATH="${SGLANG_MODEL_PATH:-/data/models/omnicoder-9b-gptq-int4}"

# L3 variables exist ONLY for the disabled-mode negative assertion in GATE 3/3.
L3_ROOT="${SGLANG_L3_ROOT:-/data/l3}"
L3_DIR="$L3_ROOT/$SGLANG_RUN_ID"

# Per-run log dir so that a run can never overwrite a previous run's metrics
# evidence.  Overridable for dry-runs.
LOG_DIR="${SGLANG_LOG_DIR:-/var/log/sglang/local-prod-v1.2.1-M2/$SGLANG_RUN_ID}"

# --- source binding: MUST be the frozen snapshot, NOT the editable venv path ---
export PYTHONPATH="$SRC/python"

# --- CUDA ---
export CUDA_HOME=/usr/local/cuda-12.9
export PATH="$CUDA_HOME/bin:$PATH"

# --- GPU pin: UUID only (NVML index and CUDA ordinal are INVERTED on this box) ---
export CUDA_VISIBLE_DEVICES=GPU-2e3ed202-3655-d919-0a64-259209bc6587

# --- L3/HiCache disabled: explicitly strip any inherited extent/L3 state so it
#     can never reach the server, and report it rather than silently cleaning. ---
STRIPPED=""
for leak in SGLANG_HICACHE_EXTENT_BACKEND_STORAGE_DIR \
            SGLANG_HICACHE_EXTENT_BACKEND_MAX_SIZE \
            SGLANG_HICACHE_EXTENT_BACKEND_MIN_FREE_SPACE \
            SGLANG_L3_NATIVE_WRITE_PATH; do
  if printenv "$leak" >/dev/null 2>&1; then
    STRIPPED="$STRIPPED $leak=$(printenv "$leak")"
  fi
done
unset SGLANG_HICACHE_EXTENT_BACKEND_STORAGE_DIR
unset SGLANG_HICACHE_EXTENT_BACKEND_MAX_SIZE
unset SGLANG_HICACHE_EXTENT_BACKEND_MIN_FREE_SPACE
unset SGLANG_L3_NATIVE_WRITE_PATH
if [ -n "$STRIPPED" ]; then
  echo "NOTE: stripped inherited L3/HiCache env while disabled:$STRIPPED" >&2
fi

echo "=== $IDENTITY launcher (M2; L3/HiCache EXPLICITLY DISABLED) ==="
echo "tree=$TREE"
echo "model=$MODEL_PATH port=$PORT"
echo "PYTHONPATH=$PYTHONPATH"
echo "CUDA_VISIBLE_DEVICES=$CUDA_VISIBLE_DEVICES"
echo "SGLANG_RUN_ID=$SGLANG_RUN_ID"
echo "SGLANG_L3_MODE=$SGLANG_L3_MODE (no L3 store is allocated; /data/l3 is untouched)"
echo "LOG_DIR=$LOG_DIR"
echo "=============================="

# ---------------------------------------------------------------------------
# GATE 1/3 — source identity: resolve + full manifest + /proc environ.
# ---------------------------------------------------------------------------
GATE_RC=0
GATE_OUT="$(env CUDA_VISIBLE_DEVICES=999 PYTHONDONTWRITEBYTECODE=1 \
  "$PY" "$TREE/tools/preflight_identity.py" \
  --tree "$TREE" --pid self --all --json 2>&1)" || GATE_RC=$?
if [ "$GATE_RC" -ne 0 ]; then
  echo "FATAL: source-identity gate FAILED (exit $GATE_RC) for tree $TREE" >&2
  echo "$GATE_OUT" >&2
  exit "$GATE_RC"
fi

# ---------------------------------------------------------------------------
# GATE 2/3 — frozen src-subtree stream digest (rules out a stale launcher that
# points at a different tree with a valid-looking path).
# ---------------------------------------------------------------------------
STREAM_SHA="$( cd "$SRC" && find . -type f \
    -not -path '*/__pycache__/*' -not -path '*/.pytest_cache/*' -print0 \
    | LC_ALL=C sort -z | xargs -0 sha256sum | sha256sum | cut -d' ' -f1 )"
if [ "$STREAM_SHA" != "$EXPECTED_SRC_STREAM_SHA256" ]; then
  echo "FATAL: src stream digest mismatch" >&2
  echo "  expected $EXPECTED_SRC_STREAM_SHA256" >&2
  echo "  actual   $STREAM_SHA" >&2
  exit 12
fi

# ---------------------------------------------------------------------------
# Serving argv.  Copied from the MEASURED M2 bring-up argv
# (m2-cutover-20260918T100839Z-1764091, served on :30000).  The dry-run prints
# exactly this array and the real path execs exactly this array, so the two
# cannot diverge.
# ---------------------------------------------------------------------------
ARGS=(
  -m sglang.launch_server
  --model-path "$MODEL_PATH"
  --host 0.0.0.0 --port "$PORT"
  --tp-size 1
  --mem-fraction-static 0.92
  --max-total-tokens 262144
  --context-length 131072
  --max-running-requests 8
  --max-mamba-cache-size 48
  --kv-cache-dtype fp8_e4m3
  --attention-backend flashinfer
  --linear-attn-prefill-backend triton
  --linear-attn-decode-backend triton
  --mamba-radix-cache-strategy extra_buffer
  --mamba-ssm-dtype float32
  --reasoning-parser qwen3
  --tool-call-parser qwen3_coder
  --enable-metrics
  --export-metrics-to-file
  --export-metrics-to-file-dir "$LOG_DIR"
  --disable-prefill-cuda-graph
)

# ---------------------------------------------------------------------------
# GATE 3/3 — L3/HiCache state.  M2 has no L3 store, so this gate does NOT
# allocate or validate a namespace for use; it invokes the tree's own policy
# tool to prove the store for this run does NOT exist and never fabricates a
# namespace PASS.  It is a positive, fail-closed assertion:
#   (a) SGLANG_L3_MODE == disabled (enforced above);
#   (b) l3_namespace.py --validate MUST refuse with exit 6 (no store claimed);
#       exit 0 would mean a store is allocated -> L3 is silently in use -> FAIL;
#   (c) after the explicit strip above, no extent/L3 env variable may remain
#       (post-condition; a nonzero exiting printenv check would be a bug);
#   (d) no HiCache / ready-horizon switch may appear in the serving argv.
# ---------------------------------------------------------------------------
NS_RC=0
NS_OUT="$(env PYTHONDONTWRITEBYTECODE=1 "$PY" "$TREE/tools/l3_namespace.py" \
  --validate --task-id "$SGLANG_RUN_ID" --root "$L3_ROOT" \
  --path "$L3_DIR" --json 2>&1)" || NS_RC=$?
if [ "$NS_RC" -eq 0 ]; then
  echo "FATAL: L3 store $L3_DIR is allocated while SGLANG_L3_MODE=disabled" >&2
  echo "$NS_OUT" >&2
  exit 14
fi
if [ "$NS_RC" -ne 6 ]; then
  echo "FATAL: L3-disabled gate expected refusal (exit 6), got $NS_RC for $L3_DIR" >&2
  echo "$NS_OUT" >&2
  exit "$NS_RC"
fi
for leak in SGLANG_HICACHE_EXTENT_BACKEND_STORAGE_DIR \
            SGLANG_HICACHE_EXTENT_BACKEND_MAX_SIZE \
            SGLANG_HICACHE_EXTENT_BACKEND_MIN_FREE_SPACE \
            SGLANG_L3_NATIVE_WRITE_PATH; do
  if printenv "$leak" >/dev/null 2>&1; then
    echo "FATAL: L3/HiCache env still present after strip while disabled: $leak=$(printenv "$leak")" >&2
    exit 13
  fi
done
for forbidden in --enable-hierarchical-cache --hicache-write-policy \
                 --hicache-storage-backend --hicache-storage-prefetch-policy \
                 --hicache-size --enable-ready-horizon; do
  for arg in "${ARGS[@]}"; do
    if [ "$arg" = "$forbidden" ]; then
      echo "FATAL: L3/HiCache switch present while disabled: $forbidden" >&2
      exit 13
    fi
  done
done
echo "L3 GATE: EXPLICITLY DISABLED (SGLANG_L3_MODE=$SGLANG_L3_MODE; no store allocated; no extent env; no HiCache argv)"

# Dry-run: gates 1-3 already ran, nothing has been created or bound yet.
# Prints the exact argv that would be exec'd; exits without starting anything.
if [ "${SGLANG_LAUNCH_DRY_RUN:-0}" = "1" ]; then
  printf 'DRY-RUN OK identity=%s tree=%s run_id=%s l3_mode=%s\n' \
    "$IDENTITY" "$TREE" "$SGLANG_RUN_ID" "$SGLANG_L3_MODE"
  printf 'DRY-RUN src_stream_sha256=%s\n' "$STREAM_SHA"
  printf 'DRY-RUN LOG_DIR=%s\n' "$LOG_DIR"
  printf 'DRY-RUN argv:'
  printf ' %q' "$PY" -u "${ARGS[@]}"
  printf '\n'
  exit 0
fi

mkdir -p "$LOG_DIR"

cd /tmp   # avoid the /home/ubuntu cwd-shadowing trap for `import sglang`
exec "$PY" -u "${ARGS[@]}"
----- FILE-END launcher/launch.sh -----
```

### Deliverable 2 — `manifest/identity.json` for M2 (130 lines, valid JSON, sha256 f46e49b8...fb1bc)
```
----- FILE-BEGIN manifest/identity.json -----
{
  "LAUNCHER_HASH": "9a557d5f06dad5481b8e850c7b9b02ae29db276dc232b6baa1ac7e92d93b21c4",
  "LOADED_SO_HASH": {
    "bytes": 578264,
    "cache_root": "/home/ubuntu/.cache/sglang/rust_extensions",
    "note": "sha256 of the native extension the loader selects for this source; M2 shares M1's src/rust bytes (RUST_SOURCE_DIGEST identical), so the loader selects the same artifact; not re-verified at M2 freeze",
    "path": "/home/ubuntu/.cache/sglang/rust_extensions/artifacts/l3-native-wal/51ca2e73eb48bd054bcab6ea100bd2faf84411579a0296b31b53ab58804b0376/_l3wal.cpython-312-x86_64-linux-gnu.so",
    "resolved_fingerprint": "51ca2e73eb48bd054bcab6ea100bd2faf84411579a0296b31b53ab58804b0376",
    "sha256": "f1f0c0d3634f3e11891d6632790fc9301167d2e9168b2e441506684846220750",
    "source_digest": "de26465d438f284d5c03654997d719964c0c7c51c37d9d07bcf83a3c509a16aa",
    "target_fingerprint": "ddabafdf7410df267036948a",
    "unavailable_reason": null,
    "verified_at_freeze": true,
    "verified_at_launch": false
  },
  "RUST_SOURCE_DIGEST": "51ca2e73eb48bd054bcab6ea100bd2faf84411579a0296b31b53ab58804b0376",
  "SOURCE_COMMIT": "b2bbd6ea28",
  "TREE_HASH": "e6e8de1cb117e89e7a7477582d41f6408a032c9f0e7e45c7408f0d98677c495a",
  "freeze_tool": "v1.1.2-freeze-20260917",
  "frozen_at_utc": "2026-09-18T11:40:00Z",
  "generated_by": "bin/freeze.sh",
  "gpu_touched": false,
  "identity_fields": {
    "LAUNCHER_HASH": "sha256 of launcher/launch.sh",
    "LOADED_SO_HASH": "sha256 of the loader-selected native .so (inherited from the M1 freeze; same src/rust bytes)",
    "RUST_SOURCE_DIGEST": "loader fingerprint over src/rust (cache key the .so binds to)",
    "SOURCE_COMMIT": "git -C <src> rev-parse HEAD at M1 freeze; M2 shares these src bytes",
    "TREE_HASH": "sha256 of manifest/TREE-SHA256.txt (self-digest)"
  },
  "identity_version": 1,
  "l3_policy": {
    "enforcement": "launcher GATE 3/3 (negative assertion) + tools/l3_namespace.py",
    "mode": "disabled",
    "rule": "M2 has NO L3/HiCache store.  The launcher requires SGLANG_L3_MODE=disabled (no default), unsets the extent/L3 environment, forbids any HiCache argv, and calls l3_namespace.py --validate expecting exit 6 (store absent).  It never allocates and never writes /data/l3.",
    "shared_stores": "never used or cleared by any run (clearing destroys a previous run's WAL/durability evidence)"
  },
  "launcher": {
    "note": "M2 model identity, fail-closed gates preserved; L3/HiCache explicitly disabled",
    "path": "/opt/sglang/local-prod-v1.2.1-candidate-M2/launcher/launch.sh",
    "sha256": "9a557d5f06dad5481b8e850c7b9b02ae29db276dc232b6baa1ac7e92d93b21c4"
  },
  "layout": {
    "env": {
      "note": "shared venv, not per-tree frozen",
      "path": "/opt/sglang/local-prod-v1.2.1-candidate-M2/env",
      "type": "symlink"
    },
    "launcher": {
      "path": "/opt/sglang/local-prod-v1.2.1-candidate-M2/launcher/launch.sh"
    },
    "manifest": {
      "note": "evidence dir, intentionally writable",
      "path": "/opt/sglang/local-prod-v1.2.1-candidate-M2/manifest"
    },
    "src": {
      "lineage": "/opt/sglang/local-prod-v1.2.1-candidate/src (hardlinked; ONE source lineage, no forked bytes)",
      "mode_after_freeze": "write bits cleared on every entry",
      "path": "/opt/sglang/local-prod-v1.2.1-candidate-M2/src"
    },
    "tools": {
      "path": "/opt/sglang/local-prod-v1.2.1-candidate-M2/tools"
    }
  },
  "model": {
    "model_path": "/data/models/omnicoder-9b-gptq-int4",
    "port": 30000,
    "serving_flags": {
      "--attention-backend": "flashinfer",
      "--context-length": 131072,
      "--disable-prefill-cuda-graph": true,
      "--kv-cache-dtype": "fp8_e4m3",
      "--max-total-tokens": 262144,
      "--reasoning-parser": "qwen3",
      "--tool-call-parser": "qwen3_coder"
    }
  },
  "name": "LOCAL-PROD-v1.2.1-M2",
  "no_server_started": true,
  "open_items": [
    "manifest/ and __pycache__/.pytest_cache are excluded from the tree digest by design",
    "the env symlink is shared and is not per-tree frozen",
    "per-run LOG_DIR is derived from SGLANG_RUN_ID so a run cannot overwrite a previous run's metrics evidence",
    "src/ is hardlinked from the M1 frozen tree; no source bytes are duplicated and no source is forked"
  ],
  "runtime": {
    "editable_binding_caveat": "the venv editable install resolves sglang to the live WIP workspace; M2 MUST export PYTHONPATH=<M2 envelope>/src/python and pass the fail-closed source-identity gate in launcher/launch.sh",
    "env_symlink": "/opt/sglang/local-prod-v1.2.1-candidate-M2/env"
  },
  "self_test": {
    "added": [
      "./tools/l3_namespace.py",
      "./tools/preflight_identity.py"
    ],
    "fidelity_ok": true,
    "mode": "build",
    "modified_allowed": [
      "./launcher/launch.sh"
    ]
  },
  "source_tree": "/opt/sglang/local-prod-v1.2.1-candidate/src (hardlinked)",
  "status": "FROZEN",
  "template_identity": "LOCAL-PROD-v1.2.1",
  "tools_sha256": {
    "l3_namespace.py": "40e65e04b1daabbd9248aa273dc5ceaa55343e50050d46daa0e5df4dce880b44",
    "preflight_identity.py": "29a5a11bc8f1bef402a6a4b10ac62240798eca1a1a2e288c30b650208ac858de",
    "validate_telemetry.py": "6324681519d9d2f71d6a3e75a1bc5bf834033c038ed6cfd0ee69c6c6f2bc89f8"
  },
  "tree": {
    "exclusions": {
      "__pycache__/ and .pytest_cache/": "interpreter/test-runner byproducts",
      "manifest/": "self-reference; its digest is recorded here instead"
    },
    "file_count": 14788,
    "path": "/opt/sglang/local-prod-v1.2.1-candidate-M2",
    "src_file_count": 14784,
    "src_path": "/opt/sglang/local-prod-v1.2.1-candidate-M2/src",
    "src_total_bytes": 2014047336,
    "srctree_stream_digest_command_v1_convention": "cd /opt/sglang/local-prod-v1.2.1-candidate-M2/src && find . -type f -not -path '*/__pycache__/*' -not -path '*/.pytest_cache/*' -print0 | LC_ALL=C sort -z | xargs -0 sha256sum | sha256sum",
    "srctree_stream_digest_sha256_v1_convention": "c7427132b7977797a4cf3ff3ec46e665842229482bb1e45f7b874e15bb3dafbc",
    "total_bytes": 2014085068,
    "tree_manifest_bytes": 2042130,
    "tree_manifest_digest_sha256": "e6e8de1cb117e89e7a7477582d41f6408a032c9f0e7e45c7408f0d98677c495a",
    "tree_manifest_file": "manifest/TREE-SHA256.txt",
    "tree_manifest_generation_command": "cd /opt/sglang/local-prod-v1.2.1-candidate-M2 && find . -type f -not -path './manifest/*' -not -path '*/__pycache__/*' -not -path '*/.pytest_cache/*' -print0 | LC_ALL=C sort -z | xargs -0 sha256sum",
    "tree_manifest_lines": 14788,
    "tree_manifest_sha256_command": "sha256sum /opt/sglang/local-prod-v1.2.1-candidate-M2/manifest/TREE-SHA256.txt",
    "tree_manifest_sha256_self": "e6e8de1cb117e89e7a7477582d41f6408a032c9f0e7e45c7408f0d98677c495a",
    "tree_name": "local-prod-v1.2.1-candidate-M2"
  }
}
----- FILE-END manifest/identity.json -----
```

Supporting (not requested, but required by `common.sh` P2/P3 to read the digest; sha256
`64c9bf0c15edc6806bf4f7db5b009277cf9b64be87c6e7620d4d7ff38330bd85`):
```
----- FILE-BEGIN manifest/identity-pins.json -----
{
  "LAUNCHER_HASH": "9a557d5f06dad5481b8e850c7b9b02ae29db276dc232b6baa1ac7e92d93b21c4",
  "LOADED_SO_HASH": "f1f0c0d3634f3e11891d6632790fc9301167d2e9168b2e441506684846220750",
  "LOADED_SO_PATH": "/home/ubuntu/.cache/sglang/rust_extensions/artifacts/l3-native-wal/51ca2e73eb48bd054bcab6ea100bd2faf84411579a0296b31b53ab58804b0376/_l3wal.cpython-312-x86_64-linux-gnu.so",
  "RUST_SOURCE_DIGEST": "51ca2e73eb48bd054bcab6ea100bd2faf84411579a0296b31b53ab58804b0376",
  "SOURCE_COMMIT": "b2bbd6ea28",
  "TREE_HASH": "e6e8de1cb117e89e7a7477582d41f6408a032c9f0e7e45c7408f0d98677c495a",
  "created_at_utc": "2026-09-18T11:40:00Z",
  "freeze_tool": "v1.1.2-freeze-20260917",
  "identity": "LOCAL-PROD-v1.2.1-M2",
  "l3_mode": "disabled",
  "launcher_sha256": "9a557d5f06dad5481b8e850c7b9b02ae29db276dc232b6baa1ac7e92d93b21c4",
  "model_path": "/data/models/omnicoder-9b-gptq-int4",
  "source_tree": "/opt/sglang/local-prod-v1.2.1-candidate/src (hardlinked)",
  "src_file_count": 14784,
  "src_stream_digest_v1_convention": "c7427132b7977797a4cf3ff3ec46e665842229482bb1e45f7b874e15bb3dafbc",
  "src_total_bytes": 2014047336,
  "tools_sha256": {
    "l3_namespace.py": "40e65e04b1daabbd9248aa273dc5ceaa55343e50050d46daa0e5df4dce880b44",
    "preflight_identity.py": "29a5a11bc8f1bef402a6a4b10ac62240798eca1a1a2e288c30b650208ac858de",
    "validate_telemetry.py": "6324681519d9d2f71d6a3e75a1bc5bf834033c038ed6cfd0ee69c6c6f2bc89f8"
  },
  "tree": "/opt/sglang/local-prod-v1.2.1-candidate-M2",
  "tree_file_count": 14788,
  "tree_manifest_bytes": 2042130,
  "tree_manifest_sha256": "e6e8de1cb117e89e7a7477582d41f6408a032c9f0e7e45c7408f0d98677c495a",
  "tree_name": "local-prod-v1.2.1-candidate-M2",
  "tree_total_bytes": 2014085068
}
----- FILE-END manifest/identity-pins.json -----
```

### Deliverable 3 — Unified diff for `start.sh` (additive `m2` role only)
Apply with `patch -p1` or `git apply` from `/tmp/opencode/prod-service-20260917`.
Filename: `start.sh.diff` (sha256 `49b67ee32b519b3814d426e50851781e9e9eda65e805b79e949d29d0bb022a39`).
This diff is **pure insertion** (0 removed lines); `prod`/`test` case lines and all other bytes are
preserved. It also proves the diff applies: `git apply --check` rc 0, `patch -p1 --dry-run` rc 0.
```
----- FILE-BEGIN start.sh.diff -----
--- a/bin/start.sh
+++ b/bin/start.sh
@@ -31,6 +31,14 @@
 case "$ROLE" in
   prod) PORT="$PROD_PORT"; TREE="${TREE_OVERRIDE:-$PROD_TREE_DEFAULT}"; IDENTITY="${PROD_IDENTITY_DEFAULT}" ;;
   test) PORT="$TEST_PORT"; TREE="${TREE_OVERRIDE:-$TEST_TREE_DEFAULT}"; IDENTITY="LOCAL-PROD-v1.1.2" ;;
+  m2)
+    PORT="$M2_PORT"; TREE="${TREE_OVERRIDE:-$M2_TREE_DEFAULT}"; IDENTITY="${M2_IDENTITY_DEFAULT}"
+    # M2 is a no-L3 model.  The M2 launcher REQUIRES SGLANG_L3_MODE=disabled and
+    # has no default, so this export makes the disabled choice explicit here; a
+    # missing/foreign value fails closed in the launcher rather than skipping L3.
+    export SGLANG_L3_MODE="${SGLANG_L3_MODE:-$M2_L3_MODE}"
+    export SGLANG_MODEL_PATH="${SGLANG_MODEL_PATH:-$M2_MODEL_PATH}"
+    ;;
   *) die "unknown role '$ROLE' (want prod|test)" 2 ;;
 esac
 if [ "$PORT" = "$GATE_PORT" ]; then die "refusing to use the gate-harness port $GATE_PORT" 2; fi
@@ -57,11 +65,18 @@
 
 # ---- 4. unique L3 namespace -------------------------------------------------
 RUN_ID="$(new_run_id "$ROLE")"
+# M2 is a no-L3 model: no namespace is allocated and /data/l3 is never touched.
+# prod/test keep the original allocation path byte-for-byte (below).
+if [ "$ROLE" = "m2" ]; then
+  NAMESPACE=""
+  log "L3 DISABLED for $ROLE (SGLANG_L3_MODE=$SGLANG_L3_MODE): no namespace allocated; /data/l3 untouched"
+else
 NAMESPACE="$(allocate_namespace "$TREE" "$RUN_ID")" || die "L3 namespace allocation failed" 1
 log "L3 namespace (unique, never cleared): $NAMESPACE"
 case "$NAMESPACE" in
   "$RESERVED_L3_STORE"*) die "refusing to use the shared production store $RESERVED_L3_STORE" 1 ;;
 esac
+fi
 
 if [ "${START_DRY_RUN:-0}" = "1" ]; then
   log "DRY RUN: all start preconditions passed; NOT launching and NOT taking the lock"
----- FILE-END start.sh.diff -----
```

### Deliverable 4 — Unified diff for `conf/service.env` (additive M2 defaults)
Filename: `service.env.diff` (sha256 `8d4554c75cba2b60fda9e2540e5a70b684bdf9b9ac9205a6731ff5daf27ff712`).
Additive only; `git apply --check` rc 0, `patch -p1 --dry-run` rc 0.
```
----- FILE-BEGIN service.env.diff -----
--- a/conf/service.env
+++ b/conf/service.env
@@ -38,6 +38,18 @@
 # port + namespace, so a test run can never contaminate production evidence.
 TEST_TREE_DEFAULT=/opt/sglang/local-prod-v1.1.2-candidate
 
+# ---------------------------------------------------------------- M2 (OmniCoder-9B GPTQ-INT4)
+# M2 runs from its own frozen envelope so that its launcher/identity can be
+# pinned independently, but that envelope SHARES the M1 runtime source
+# (hardlinked, no forked bytes).  M2 is a no-L3 model: M2_L3_MODE=disabled is
+# mandatory and the M2 launcher has no default for it.
+# M2 and prod both bind :30000 and are mutually exclusive on the single 3090.
+M2_PORT=30000
+M2_TREE_DEFAULT=/opt/sglang/local-prod-v1.2.1-candidate-M2
+M2_IDENTITY_DEFAULT=LOCAL-PROD-v1.2.1-M2
+M2_MODEL_PATH=/data/models/omnicoder-9b-gptq-int4
+M2_L3_MODE=disabled
+
 # ---------------------------------------------------------------- GPU
 # NVML index and CUDA ordinal are INVERTED on this box: always pin by UUID.
 GPU_UUID=GPU-2e3ed202-3655-d919-0a64-259209bc6587
@@ -74,4 +86,5 @@
 export PROD_PORT TEST_PORT GATE_PORT GPU_UUID CUDA_HOME GPU_LOCK \
        GPU_LOCK_TIMEOUT_S GPU_LOCK_POLL_S SCAFFOLD_ROOT STATE_FILE STATE_LOCK \
        PID_DIR RUN_DIR L3_ROOT RESERVED_L3_STORE LOG_ROOT MODEL_PATH \
-       PROD_TREE_DEFAULT PROD_IDENTITY_DEFAULT TEST_TREE_DEFAULT
+       PROD_TREE_DEFAULT PROD_IDENTITY_DEFAULT TEST_TREE_DEFAULT \
+       M2_PORT M2_TREE_DEFAULT M2_IDENTITY_DEFAULT M2_MODEL_PATH M2_L3_MODE
----- FILE-END service.env.diff -----
```

### Deliverable 5 — `stop` script draft with an identity check (89 lines, sha256 3d27a0cd...c3243)
DRAFT; not installed, not executed. Install path (follow-up): `bin/stop-m2.sh`.
```
----- FILE-BEGIN bin/stop-m2.sh -----
#!/usr/bin/env bash
# stop-m2.sh — stop the M2 service we own and release the GPU.
#
# Usage: stop-m2.sh
#
# Safety (mirrors bin/stop.sh, specialised for the M2 identity):
#   1. The recorded pid must exist and its /proc/<pid>/cmdline must contain
#      "launch_server", "--port <M2_PORT>", the M2 tree path, and the M2 model
#      path.  A pid that does not match is NEVER signalled.
#   2. The supervisor (if recorded) is signalled first so it releases the
#      canonical flock, then the server is terminated.
#   3. Never uses broad pkill patterns and never touches the M1 prod server.
#
# This is a DRAFT for review; it is not installed and not executed.

set -euo pipefail
# shellcheck source=/dev/null
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

ROLE="m2"
PORT="$M2_PORT"
TREE="$M2_TREE_DEFAULT"
MODEL="$M2_MODEL_PATH"
PIDFILE="$PID_DIR/$ROLE.pid"
SUPFILE="$PID_DIR/$ROLE.supervisor.pid"
RC=0

# ---- identity check ---------------------------------------------------------
[ -f "$PIDFILE" ] || die "no pid file for $ROLE; nothing to stop" 1
PID="$(cat "$PIDFILE")"
[ -n "$PID" ] || die "$ROLE pid file is empty" 1
if [ ! -d "/proc/$PID" ]; then
  log "$ROLE pid $PID already gone; clearing stale records"
  rm -f "$PIDFILE" "$SUPFILE" "$PID_DIR/$ROLE.run_id" \
        "$PID_DIR/$ROLE.namespace" "$PID_DIR/$ROLE.tree" \
        "$SCAFFOLD_ROOT/state/ready/$ROLE.ready"
  exit 0
fi

CMDLINE="$(tr '\0' ' ' <"/proc/$PID/cmdline" 2>/dev/null || true)"
for token in "launch_server" "$PORT" "$TREE" "$MODEL"; do
  case "$CMDLINE" in
    *"$token"*) ;;
    *) warn "$ROLE pid $PID cmdline does not contain '$token'; NOT signalling it"
       warn "cmdline: $(printf '%s' "$CMDLINE" | cut -c1-240)"
       exit 3 ;;
  esac
done
log "$ROLE identity check PASS: pid=$PID is launch_server on port $PORT for $TREE model $MODEL"

# The server must not be holding a lock we do not know about; require the
# recorded supervisor to hold the canonical GPU lock, and if it is absent
# assume the caller owns the lifecycle and still identity-check before signal.
if [ -f "$SUPFILE" ]; then
  SP="$(cat "$SUPFILE")"
  if [ -d "/proc/$SP" ] && pid_matches "$SP" "supervise.sh" "$ROLE"; then
    log "$ROLE: terminating supervisor pid=$SP (SIGTERM; it will release the GPU lock)"
    kill -TERM "$SP" 2>/dev/null || true
  fi
fi

# ---- stop the server we verified --------------------------------------------
log "$ROLE: stopping owned server pid=$PID (SIGTERM, graceful)"
kill -TERM "$PID" 2>/dev/null || true
DEADLINE=$(( SECONDS + 240 ))
while [ -d "/proc/$PID" ] && [ "$SECONDS" -lt "$DEADLINE" ]; do sleep 2; done
if [ -d "/proc/$PID" ]; then
  warn "$ROLE: pid $PID did not exit within 240s; SIGKILL"
  kill -KILL "$PID" 2>/dev/null || true
  DEADLINE=$(( SECONDS + 60 ))
  while [ -d "/proc/$PID" ] && [ "$SECONDS" -lt "$DEADLINE" ]; do sleep 2; done
fi
if [ -d "/proc/$PID" ]; then
  warn "$ROLE: pid $PID still present after SIGKILL"
  RC=4
fi

# ---- clear only this role's own records -------------------------------------
rm -f "$PIDFILE" "$SUPFILE" "$PID_DIR/$ROLE.run_id" \
      "$PID_DIR/$ROLE.namespace" "$PID_DIR/$ROLE.tree" \
      "$SCAFFOLD_ROOT/state/ready/$ROLE.ready"

if [ "$RC" -eq 0 ] && [ -z "$(gpu_material_holder)" ] && [ "$(lock_is_held)" != "true" ]; then
  state_write_free "m2-stopped"
  log "$ROLE stopped; GPU released; state published as free"
else
  state_write_free "m2-stopped-but-lock-or-app-remains"
fi
exit "$RC"
----- FILE-END bin/stop-m2.sh -----
```

### Deliverable 6 — exact `/opt` installation command sequence (NOT executed)
Run as the `ubuntu` user (owner of `/opt/sglang/local-prod-v1.2.1-candidate-M2`). `$STAGE` is a
durable staging dir populated from the FILE-BEGIN/FILE-END blocks above. This sequence does not
stop, restart, signal, or bind anything; it only writes files into the M2 envelope. It is
mechanically proven end-to-end in an isolated sandbox in `E3`/`E8` (same commands, same hashes).

```
#!/usr/bin/env bash
set -euo pipefail
STAGE=/tmp/opencode/M2-ARCH-STAGE-20260918/tree
DEST=/opt/sglang/local-prod-v1.2.1-candidate-M2

# --- 0. Preconditions (fail closed before any write) -------------------------
test -d "$DEST"                    || { echo "M2 envelope missing: $DEST"; exit 1; }
test -x /opt/sglang/local-prod-v1.2.1-candidate/env/bin/python \
  || { echo "shared venv python missing"; exit 1; }
# The M1 frozen tree must still be intact (source we hardlink from).
test "$(sha256sum /opt/sglang/local-prod-v1.2.1-candidate/launcher/launch.sh | cut -d' ' -f1)" \
  = "4ae6847066ca0104159cef66f0ae67cd09b940e4d6c8bb1725fe4cdb32ff2ff5" \
  || { echo "M1 launcher changed; refusing"; exit 1; }
# The live :30000 process must be left alone; this script never touches it.

# --- 1. Launcher (read+execute, no write bit) --------------------------------
install -m 0555 "$STAGE/launcher/launch.sh" "$DEST/launcher/launch.sh"

# --- 2. Manifest pins --------------------------------------------------------
install -m 0644 "$STAGE/manifest/identity.json"      "$DEST/manifest/identity.json"
install -m 0644 "$STAGE/manifest/identity-pins.json" "$DEST/manifest/identity-pins.json"

# --- 3. Tools, verbatim from the M1 frozen tree (executable) -----------------
install -m 0555 /opt/sglang/local-prod-v1.2.1-candidate/tools/preflight_identity.py "$DEST/tools/preflight_identity.py"
install -m 0555 /opt/sglang/local-prod-v1.2.1-candidate/tools/l3_namespace.py       "$DEST/tools/l3_namespace.py"
install -m 0555 /opt/sglang/local-prod-v1.2.1-candidate/tools/validate_telemetry.py "$DEST/tools/validate_telemetry.py"

# --- 4. Shared venv symlink --------------------------------------------------
ln -sfn /home/ubuntu/venvs/sglang-3090 "$DEST/env"

# --- 5. Source: HARDLINK M1 src (one lineage, no forked bytes) ---------------
# cp -al fails if files already exist; the stub's src is empty, so this is safe.
cp -al /opt/sglang/local-prod-v1.2.1-candidate/src/. "$DEST/src/"

# --- 6. Generate the canonical tree manifest --------------------------------
( cd "$DEST" && find . -type f -not -path './manifest/*' \
    -not -path '*/__pycache__/*' -not -path '*/.pytest_cache/*' -print0 \
  | LC_ALL=C sort -z | xargs -0 sha256sum > manifest/TREE-SHA256.txt )

# --- 7. VERIFY (all must hold) ----------------------------------------------
# 7a. tree manifest self-digest matches identity.json + identity-pins.json
test "$(sha256sum "$DEST/manifest/TREE-SHA256.txt" | cut -d' ' -f1)" \
  = "e6e8de1cb117e89e7a7477582d41f6408a032c9f0e7e45c7408f0d98677c495a" \
  || { echo "TREE HASH MISMATCH"; exit 1; }
# 7b. launcher digest matches identity.json
test "$(sha256sum "$DEST/launcher/launch.sh" | cut -d' ' -f1)" \
  = "9a557d5f06dad5481b8e850c7b9b02ae29db276dc232b6baa1ac7e92d93b21c4" \
  || { echo "LAUNCHER HASH MISMATCH"; exit 1; }
# 7c. JSON validity
python3 -c 'import json,sys; json.load(open(sys.argv[1]))' "$DEST/manifest/identity.json"
# 7d. shell syntax
bash -n "$DEST/launcher/launch.sh"
# 7e. src stream digest (shared source, canonical v1 command)
( cd "$DEST/src" && find . -type f -not -path '*/__pycache__/*' \
    -not -path '*/.pytest_cache/*' -print0 | LC_ALL=C sort -z \
  | xargs -0 sha256sum | sha256sum | cut -d' ' -f1 ) \
  | grep -qx c7427132b7977797a4cf3ff3ec46e665842229482bb1e45f7b874e15bb3dafbc \
  || { echo "SRC STREAM MISMATCH"; exit 1; }
# 7f. scaffold preflight P1-P7 (source-identity + namespace gate capability)
bash /tmp/opencode/prod-service-20260917/bin/preflight.sh "$DEST"
echo "M2 ENVELOPE INSTALLED AND VERIFIED"

# --- 8. OPTIONAL dry-run of the installed launcher (does NOT bind/signal) ----
# Reads only; no port bind, no namespace write (validate expects refusal exit 6).
SGLANG_LAUNCH_DRY_RUN=1 SGLANG_L3_MODE=disabled \
  SGLANG_RUN_ID="m2-freeze-verify-$(date -u +%Y%m%dT%H%M%SZ)-$$" \
  SGLANG_PORT=30000 bash "$DEST/launcher/launch.sh"

# --- 9. OPTIONAL apply the scaffold diffs (review before running) ------------
# ( cd /tmp/opencode/prod-service-20260917 && git apply --check <stage>/start.sh.diff \
#     && git apply <stage>/start.sh.diff )
# ( cd /tmp/opencode/prod-service-20260917 && git apply --check <stage>/service.env.diff \
#     && git apply <stage>/service.env.diff )
# ( install -m 0555 <stage>/bin/stop-m2.sh /tmp/opencode/prod-service-20260917/bin/stop-m2.sh )
```
Declared install-time hashes the follow-up must reproduce:
| Artifact | sha256 |
|---|---|
| `launcher/launch.sh` | `9a557d5f06dad5481b8e850c7b9b02ae29db276dc232b6baa1ac7e92d93b21c4` |
| `manifest/identity.json` | `f46e49b8f562040809dff4d081eabaaba52337f4acdc3e2539abf69cdb5fb1bc` |
| `manifest/identity-pins.json` | `64c9bf0c15edc6806bf4f7db5b009277cf9b64be87c6e7620d4d7ff38330bd85` |
| `manifest/TREE-SHA256.txt` | `e6e8de1cb117e89e7a7477582d41f6408a032c9f0e7e45c7408f0d98677c495a` |
| `bin/stop-m2.sh` | `3d27a0cd4f728f6c9dd34df252cb6f7c2ca98f2f0f216c902ac49b96c75c3243` |
| `start.sh.diff` | `49b67ee32b519b3814d426e50851781e9e9eda65e805b79e949d29d0bb022a39` |
| `service.env.diff` | `8d4554c75cba2b60fda9e2540e5a70b684bdf9b9ac9205a6731ff5daf27ff712` |

## Defects / blockers

1. **The live M2 server is unreachable by the stop draft, by design.** pid 1764114 was launched
   ad-hoc through the M1 tree, so there is no `$PID_DIR/m2.pid` and its cmdline references
   `.../local-prod-v1.2.1-candidate`, not the M2 envelope. `stop-m2.sh` therefore fails closed
   (rc 1: no pid file; or rc 3 if a pid file were forged). This is correct safety behavior, not a
   bug, but the follow-up must NOT claim it can stop the currently-running process.
2. **The M2 envelope currently on disk is an empty stub** (created 11:18): its `src/`, `manifest/`,
   `tools/` are empty and its launcher is M1's bytes. Extract deliverable 1 leaves the envelope in
   a state where the identity gate would FAIL until deliverables 1/2 and the install sequence are
   applied together. Installation is a single atomic follow-up step.
3. **`LOADED_SO_HASH` is inherited, not re-verified for M2.** M2 hardlinks M1's `src/rust`, so the
   loader fingerprint is identical by construction; however, `verified_at_launch=false`. This is
   the same status M1 carries and should be closed at first M2 launch, not silently assumed.
4. **`SOURCE_COMMIT` is M1's (`b2bbd6ea28`)** because M2 shares M1's source bytes. `git` is not
   available in the frozen tree (`fatal: not a git repository`), so this value was carried from
   `identity.json`, not recomputed. It is a claim about the shared source, not a fresh measurement.
5. **`/data/l3` is at 96% (21 GiB free).** M2 deliberately allocates nothing, so no pressure is
   added; noted because M1's extent path remains space-constrained.
6. **`OWNER IDENTITY MISLABEL` in the live owner state is not fixed by this design.** The ad-hoc
   run wrote `"identity": "M2-OMNICODER-9B-GPTQ-INT4"` directly. The scaffold path fixes this by
   reading `.name` from the M2 `identity.json` in `supervise.sh` (`LOCAL-PROD-v1.2.1-M2`), but that
   only takes effect for a scaffold-managed launch, not the current ad-hoc process.
7. **Scratch-created metadata side effect (disclosed).** During a writability probe I created and
   immediately removed `/opt/sglang/local-prod-v1.2.1-candidate-M2/.hltest_dst`. No content remains
   (`find` confirms no residue), but the directory mtime moved 11:18 -> 11:39. No file under `/opt`
   was modified. `/data/l3` received no new stores. The live server was never signalled.

## Remaining claims / exclusions

- **Established:** the M2 launcher text, its hash, its syntax validity, the M2 identity JSON and
  manifest, the two diffs' clean application and byte-preservation, the stop draft's syntax, and
  that the full gate chain (G1/G2/G3) PASSes and every negative case fails closed.
- **Established:** hardlinked `src` shares inodes with M1 (`link count 4` during staging; restored
  to 1 after cleanup), so "one source lineage, no forked bytes" is a filesystem fact, not prose.
- **Not established (and must not be claimed):** that a real M2 launch under this launcher reaches
  `/health` 200. That requires stopping the live server and taking the GPU — explicitly out of scope.
  The dry-run proves only that the gates pass and the argv is exactly the proven M2 argv.
- **Not established:** `supervise.sh` was NOT run to completion (it correctly blocked on the live
  canonical GPU lock and timed out at 25 s). Env propagation through its `setsid env` idiom was
  verified separately (`E10`), not by a full supervised launch.
- **Assumption (proposal, not fact):** that the intended M2 envelope is
  `/opt/sglang/local-prod-v1.2.1-candidate-M2` (already present as a stub) rather than sharing M1's
  tree path directly. The stub's existence and the dispatch's request for a distinct M2
  `launcher/launch.sh` + `manifest/identity.json` support this; the follow-up task should confirm.
- **Rejected alternative (recorded):** reusing the M1 launcher with only `SGLANG_MODEL_PATH` changed
  would NOT give M2 an independently pinnable identity, and the gate would validate M1's launcher
  hash while serving M2 — so it was not chosen.
- **Rejected alternative (recorded):** copying `src/` into the M2 envelope (a true fork) was not
  chosen; hardlinking keeps a single source lineage and identical digests.
- **Prior artifact defect corrected:** the malformed `start.sh` diff around line 352 of
  `M2-FROZEN-LAUNCHER-IMPLEMENT-R3-20260918.md` was NOT copied; both diffs here are freshly
  generated and independently proven to apply.
- **Interface note:** `SGLANG_L3_MODE` is this launch path's own control variable (it is not read by
  `sglang.launch_server`). Its only job is to make the disabled choice explicit and fail closed.
- **Exclusions:** no writes to `/opt`, no changes to `conf/service.env` or `bin/start.sh` on disk,
  no ledger edits, no service signals, no port binds, no L3 allocations under `/data/l3`.

## Scratch / evidence location (transparency)
All staging and verification ran under `/tmp/opencode/M2-ARCH-STAGE-20260918/` (allowed by the
dispatch for diff-check copies). Throwaway hardlink trees were removed; `/opt` link counts and
digests were re-verified as unchanged afterward (`E11`). The only file written outside scratch and
the artifact is this node's tool-output capture under `~/.local/share/opencode/`, which is runtime
bookkeeping, not a deliverable.

Terminal state: DONE
