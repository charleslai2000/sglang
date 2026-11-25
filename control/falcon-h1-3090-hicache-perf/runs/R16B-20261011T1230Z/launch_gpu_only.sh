#!/usr/bin/env bash
set -euo pipefail
ROOT=/tmp/sglang-f1-r16b-clean
RUN=/home/ubuntu/workspaces/3rdparty/sglang-hicache/control/falcon-h1-3090-hicache-perf/runs/R16B-20261011T1230Z
cd "$ROOT"
export PYTHONPATH="/tmp/f1-r3-kernel-overlay:$ROOT/python:$ROOT/python/sglang/kernels/aot/python${PYTHONPATH:+:$PYTHONPATH}"
export SGLANG_ENABLE_HEALTH_ENDPOINT_GENERATION=false
export PROMETHEUS_MULTIPROC_DIR="$RUN/prometheus-gpu-only"
mkdir -p "$PROMETHEUS_MULTIPROC_DIR"
exec /home/ubuntu/venvs/sglang-3090/bin/python -u -m sglang.launch_server \
 --model-path /data/models/Falcon-H1-7B-Instruct-GPTQ-Int4 --revision 52036ae497a2c0c253e17f98cc8652f2f7082ae3 \
 --served-model-name falcon-h1-r16b --host 127.0.0.1 --port 30138 --tp-size 1 --trust-remote-code \
 --mem-fraction-static 0.90 --max-running-requests 9 --context-length 8192 --cuda-graph-max-bs-decode 8 \
 --cuda-graph-backend-prefill disabled --cuda-graph-backend-decode full --enable-metrics --log-level info
