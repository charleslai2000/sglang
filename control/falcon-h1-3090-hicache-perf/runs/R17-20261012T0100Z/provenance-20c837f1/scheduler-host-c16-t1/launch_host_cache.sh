#!/usr/bin/env bash
set -euo pipefail
ROOT=/tmp/sglang-r17
RUN="$ROOT/control/falcon-h1-3090-hicache-perf/runs/R17-20261012T0100Z"
cd "$ROOT"
export PYTHONPATH="/tmp/f1-r3-kernel-overlay:$ROOT/python:$ROOT/python/sglang/kernels/aot/python${PYTHONPATH:+:$PYTHONPATH}"
export SGLANG_ENABLE_HEALTH_ENDPOINT_GENERATION=false
export SGLANG_PROFILE_V2="${SGLANG_PROFILE_V2:-0}"
export SGLANG_LOG_FORWARD_ITERS="${SGLANG_LOG_FORWARD_ITERS:-1}"
export SGLANG_R17_PROFILE_TAG="${SGLANG_R17_PROFILE_TAG:-r17}"
export PROMETHEUS_MULTIPROC_DIR="$RUN/prometheus"
mkdir -p "$PROMETHEUS_MULTIPROC_DIR"
exec /home/ubuntu/venvs/sglang-3090/bin/python -u -m sglang.launch_server \
 --model-path /data/models/Falcon-H1-7B-Instruct-GPTQ-Int4 \
 --revision 52036ae497a2c0c253e17f98cc8652f2f7082ae3 \
 --served-model-name falcon-h1-r17 --host 127.0.0.1 --port 30160 --tp-size 1 \
 --trust-remote-code --mem-fraction-static 0.90 --max-running-requests 16 --context-length 8192 \
 --max-mamba-cache-size 83 --mamba-radix-cache-strategy extra_buffer --cuda-graph-max-bs-decode 16 \
 --enable-forward-pass-metrics --forward-pass-metrics-worker-id falcon-r17 --forward-pass-metrics-ipc-name "ipc:///tmp/sglang-r17-${SGLANG_R17_PROFILE_TAG}.sock" \
 --cuda-graph-backend-prefill disabled --cuda-graph-backend-decode full \
 --enable-hierarchical-cache --hicache-ratio 2.0 --enable-metrics --export-metrics-to-file --export-metrics-to-file-dir "$RUN/request-metrics" --log-level info
