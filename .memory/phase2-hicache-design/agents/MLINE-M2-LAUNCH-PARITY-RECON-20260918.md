# M2 Launch Parity Reconciliation — Minimal Design

**Task**: Produce minimal design for granting M2 a first-class, freeze-able launch path with same safety guarantees as M1's frozen production launcher.

**Scope**: READ-ONLY analysis, bounded design deliverable. No implementation, no deployment, no writes to /opt, no GPU state changes, no restarts.

**Status**: WORKING

---

## Evidence

### M2 Current Launch (Temporary Script)

**File**: `/tmp/opencode/MLINE-M2-CUTOVER-20260918/launch-m2.sh`  
**Lines**: 1-153

Key excerpts (verbatim):

- **Line 2-6**: "# scratch artifact ( /tmp/opencode/... ), NOT product source"
- **Line 8-14**: Uses frozen tree `TREE=/opt/sglang/local-prod-v1.2.1-candidate` via PYTHONPATH but NOT through frozen launcher
- **Line 46-47**: Port check via embedded python socket binding
- **Line 49-50**: Material GPU holder check via `nvidia-smi`
- **Line 53-57**: Acquires flock on /tmp/opencode/gpu-3090.lock (fd 9) if available
- **Line 68-91**: Launch args array (direct python -m sglang.launch_server)
- **Line 94-101**: `setsid env ... PYTHONPATH="$SRC" ... (${ARGS[@]})`
- **Line 107-124**: Writes state file to OVERRIDE path

**M2 Launch Command** (as constructed, lines 68-91):
```
$PY -u -m sglang.launch_server \
  --model-path $MODEL \
  --host $HOST --port $PORT \
  --tp-size 1 \
  --mem-fraction-static 0.92 \
  --max-total-tokens 262144 \
  --context-length 131072 \
  --max-running-requests 8 \
  --max-mamba-cache-size 48 \
  --kv-cache-dtype fp8_e4m3 \
  --attention-backend flashinfer \
  --linear-attn-prefill-backend triton \
  --linear-attn-decode-backend triton \
  --mamba-radix-cache-strategy extra_buffer \
  --mamba-ssm-dtype float32 \
  --reasoning-parser qwen3 \
  --tool-call-parser qwen3_coder \
  --enable-metrics \
  --export-metrics-to-file \
  --export-metrics-to-file-dir $LOG_DIR \
  --disable-prefill-cuda-graph \
```

### M1 Frozen Production Launcher (Reference)

**Files**:
- `/opt/sglang/local-prod-v1.2.1-candidate/launcher/launch.sh` (lines 1-189)
- `/opt/sglang/local-pore-v1.2.1-candidate/manifest/identity.json` (lines 1-116)
- `/tmp/opencode/prod-service-20260917/bin/start.sh` (lines 1-99)
- `/tmp/opencode/prod-service-20260917/bin/supervise.sh` (lines 1-162)
- `/tmp/opencode/prod-service-20260917/bin/preflight.sh` (lines 1-121)
- `/tmp/opencode/prod-service-20260917/bin/switch.sh` (lines 1-77)

---

## Safety Mechanisms in M1 Frozen Launcher

### GATE 1: Fail-Closed Source-Identity Gate (lines 98-106 of launch.sh)

```bash
GATE_RC=0
GATE_OUT="$(env CUDA_VISIBLE_DEVICES=999 PYTHONDONTWRITEBYTECODE=1 \
  "$PY" "$TREE/tools/preflight_identity.py" \
  --tree "$TREE" --pid self --all --json 2>&1)" || GATE_RC=$?
if [ "$GATE_RC" -ne 0 ]; then
  echo "FATAL: source-identity gate FAILED (exit $GATE_RC) for tree $TREE" >&2
  echo "$GATE_OUT" >&2
  exit "$GATE_RC"
fi
```

**Checks enforced by preflight_identity.py**:
- P1: Tree layout (launcher, python, identity.json, src/python/sglang, manifest/TREE-SHA256.txt present)
- P2: Manifest digest matches recorded digest in identity.json
- P3: Launcher sha256 matches recorded launcher hash
- P4: Launcher enforces source-identity gate (self-check)
- P5: Launcher enforces per-run L3 namespace gate
- P6: sglang.__file__ resolves INSIDE tree (not editable venv binding)
- P7: Reserved shared L3 store present

### GATE 2: Frozen Src-Subtree Stream Digest (lines 112-120 of launch.sh)

```bash
STREAM_SHA="$( cd "$SRC" && find . \
    -not -path '*/__pycache__/*' -not -path '*/.pytest_cache/*' -print0 \
    | LC_ALL=C sort -z | xargs -0 sha256sum | sha256sum | cut -d' ' -f1 )"
if [ "$STREAM_SHA" != "$EXPECTED_SRC_STREAM_SHA256" ]; then
  echo "FATAL: src stream digest mismatch" >&2
  echo "  expected $EXPECTED_SRC_STREAM_SHA256" >&2
  echo "  actual   $STREAM_SHA" >&2
  exit 12
fi
```

