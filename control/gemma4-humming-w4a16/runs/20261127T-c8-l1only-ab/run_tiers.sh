#!/usr/bin/env bash
# T012 conditional three-tier validation: production HiCache L1+L2+L3 config from
# the frozen C-8 acceptance argv, Marlin vs Humming, identical workload.
set -Eeuo pipefail
ROOT=/home/ubuntu/workspaces/3rdparty/sglang-hicache
OUT=$(cd "$(dirname "$0")" && pwd)
WRAP=$ROOT/control/gemma4-rtx3090-throughput-scheduling/runs/t007_c8_profile.sh
BASELINE=${T012_TIER_BASELINE:-/data/sglang-hicache/gemma4/runs/20261126T-t009-c8-acceptance-r6/launch-argv.txt}
VENV=/home/ubuntu/venvs/sglang-3090

[[ -r "$BASELINE" ]] || { echo "missing baseline argv: $BASELINE" >&2; exit 2; }

for CELL in off on; do
  DIR=$OUT/tiers-$CELL
  rm -rf "$DIR"
  mkdir -p "$DIR"
  cp "$OUT/tiers-intent.txt" "$DIR/intent.txt"
  ENVV=(T007_OUT="$DIR" T007_BASELINE_ARGV="$BASELINE" T007_HICACHE_MODE=on
        T007_WINDOW_SECONDS=0 T007_CHUNK=4096 T007_BENCH_TAG="T012-tiers-$CELL")
  if [[ $CELL == on ]]; then
    ENVV+=(SGLANG_CTWNA16_HUMMING=1)
  fi
  echo "CELL_START cell=$CELL at=$(date -u +%FT%TZ)"
  mkdir -p "$OUT/logs"
  if ! env "${ENVV[@]}" bash "$WRAP" > "$OUT/logs/tiers-$CELL-wrapper.log" 2>&1; then
    printf 'cell=%s wrapper_failed\n' "$CELL" >> "$OUT/tiers-status.txt"
    tail -20 "$OUT/logs/tiers-$CELL-wrapper.log" || true
    exit 4
  fi
  printf 'cell=%s done=%s summary=%s\n' "$CELL" "$(date -u +%FT%TZ)" \
    "$(cat "$DIR/official-summary.txt" 2>/dev/null || echo MISSING)" >> "$OUT/tiers-status.txt"
done

"$VENV/bin/python" "$OUT/compare_tiers.py" "$OUT" | tee "$OUT/tiers-compare.log"
