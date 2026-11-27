#!/usr/bin/env bash
# T013 full combo sequence: C-8 L1-only, three-tier, T010 long context.
set -Eeuo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
run() { bash "$HERE/run_combo.sh" "$@"; }
run c8 triton r1
run c8 fa2 r1
run c8 fa2 r2
run tiers triton r1
run tiers fa2 r1
run tiers fa2 r2
run long triton r1
run long fa2 r1
/home/ubuntu/venvs/sglang-3090/bin/python "$HERE/compare_combos.py" "$HERE" | tee "$HERE/combo-compare.txt"
