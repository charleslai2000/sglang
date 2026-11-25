#!/usr/bin/env bash
set -euo pipefail
cd /home/ubuntu/workspaces/3rdparty/sglang-hicache
run="$PWD/control/falcon-h1-3090-hicache-perf/runs/R14-20261011T0000Z"
mkdir -p "$run/logs" "$run/prometheus" "$run/extent"
export PYTHONPATH="/tmp/f1-r3-kernel-overlay:$PWD/python:$PWD/python/sglang/kernels/aot/python${PYTHONPATH:+:$PYTHONPATH}"
export PROMETHEUS_MULTIPROC_DIR="$run/prometheus"
export T38C_RUN_ID="falcon-r14-l3-$(date -u +%Y%m%dT%H%M%SZ)"
export T38C_BUILD_COMPLETE_DEBUG=1
if [[ -e /tmp/t38c-durable-trace || -e /tmp/t38c-probe.log ]]; then echo "refusing shared marker/log collision" >&2; exit 2; fi
ln -s "$run/t38c-probe.jsonl" /tmp/t38c-probe.log
touch /tmp/t38c-durable-trace
cleanup() { rm -f /tmp/t38c-durable-trace /tmp/t38c-probe.log; }
trap cleanup EXIT INT TERM
/home/ubuntu/venvs/sglang-3090/bin/python -u -m sglang.launch_server \
  --model-path /data/models/Falcon-H1-7B-Instruct-GPTQ-Int4 --revision 52036ae497a2c0c253e17f98cc8652f2f7082ae3 \
  --served-model-name falcon-h1-r14 --host 127.0.0.1 --port 30127 --tp-size 1 --trust-remote-code \
  --mem-fraction-static 0.90 --max-running-requests 4 --context-length 8192 --mamba-radix-cache-strategy extra_buffer \
  --enable-hierarchical-cache --enable-session-radix-cache --hicache-size 1 --hicache-write-policy write_through \
  --hicache-io-backend kernel --hicache-mem-layout page_first --hicache-storage-backend extent \
  --hicache-storage-backend-extra-config '{"storage_dir":"/home/ubuntu/workspaces/3rdparty/sglang-hicache/control/falcon-h1-3090-hicache-perf/runs/R14-20261011T0000Z/extent","extent_size":150994944,"file_size":4294967296,"max_size":4294967296,"min_free_space":10737418240}' \
  --cuda-graph-backend-prefill disabled --cuda-graph-backend-decode full --enable-metrics --log-level info >"$run/server.log" 2>&1
