#!/usr/bin/env bash
# T007: export the bounded Nsight window and summarize it with the existing analyzers.
set -euo pipefail
OUT=${1:?usage: t007_export_and_summarize.sh RUN_DIR}
ROOT=/home/ubuntu/workspaces/3rdparty/sglang-hicache
NSYS=/usr/local/bin/nsys

"$NSYS" export --type sqlite --force-overwrite true \
  -o "$OUT/t007-c8-window.sqlite" "$OUT/t007-c8-window.nsys-rep" > "$OUT/nsys-export.log" 2>&1
ls -l "$OUT/t007-c8-window.sqlite" | tee "$OUT/nsys-export-size.txt"

cd "$ROOT"
python3 control/gemma4-rtx3090-throughput-scheduling/runs/t007_analyze_window.py "$OUT" | tee "$OUT/window-analysis.txt"
python3 control/gemma4-rtx3090-throughput-scheduling/runs/t007_summarize_metrics.py "$OUT" | tee "$OUT/metrics-summary.txt"
