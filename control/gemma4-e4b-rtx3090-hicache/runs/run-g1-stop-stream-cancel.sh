#!/usr/bin/env bash
set -euo pipefail
repo=/home/ubuntu/workspaces/3rdparty/sglang-hicache;venv=/home/ubuntu/venvs/sglang-3090;model=/data/sglang-hicache/gemma4/model;out="/data/sglang-hicache/gemma4/runs/$(date -u +%Y%m%dT%H%M%SZ)-g1-stop-stream-cancel";mkdir -p "$out";exec 9>/tmp/f1-r16b-gpu-exclusive.lock;flock -n 9 || { echo GPU-lock-unavailable >&2;exit 90; }
export PYTHONPATH="$repo/python:/data/sglang-hicache/gemma4/aot-sm86-build:$repo/3rdparty/sglang/python/sglang/kernels/aot/python${PYTHONPATH:+:$PYTHONPATH}";export LD_LIBRARY_PATH="$venv/lib/python3.12/site-packages/torch/lib:/usr/local/cuda-12.9/lib64${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}";export SGLANG_CACHE_DIR=/data/sglang-hicache/gemma4/cache;export HF_HOME=/data/sglang-hicache/gemma4/hf-home
(cd "$repo";"$venv/bin/python" -m sglang.launch_server --model-path "$model" --trust-remote-code --host 127.0.0.1 --port 31042 --context-length 2048 --max-running-requests 8 --max-total-tokens 4096 --mem-fraction-static .82 --kv-cache-dtype fp8_e5m2 --attention-backend triton --cuda-graph-max-bs-decode 1 --log-level info) > "$out/server.log" 2>&1 & pid=$!;echo "$pid" > "$out/server.pid"
cleanup(){ kill -TERM "$pid" 2>/dev/null || true;sleep 5;pkill -TERM -P "$pid" 2>/dev/null || true;kill -TERM "$pid" 2>/dev/null || true; };trap cleanup EXIT
for _ in $(seq 1 240);do curl -fsS http://127.0.0.1:31042/health >/dev/null 2>&1 && break;kill -0 "$pid" 2>/dev/null || { tail -50 "$out/server.log";exit 2; };sleep 5;done
GEMMA4_RUN_OUT="$out" "$venv/bin/python" "$repo/control/gemma4-e4b-rtx3090-hicache/runs/run-g1-stop-stream-cancel.py" | tee "$out/client.stdout"
printf '{"status":"MEASURED"}\n' > "$out/run-status.json"
