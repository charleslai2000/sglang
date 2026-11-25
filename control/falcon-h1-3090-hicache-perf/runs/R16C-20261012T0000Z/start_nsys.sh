#!/usr/bin/env bash
set -euo pipefail
RUN=/home/ubuntu/workspaces/3rdparty/sglang-hicache/control/falcon-h1-3090-hicache-perf/runs/R16C-20261012T0000Z
rm -f "$RUN/stop-nsys-server"
exec /home/ubuntu/venvs/sglang-3090/bin/python "$RUN/nsys_attach_profile.py"
