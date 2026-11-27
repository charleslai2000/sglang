#!/usr/bin/env bash
# T013 follow-up cells: interleaved repetitions so ordering effects do not
# favour one arm, then the full comparison.
set -Eeuo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
run() { bash "$HERE/run_combo.sh" "$@"; }
run c8 triton r2
run tiers triton r2
run c8 fa2 r3
run c8 triton r3
/home/ubuntu/venvs/sglang-3090/bin/python "$HERE/compare_combos.py" "$HERE" > "$HERE/combo-compare.txt"
cat "$HERE/combo-compare.txt"
