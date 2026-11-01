#!/usr/bin/env bash
set -euo pipefail
repo=/home/ubuntu/workspaces/3rdparty/sglang-hicache
venv=/home/ubuntu/venvs/sglang-3090
model=/data/sglang-hicache/gemma4/model
fixture=/data/sglang-hicache/gemma4/runs/20261031T172407Z-radix8k-profiler-prefill-c16
nsys=/opt/nvidia/nsight-compute/2025.2.1/host/target-linux-x64/nsys
out=/data/sglang-hicache/gemma4/runs/20261101T-prefill-sizes
mkdir -p "$out"
exec 9>/tmp/f1-r16b-gpu-exclusive.lock
flock -n 9 || exit 90
server_pid= nsys_pid= monitor_pid=
cleanup() {
  if [[ -n $server_pid ]]; then
    kill -TERM "$server_pid" 2>/dev/null || true
    for _ in $(seq 1 45); do kill -0 "$server_pid" 2>/dev/null || break; sleep 2; done
    pkill -TERM -P "$server_pid" 2>/dev/null || true
  fi
  if [[ -n $nsys_pid ]]; then kill -INT "$nsys_pid" 2>/dev/null || true; wait "$nsys_pid" 2>/dev/null || true; fi
  if [[ -n $monitor_pid ]]; then kill -TERM "$monitor_pid" 2>/dev/null || true; wait "$monitor_pid" 2>/dev/null || true; fi
  nvidia-smi --query-gpu=memory.used,utilization.gpu --format=csv,noheader >"$out/gpu-after.csv" 2>/dev/null || true
}
trap cleanup EXIT INT TERM
cp "$fixture/fixture.json" "$out/fixture.json"; cp "$fixture/fixture.sha256" "$out/fixture.sha256"
git -C "$repo" rev-parse HEAD >"$out/repo-head"
export PYTHONPATH="$repo/python:/data/sglang-hicache/gemma4/aot-sm86-build:$repo/3rdparty/sglang/python/sglang/kernels/aot/python${PYTHONPATH:+:$PYTHONPATH}"
export LD_LIBRARY_PATH="$venv/lib/python3.12/site-packages/torch/lib:/usr/local/cuda-12.9/lib64${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export SGLANG_CACHE_DIR=/data/sglang-hicache/gemma4/cache HF_HOME=/data/sglang-hicache/gemma4/hf-home
export SGLANG_ENABLE_REQUEST_TIME_STATS_LOGGING=1 SGLANG_ENABLE_METRICS_DEVICE_TIMER=1 SGLANG_LOG_FORWARD_ITERS=1 SGLANG_RADIX8K_PROFILER_NVTX=1 RADIX8K_OUT="$out"
nvidia-smi --query-gpu=timestamp,memory.used,utilization.gpu --format=csv --loop-ms=100 >"$out/gpu-samples.csv" & monitor_pid=$!
"$nsys" profile --duration=120 --trace=cuda,nvtx,osrt --sample=none --cpuctxsw=none --cuda-graph-trace=graph --cuda-event-trace=false --force-overwrite=true -o "$out/profile" "$venv/bin/python" -m sglang.launch_server --model-path "$model" --trust-remote-code --host 127.0.0.1 --port 31371 --context-length 8450 --max-running-requests 1 --prefill-max-requests 1 --max-prefill-tokens 16384 --chunked-prefill-size 8192 --mem-fraction-static .90 --kv-cache-dtype bf16 --attention-backend triton --disable-radix-cache --enable-metrics --enable-request-time-stats-logging --log-level info >"$out/nsys-launch.log" 2>&1 &
nsys_pid=$!
for _ in $(seq 1 150); do server_pid=$(pgrep -f '[p]ython.*-m sglang.launch_server.*--port 31371'|head -1||true); [[ -n $server_pid ]] && break; sleep .2; done
[[ -n $server_pid ]] || exit 5
echo "$server_pid" >"$out/server.pid"
for _ in $(seq 1 90); do curl -sf http://127.0.0.1:31371/health >/dev/null && break; sleep 4; done
curl -sf http://127.0.0.1:31371/health >/dev/null
"$venv/bin/python" "$repo/control/gemma4-e4b-rtx3090-g1-perf-convergence/runs/prefill_sizes_gpu.py"
if [[ -n $server_pid ]]; then kill -TERM "$server_pid" 2>/dev/null || true; wait "$server_pid" 2>/dev/null || true; server_pid=; fi
if [[ -n $nsys_pid ]]; then wait "$nsys_pid" || true; nsys_pid=; fi
if [[ -n $monitor_pid ]]; then kill -TERM "$monitor_pid" 2>/dev/null || true; wait "$monitor_pid" 2>/dev/null || true; monitor_pid=; fi
nvidia-smi --query-gpu=memory.used,utilization.gpu --format=csv,noheader >"$out/gpu-after.csv" 2>/dev/null || true
