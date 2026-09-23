#!/usr/bin/env bash
# =============================================================================
# GGUF sampled-contract smoke gate -- sequential driver.
#
# OWNER ORDER IS FIXED:  M4 FIRST, then M3.
#   M4 (swift-qwen38-27b-q3_k_m) is the shared-GGUF-runtime CONTROL: it exercises
#   the same GGUF loader/runtime path with a different quantization (Q3_K_M) and
#   carries an extra repetition penalty in its metadata.
#   M3 (IQ3_S) is the IQ3-specific risk (851 tensors, no penalty_repeat).
#   Running the control first means an M3 failure is only interpreted after the
#   shared runtime has been shown to either pass or fail on its own.
#
# The harness itself acquires/releases the canonical GPU lock per model; this
# driver never signals or kills an incumbent, and NEVER binds port 30000.
#
# Usage:
#   bash run_sampled_smoke.sh                 # full gate (needs the GPU, later)
#   GGUF_GATE_SRC=/path/to/python bash run_sampled_smoke.sh
#   bash run_sampled_smoke.sh --print-plan    # no GPU: show what would run
# =============================================================================
set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="${GGUF_GATE_PY:-/opt/sglang/local-prod-v1/env/bin/python}"
SRC="${GGUF_GATE_SRC:-/home/ubuntu/workspaces/3rdparty/sglang/python}"
PORT="${GGUF_GATE_PORT:-30165}"
RUNROOT="${GGUF_GATE_RUNROOT:-/mnt/data/nerun-dev/gguf-sampled-smoke-20260917/runs}"

export GGUF_GATE_SRC="$SRC"
export GGUF_GATE_PY="$PY"
export GGUF_GATE_PORT="$PORT"
export GGUF_GATE_RUNROOT="$RUNROOT"
export PYTHONDONTWRITEBYTECODE=1

echo "=== gguf-sampled-smoke gate ==="
echo "source tree : $SRC"
echo "python      : $PY"
echo "port        : $PORT   (never 30000)"
echo "runroot     : $RUNROOT"
echo "order       : m4 (control) -> m3 (IQ3-specific risk)"

if [ "${1:-}" = "--print-plan" ]; then
  echo
  echo "PLAN (no GPU contact, no server start):"
  echo "  1. $PY $HERE/server_harness_sampled.py --cpu-smoke"
  echo "  2. $PY $HERE/server_harness_sampled.py m4"
  echo "  3. $PY $HERE/server_harness_sampled.py m3"
  exit 0
fi

if [ ! -d "$SRC/sglang" ]; then
  echo "FATAL: source tree has no sglang package: $SRC" >&2
  exit 1
fi
if [ ! -x "$PY" ]; then
  echo "FATAL: python not executable: $PY" >&2
  exit 1
fi

mkdir -p "$RUNROOT"
cd "$HERE" || exit 1

# Offline contract smoke first: if the request/ngram logic is wrong, a GPU run
# would produce meaningless evidence.  Cheap, no socket, no CUDA.
echo
echo "=== step 0: CPU contract smoke $(date -u) ==="
"$PY" server_harness_sampled.py --cpu-smoke > "$RUNROOT/cpu_smoke.json" 2>&1
RC0=$?
echo "CPU_SMOKE_RC=$RC0"
if [ "$RC0" -ne 0 ]; then
  echo "FATAL: CPU contract smoke failed; not starting any server." >&2
  tail -40 "$RUNROOT/cpu_smoke.json" >&2
  exit "$RC0"
fi

echo
echo "=== step 1: M4 (control) $(date -u) ==="
"$PY" server_harness_sampled.py m4 > "$RUNROOT/m4.stdout.log" 2>&1
RC4=$?
echo "M4_RC=$RC4  $(date -u)"

echo
echo "=== step 2: M3 (IQ3-specific risk) $(date -u) ==="
"$PY" server_harness_sampled.py m3 > "$RUNROOT/m3.stdout.log" 2>&1
RC3=$?
echo "M3_RC=$RC3  $(date -u)"

echo
echo "=== per-model verdicts ==="
for k in m4 m3; do
  f="$RUNROOT/$k/report.json"
  if [ -f "$f" ]; then
    "$PY" - "$f" <<'PYEOF'
import json, sys
d = json.load(open(sys.argv[1]))
rep = d.get("criterion_report") or {}
print(f"--- {d.get('model_name')} ({d.get('model_key')}): "
      f"verdict={d.get('verdict')} status={d.get('status')}")
for name, c in (rep.get("criteria") or {}).items():
    print(f"      {name:24s} {'PASS' if c.get('pass') else 'FAIL'}")
for name, c in (rep.get("diagnostics") or {}).items():
    print(f"      diag:{name:19s} {c}")
if rep.get("failures"):
    print(f"      failures={rep['failures']}")
PYEOF
  else
    echo "--- $k: no report.json (rc=$RC4/$RC3)"
  fi
done

echo "=== gate end $(date -u) ==="
touch "$RUNROOT/sampled_smoke.done"
# Exit non-zero if either model failed, so CI/callers can gate on it.
if [ "$RC4" -ne 0 ] || [ "$RC3" -ne 0 ]; then exit 5; fi
exit 0
