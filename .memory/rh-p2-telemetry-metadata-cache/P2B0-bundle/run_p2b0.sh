#!/usr/bin/env bash
# P2-B0 cell runner (thin client-side wrapper).
#
# !!! THIS SCRIPT DOES NOT ACQUIRE THE GPU LOCK !!!
# The orchestrator/tester MUST launch (and later stop) the SGLang server under
# the single 3090 lock BEFORE invoking this script, e.g.:
#
#   P2B0_RH=on P2B0_MAX_RUNNING=4 P2B0_RUN_ID=p2b0-C4-on \
#     bash /mnt/data/neuron/sglang-3090-r112-20260911/launch-p2b0.sh \
#     > /mnt/data/neuron/sglang-3090-r112-20260911/sglang-server-p2b0-C4-on.log 2>&1 &
#
# launch-p2b0.sh acquires /mnt/data/gpu/3090.lock itself and holds it for the
# lifetime of the server.  This wrapper only sends client traffic to the
# already-running server and samples GPU + /metrics read-only; it never starts,
# stops or reconfigures the server and never touches the lock.
#
# It writes join.jsonl / gpu.csv / metrics.csv / cell.json under --out-dir and
# then runs p2b0_analyze.py to produce cell-summary.v2.json (plus a legacy
# cell-summary.json copy with the same v2 content).
#
# Usage:
#   run_p2b0.sh --out-dir DIR --agents 4 --rh on \
#     [--prime-turns 2] [--measure-turns 10] [--measure-seconds 300] \
#     [--hist-tokens 6000] [--delta-words 210] [--max-tokens 32] \
#     [--client-max-time 1200] [--gpu-sample-ms 200] [--nonce ID] \
#     [--base http://127.0.0.1:30000] [--server-log LOG]
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="${P2B0_PYTHON:-python3}"

OUT_DIR=""
AGENTS=4
RH="on"
PRIME_TURNS=2
MEASURE_TURNS=10
MEASURE_SECONDS=300
HIST_TOKENS=6000
DELTA_WORDS=210
MAX_TOKENS=32
CLIENT_MAX_TIME=1200
GPU_SAMPLE_MS=200
NONCE="$(date +%Y%m%d-%H%M%S)"
BASE="${P2B0_BASE:-http://127.0.0.1:30000}"
SERVER_LOG="${P2B0_SERVER_LOG:-/mnt/data/neuron/sglang-3090-r112-20260911/sglang-server-e.log}"
SKIP_ANALYZE=0

while [ $# -gt 0 ]; do
  case "$1" in
    --out-dir) OUT_DIR="$2"; shift 2 ;;
    --agents) AGENTS="$2"; shift 2 ;;
    --rh) RH="$2"; shift 2 ;;
    --prime-turns) PRIME_TURNS="$2"; shift 2 ;;
    --measure-turns) MEASURE_TURNS="$2"; shift 2 ;;
    --measure-seconds) MEASURE_SECONDS="$2"; shift 2 ;;
    --hist-tokens) HIST_TOKENS="$2"; shift 2 ;;
    --delta-words) DELTA_WORDS="$2"; shift 2 ;;
    --max-tokens) MAX_TOKENS="$2"; shift 2 ;;
    --client-max-time) CLIENT_MAX_TIME="$2"; shift 2 ;;
    --gpu-sample-ms) GPU_SAMPLE_MS="$2"; shift 2 ;;
    --nonce) NONCE="$2"; shift 2 ;;
    --base) BASE="$2"; shift 2 ;;
    --server-log) SERVER_LOG="$2"; shift 2 ;;
    --skip-analyze) SKIP_ANALYZE=1; shift ;;
    -h|--help) sed -n '1,40p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

if [ -z "$OUT_DIR" ]; then
  echo "FATAL: --out-dir is required" >&2
  exit 2
fi
mkdir -p "$OUT_DIR"

echo "P2B0_CELL out=$OUT_DIR agents=$AGENTS rh=$RH nonce=$NONCE"
echo "NOTE: server must already be running under the 3090 lock (not acquired here)."

set +e
"$PY" "$HERE/p2b0_driver.py" --run \
  --base "$BASE" \
  --agents "$AGENTS" \
  --rh "$RH" \
  --max-running "$AGENTS" \
  --prime-turns "$PRIME_TURNS" \
  --measure-turns "$MEASURE_TURNS" \
  --measure-seconds "$MEASURE_SECONDS" \
  --hist-tokens "$HIST_TOKENS" \
  --delta-words "$DELTA_WORDS" \
  --max-tokens "$MAX_TOKENS" \
  --client-max-time "$CLIENT_MAX_TIME" \
  --gpu-sample-ms "$GPU_SAMPLE_MS" \
  --nonce "$NONCE" \
  --server-log "$SERVER_LOG" \
  --out-dir "$OUT_DIR"
rc=$?
set -e
echo "DRIVER_RC=$rc"

if [ "$SKIP_ANALYZE" -eq 0 ]; then
  set +e
  "$PY" "$HERE/p2b0_analyze.py" --cell-json "$OUT_DIR/cell.json" \
    --out "$OUT_DIR/cell-summary.v2.json"
  arcs=$?
  set -e
  echo "ANALYZE_RC=$arcs"
  # keep the legacy filename for existing consumers (same v2 content)
  if [ "$arcs" -eq 0 ]; then
    cp "$OUT_DIR/cell-summary.v2.json" "$OUT_DIR/cell-summary.json"
  fi
fi
exit "$rc"
