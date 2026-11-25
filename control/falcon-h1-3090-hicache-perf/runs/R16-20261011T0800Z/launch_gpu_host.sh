#!/usr/bin/env bash
set -euo pipefail
ROOT=/home/ubuntu/workspaces/3rdparty/sglang-hicache
RUN="$ROOT/control/falcon-h1-3090-hicache-perf/runs/R16-20261011T0800Z"
cd "$ROOT"
mkdir -p "$RUN/prometheus"
export PYTHONPATH="/tmp/f1-r3-kernel-overlay:$ROOT/python:$ROOT/python/sglang/kernels/aot/python${PYTHONPATH:+:$PYTHONPATH}"
export PROMETHEUS_MULTIPROC_DIR="$RUN/prometheus"
exec /home/ubuntu/venvs/sglang-3090/bin/python -u -m sglang.launch_server \
 --model-path /data/models/Falcon-H1-7B-Instruct-GPTQ-Int4 \
 --revision 52036ae497a2c0c253e17f98cc8652f2f7082ae3 \
 --served-model-name falcon-h1-f1-r16 --host 127.0.0.1 --port 30129 --tp-size 1 \
 --trust-remote-code --mem-fraction-static 0.90 --max-running-requests 9 --context-length 8192 --cuda-graph-max-bs-decode 8 \
 --enable-hierarchical-cache --hicache-size 12 --hicache-write-policy write_through \
 --hicache-io-backend kernel --hicache-mem-layout page_first \
 --cuda-graph-backend-prefill disabled --cuda-graph-backend-decode full \
 --enable-metrics --log-level info