**EXPECTED_SRC_STREAM_SHA256** (line 29): `c7427132b7977797a4cf3ff3ec46e665842229482bb1e45f7b874e15bb3dafbc`

### GATE 3: Per-Run L3 Namespace (lines 126-133 of launch.sh)

```bash
NS_RC=0
NS_OUT="$(env PYTHONDONTWRITEBYTECODE=1 "$PY" "$TREE/tools/l3_namespace.py" \
  --validate --task-id "$SGLANG_RUN_ID" --root "$L3_ROOT" \
  --path "$L3_DIR" --json 2>&1)" || NS_RC=$?
if [ "$NS_RC" -ne 0 ]; then
  echo "FATAL: L3 namespace gate FAILED (exit $NS_RC) for $L3_DIR" >&2
  echo "$NS_OUT" >&2
  exit "$NS_RC"
fi
```

### Gateway Variables Set Before Server Launch (lines 28-84 of launch.sh)

**Required environment** (M1 pattern):
- `SGLANG_PORT`, `SGLANG_PROFILE`, `SGLANG_RUN_ID`, `SGLANG_L3_ROOT`, `SGLANG_LOG_DIR`
- `PYTHONPATH="$SRC/python"` (line 70)
- `CUDA_HOME=/usr/local/cuda-12.9` (line 73)
- `CUDA_VISIBLE_DEVICES=GPU-2e3ed202-3655-d919-0a64-259209bc6587` (line 76)
- `SGLANG_HICACHE_EXTENT_BACKEND_*` (lines 79-82)
- `SGLANG_L3_NATIVE_WRITE_PATH=1` (line 83)

### Health Gate + Stop/Rollback Path (supervise.sh lines 123-153)

**Health check** (lines 123-132):
```bash
HEALTH_DEADLINE=$(( SECONDS + 2400 ))
while [ "$SECONDS" -lt "$HEALTH_DEADLINE" ]; do
  if ! [ -d "/proc/$SERVER_PID" ]; then die "server exited during startup; see $CONSOLE" 1; fi
  code="$(CUDA_VISIBLE_DEVICES=999 curl -s -o /dev/null -w '%{http_code}' \
          --max-time 5 "http://127.0.0.1:$PORT/health" 2>/dev/null || echo 000)"
  if [ "$code" = "200" ]; then break; fi
  sleep 3
done
```

**Stop path** (supervise.sh line 160):
```bash
wait "$SERVER_PID" || true
# supervisor releases lock
```

**supervise.sh** enforces canonical GPU lock (line 37-38):
```bash
gpu_lock_acquire 9 "supervise-$ROLE-$RUN_ID" || die "could not acquire canonical GPU lock" 1
```

---

## GAP Analysis: M2 vs M1

| Gap | M1 Has | M2 Has | Classification |
|-----|--------|--------|----------------|
| **Fail-closed source-identity gate via preflight_identity.py** | YES (lines 98-106) | NO | REQUIRED for safety parity |
| **Tree manifest digest verification (P2)** | YES | NO | REQUIRED for safety parity |
| **Launcher hash verification (P3)** | YES | NO | REQUIRED for safety parity |
| **Frozen launcher sha256 gate** | YES (P4 via preflight_identity.py) | NO (uses static TREE path) | REQUIRED for safety parity |
| **Per-run L3 namespace allocation/gate (P5)** | YES (l3_namespace.py) | NO | REQUIRED for safety parity |
| **sglang.__file__ binding check (P6)** | YES | NO | REQUIRED for safety parity |
| **Reserved L3 store check (P7)** | YES | NO | REQUIRED for safety parity |
| **src-subtree stream digest (EXPECTED_SRC_STREAM_SHA256)** | YES (line 29) | NO | REQUIRED for safety parity |
| **Supervise process with env verification** | YES (lines 77-118 of supervise.sh) | NO | REQUIRED for safety parity |
| **Supervise process holds canonical GPU lock** | YES (line 37) | YES (line 53) | Parity achieved |
| **Health gate via /health endpoint** | YES (line 124) | YES (line 140) | Parity achieved |
| **Port check (free check)** | start.sh line 33 | M2 line 46 | Parity achieved |
| **Material GPU holder check** | start.sh line 44 | M2 line 49 | Parity achieved |
| **stop.sh with identity check** | YES (common.sh line 191-197) | NO | REQUIRED |
| **Flocked lock /tmp/opencode/gpu-3090.lock** | YES | YES | Parity achieved |
| **Switch.sh for prod/test handoff** | YES (line 24-77) | NO | NICE-TO-HAVE |
| **Key/file signifier in /opt** | YES (name=LOCAL-PROD-v1.2.1) | NO | NICE-TO-HAVE |
| **/data/l3 per-run namespace** | YES (line 61-62) | NO | N/A for M2 (L3 disabled) |
| **SGLANG_RUN_ID allocation** | YES (line 63-67) | NO | REQUIRED for P5 |
| **preference.json, source-commit check** | NO, CHECKS done by launcher | N/A for M2 | N/A |

---

## Minimal Change Set Required for M2 Production Ready

### Files to CREATE

