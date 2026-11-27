#!/usr/bin/env bash
# T013 closing sequence: paired C-8 reps with coverage, L3 restore probe, second
# long-context FA2 rep.
set -Eeuo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
export SGLANG_T011_BF16_TIMING_STRIDE=8
bash "$HERE/run_combo.sh" c8 fa2 r4
unset SGLANG_T011_BF16_TIMING_STRIDE
bash "$HERE/run_combo.sh" c8 triton r4
bash "$HERE/../20261127T-restore/run_restore.sh" > "$HERE/../20261127T-restore/restore.log" 2>&1 || true
bash "$HERE/run_combo.sh" long fa2 r2
/home/ubuntu/venvs/sglang-3090/bin/python "$HERE/compare_combos.py" "$HERE" > "$HERE/combo-compare.txt"
cat "$HERE/combo-verdict.json" | head -40
