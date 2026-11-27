#!/usr/bin/env bash
# T013 combo cell: one C-8-family cell with a fixed (attention, quant) combination.
#   usage: run_combo.sh <c8|tiers|long> <triton|fa2> <rep>
set -Eeuo pipefail
ROOT=/home/ubuntu/workspaces/3rdparty/sglang-hicache
OUT=$(cd "$(dirname "$0")" && pwd)
WRAP=$ROOT/control/gemma4-rtx3090-throughput-scheduling/runs/t007_c8_profile.sh
TIER_ARGV=/data/sglang-hicache/gemma4/runs/20261126T-t009-c8-acceptance-r6/launch-argv.txt
L1ONLY_ARGV=/data/sglang-hicache/gemma4/runs/20261127T-t011-l1only-off2/launch-argv.txt
VENV=/home/ubuntu/venvs/sglang-3090

WORKLOAD=${1:?workload c8|tiers|long}
ARM=${2:?arm triton|fa2}
REP=${3:-r1}
CELL="$WORKLOAD-$ARM-$REP"
DIR=$OUT/cells/$CELL

[[ -r "$TIER_ARGV" && -r "$L1ONLY_ARGV" ]] || { echo "missing baseline argv" >&2; exit 2; }

rm -rf "$DIR"
mkdir -p "$DIR" "$OUT/logs"
cp "$OUT/cell-intent.txt" "$DIR/intent.txt"

ENVV=(T007_OUT="$DIR" T007_WINDOW_SECONDS=0 T007_CHUNK=4096 T007_BENCH_TAG="T013-$CELL"
      SGLANG_CTWNA16_HUMMING=1
      SGLANG_T011_BF16_TIMING_PATH="$DIR/ragged-coverage.json"
      SGLANG_T011_BF16_PREFIX_BUDGET_MB=128)
case "$WORKLOAD" in
  c8)
    ENVV+=(T007_BASELINE_ARGV="$L1ONLY_ARGV" T007_HICACHE_MODE=off)
    ;;
  tiers)
    ENVV+=(T007_BASELINE_ARGV="$TIER_ARGV" T007_HICACHE_MODE=on)
    ;;
  long)
    ENVV+=(T007_BASELINE_ARGV="$TIER_ARGV" T007_HICACHE_MODE=on
           T007_BENCH_CLIENTS=96 T007_BENCH_ROUNDS=6 T007_BENCH_REQ_LEN=5000
           T007_BENCH_OUT_LEN=256 T007_BENCH_MAXPAR=64)
    ;;
  *) echo "unknown workload: $WORKLOAD" >&2; exit 2 ;;
esac
if [[ $ARM == fa2 ]]; then
  ENVV+=(SGLANG_FA2_RAGGED_EXTEND=1 SGLANG_T011_BF16_TIMING_STRIDE=8)
elif [[ $ARM != triton ]]; then
  echo "unknown arm: $ARM" >&2; exit 2
fi

echo "CELL_START cell=$CELL at=$(date -u +%FT%TZ)" | tee -a "$OUT/combo-status.txt"
if ! env "${ENVV[@]}" bash "$WRAP" > "$OUT/logs/$CELL-wrapper.log" 2>&1; then
  printf 'cell=%s wrapper_failed at=%s\n' "$CELL" "$(date -u +%FT%TZ)" >> "$OUT/combo-status.txt"
  tail -20 "$OUT/logs/$CELL-wrapper.log" || true
  exit 4
fi
printf 'cell=%s done=%s summary=%s\n' "$CELL" "$(date -u +%FT%TZ)" \
  "$(cat "$DIR/official-summary.txt" 2>/dev/null || echo MISSING)" >> "$OUT/combo-status.txt"
# The L3 extent is a reproducible cache; keep the evidence, drop the bytes.
if [[ -d "$DIR/l3-extent" ]]; then
  du -sh "$DIR/l3-extent" >> "$OUT/combo-status.txt"
  grep -c . /dev/null >/dev/null || true
  cnt=$(grep -c "extent" "$DIR/server.log" 2>/dev/null || echo 0)
  printf 'cell=%s extent_log_lines=%s\n' "$CELL" "$cnt" >> "$OUT/combo-status.txt"
  rm -rf "$DIR/l3-extent"
fi