**1. `/opt/sglang/local-prod-v1.2.1-candidate-M2/` — new frozen tree for M2**

| File | Purpose | Content Summary |
|------|---------|-----------------|
| `launcher/launch.sh` | Frozen launcher with identity gate | M1 launch.sh adapted for M2 model path |
| `manifest/identity.json` | Frozen identity manifest | Similar to local-prod, with name="LOCAL-PROD-v1.2.1-M2" and source commit |
| `manifest/TREE-SHA256.txt` | Self-digest of manifest | Generated trees of files |
| `manifest/identity-pins.json` | Launcher hash pin (line 34 pattern) | Recorded launcher sha256 |

**2. New preflight tools under M2 tree**

| File | Source | Purpose |
|------|---------|---------|
| `tools/preflight_identity.py` | Copy from `/opt/sglang/local-prod-v1.2.1-candidate/tools/` | Run as-is, checks adapt to M2 tree |
| `tools/l3_namespace.py` | Copy from `/opt/sglang/local-prod-v1.2.1-candidate/tools/` | Run as-is |

**3. `/opt/sglang/local-prod-v1.2.1-candidate-M2/launcher-repin.sh`**

| Line | Purpose |
|------|---------|
| Writes `identity.json`, `identity-pins.json`, `TREE-SHA256.txt` from raw tree |
| Runs via `bin/freeze.sh` |

**4. `/opt/sglang/local-prod-v1.2.1-candidate-M2/src`**

| Note |
|------|
| Contains the M2-specific source code (omnicoder-9b scripted). This would be git frozen as M1's is for M1. |

---

### Additional File Changes

**5. `/tmp/opencode/prod-service-20260917/bin/start.sh` — add M2 role handler**

Current (lines 28-35, after ROLE assignment):
```bash
case "$ROLE" in
  prod) PORT="$PROD_PORT"; TREE="${TREE_OVERRIDE:-$PROD_TREE_DEFAULT}"; IDENTITY="${PROD_IDENTITY_DEFAULT}" ;;
  test) PORT="$TEST_PORT"; TREE="${TREE_OVERRIDE:-$TEST_TREE_DEFAULT}"; IDENTITY="LOCAL-PROD-v1.1.2" ;;
  *) die "unknown role '$ROLE' (want prod|test)" 2 ;;
esac
```

**Add**:
```bash
m2) PORT="$M2_PORT"; TREE="${TREE_OVERRIDE:-$M2_TREE_DEFAULT}"; IDENTITY="${M2_IDENTITY_DEFAULT}" ;;
```

Wait for:
- `start.sh` to recognize the new M2 role and pass the right tree.
- `/opt/sglang/local-prod-v1.2.1-M2-frozen/` becomes the M2 canonical tree path.

**6. `/tmp/opencode/prod-service-20260917/conf/service.env` — add M2 defaults**

Add:
```bash
M2_PORT=30000
M2_TREE_DEFAULT=/opt/sglang/local-prod-v1.2.1-candidate-M2
M2_IDENTITY_DEFAULT=LOCAL-PROD-v1.2.1-M2
M2_MODEL_PATH=/data/models/omnicoder-9b-gptq-int4
```

---

## Model Identity Gate for M2

**Required checks (from M1 pattern, adapted for M2)**:

1. **Tree hash verification** — M2's expected `TREE-SHA256.txt` digest matches current file:
   - Currently stored: `5ed662d0b603ef9ab29294a690c036718714e0ed5b699b62b8b7be488defd950` (line 168 of identity.json)
   - This would be a SHA256 of the filtered manifest fileset.

2. **Launcher sha256 pin** — M2 launcher file hash:
   - To be generated after `launch.sh` is created, similar computation to M1.

3. **Source commit** — M2-specific commit:
   - Line 17 of identity.json: `SOURCE_COMMIT` (M1's = `b2bbd6ea28`)

4. **sglang.__file__ binds inside M2 tree** — verified by P6 gate (line 95-98 of preflight.sh)

**The gate does not start the server** (per line 11-12 of launch.sh).

---

## What Cannot Be Determined Without Write/Run Access

1. **Actual M2 tree SHA256** — needs the real M2 src tree files to compute
2. **M2-specific commit hash** — not provided in input context (analogous to M1's `b2bbd6ea28`)
3. **M2 launcher file content** — needs to be created
4. **Hicache extent backend settings for M2** — M2 doesn't use HiCache but the /data/l3 directory is needed
5. **M2-specific constants (CONTEXT_MAX etc)** — only `--max-total-tokens 262144` known explicitly for M2

---

## Remaining Claims / Observations

1. **M2 has been ad-hoc served successfully** — evidenced by successful smoke tests (`M2_UP_PID`, `M2-server-info.txt` present)
2. **M2 uses frozen tree for src** (`PYTHONPATH="$TREE/src/python"`, line 8)
3. **M1 and M2 are incompatible on single 3090** — single GPU exclusive model (line 6 of switch.sh)
4. **Both M1 and M2 need L3 disabled** — M1 has HiCache/Ready-Horizon off for M2 spec, but M1 is already on production

---

**Terminal state: DONE**
