#!/usr/bin/env bash
# T013 round 2: the scored combos after the layer-gating fix (FA2 must actually
# plan once per prefill Forward). Paired cells, same argv, only the flag differs.
set -Eeuo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
run() { bash "$HERE/run_combo.sh" "$@"; }
run c8 triton r5
run c8 fa2 r5
run tiers triton r3
run tiers fa2 r3
run long triton r2
run long fa2 r2
/home/ubuntu/venvs/sglang-3090/bin/python "$HERE/compare_combos.py" "$HERE" > "$HERE/combo-compare.txt"
