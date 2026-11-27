#!/usr/bin/env bash
# T013 closing: real L3 restore + greedy equality across combos, then a repeat of
# the noisiest pair (C-8 L1-only) to show the FA2 delta is stable.
set -Eeuo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
bash "$HERE/../20261127T-restore/run_restore.sh" > "$HERE/../20261127T-restore/restore.log" 2>&1 || true
bash "$HERE/run_combo.sh" c8 triton r6
bash "$HERE/run_combo.sh" c8 fa2 r6
/home/ubuntu/venvs/sglang-3090/bin/python "$HERE/compare_combos.py" "$HERE" > "$HERE/combo-compare.txt"
