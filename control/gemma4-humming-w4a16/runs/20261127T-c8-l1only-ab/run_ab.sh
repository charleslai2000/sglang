#!/usr/bin/env bash
# T012 C-8 L1-only A/B: frozen baseline argv, HiCache off, chunk 4096,
# 40 clients x 20 rounds (800 requests), identical for every cell.
# The only difference between cells is SGLANG_CTWNA16_HUMMING on the Humming arm.
set -Eeuo pipefail
ROOT=/home/ubuntu/workspaces/3rdparty/sglang-hicache
OUT=$(cd "$(dirname "$0")" && pwd)
WRAP=$ROOT/control/gemma4-rtx3090-throughput-scheduling/runs/t007_c8_profile.sh
BASELINE=${T012_BASELINE_ARGV:-/data/sglang-hicache/gemma4/runs/20261127T-t011-l1only-off2/launch-argv.txt}
VENV=/home/ubuntu/venvs/sglang-3090

[[ -r "$BASELINE" ]] || { echo "missing baseline argv: $BASELINE" >&2; exit 2; }

for CELL in off on1 on2; do
  DIR=$OUT/c8-$CELL
  rm -rf "$DIR"
  mkdir -p "$DIR"
  cp "$OUT/cell-intent.txt" "$DIR/intent.txt"
  ENVV=(T007_OUT="$DIR" T007_BASELINE_ARGV="$BASELINE" T007_HICACHE_MODE=off
        T007_WINDOW_SECONDS=0 T007_CHUNK=4096 T007_BENCH_TAG="T012-c8-l1only-$CELL")
  if [[ $CELL != off ]]; then
    ENVV+=(SGLANG_CTWNA16_HUMMING=1)
  fi
  echo "CELL_START cell=$CELL at=$(date -u +%FT%TZ)"
  mkdir -p "$OUT/logs"
  if ! env "${ENVV[@]}" bash "$WRAP" > "$OUT/logs/$CELL-wrapper.log" 2>&1; then
    printf 'cell=%s wrapper_failed\n' "$CELL" >> "$OUT/ab-status.txt"
    tail -20 "$OUT/logs/$CELL-wrapper.log" || true
    exit 4
  fi
  printf 'cell=%s done=%s summary=%s\n' "$CELL" "$(date -u +%FT%TZ)" \
    "$(cat "$DIR/official-summary.txt" 2>/dev/null || echo MISSING)" >> "$OUT/ab-status.txt"
done

"$VENV/bin/python" "$OUT/compare_ab.py" "$OUT" | tee "$OUT/compare.log"
