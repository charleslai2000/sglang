#!/usr/bin/env bash
set -euo pipefail
RUN=/home/ubuntu/workspaces/3rdparty/sglang-hicache/control/falcon-h1-3090-hicache-perf/runs/R16C-20261012T0000Z
cfg=$1;conc=$2;trial=$3;exec "$RUN/sweep.sh" "$cfg" "$conc" "$trial"
