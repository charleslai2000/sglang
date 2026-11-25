#!/usr/bin/env bash
set -euo pipefail
RUN=/home/ubuntu/workspaces/3rdparty/sglang-hicache/control/falcon-h1-3090-hicache-perf/runs/R16C-20261012T0000Z
ROOT=/tmp/sglang-f1-r16b-clean
export PYTHONPATH="/tmp/f1-r3-kernel-overlay:$ROOT/python:$ROOT/python/sglang/kernels/aot/python"
for conc in 1 4 8 9;do
 for trial in 1 2 3;do
  f="$RUN/manifest-v4-c${conc}-t${trial}.json"
  args=(--create-manifest --output '' --manifest "$f" --concurrency "$conc")
  if [[ -e $f ]];then echo "preserving frozen manifest $f";continue;fi
  /home/ubuntu/venvs/sglang-3090/bin/python "$RUN/multiturn_sweep.py" "${args[@]}" > "$RUN/manifest-v4-c${conc}-t${trial}.log" 2>&1
  chmod 0444 "$f"
 done
done
