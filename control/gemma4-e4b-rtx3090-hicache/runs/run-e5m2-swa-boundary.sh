#!/usr/bin/env bash
set -euo pipefail
repo=/home/ubuntu/workspaces/3rdparty/sglang-hicache;venv=/home/ubuntu/venvs/sglang-3090;model=/data/sglang-hicache/gemma4/model;root=/data/sglang-hicache/gemma4/runs
out="$root/$(date -u +%Y%m%dT%H%M%SZ)-e5m2-swa-boundary";mkdir -p "$out";exec 9>/tmp/f1-r16b-gpu-exclusive.lock;flock -n 9 || { echo GPU-lock-unavailable >&2;exit 90; };printf '%s\n' "$out" > "$out/run-path"
export PYTHONPATH="$repo/python:/data/sglang-hicache/gemma4/aot-sm86-build:$repo/3rdparty/sglang/python/sglang/kernels/aot/python${PYTHONPATH:+:$PYTHONPATH}";export LD_LIBRARY_PATH="$venv/lib/python3.12/site-packages/torch/lib:/usr/local/cuda-12.9/lib64${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}";export SGLANG_GEMMA4_CAPTURE_LAYERS=1;export GEMMA4_MODEL_IDENTITY='{"model_revision":"6cd26aaa2357fb2bad8c51699a7558a4d1a965bb","model_sha256":"19d89d2a4b3e401a3eae75ec08ab112810421a036c91d8c8226b686be7fe0c5d"}';export SGLANG_CACHE_DIR=/data/sglang-hicache/gemma4/cache;export HF_HOME=/data/sglang-hicache/gemma4/hf-home
start(){ local mode=$1 port=$2 dtype=$3; local dir="$out/$mode";mkdir -p "$dir";export SGLANG_GEMMA4_LAYERS_FILE="$dir/forward" SGLANG_GEMMA4_CAPTURE_LOGITS=1 SGLANG_GEMMA4_LOGITS_FILE="$dir/forward"; (cd "$repo";"$venv/bin/python" -m sglang.launch_server --model-path "$model" --trust-remote-code --host 127.0.0.1 --port "$port" --context-length 1024 --max-running-requests 1 --max-total-tokens 1024 --mem-fraction-static .82 --kv-cache-dtype "$dtype" --attention-backend triton --cuda-graph-max-bs-decode 1 --log-level info) > "$dir/server.log" 2>&1 & echo $! > "$dir/server.pid"; }
stop(){ local dir=$1;local p; p=$(cat "$dir/server.pid" 2>/dev/null || true);if [[ -n $p ]];then kill -TERM "$p" 2>/dev/null || true;fi;for _ in $(seq 1 90);do [[ -z $p ]] || ! kill -0 "$p" 2>/dev/null && break;sleep 2;done;if [[ -n $p ]] && kill -0 "$p" 2>/dev/null;then pkill -TERM -P "$p" 2>/dev/null || true;kill -TERM "$p" 2>/dev/null || true;sleep 3;fi; }
cleanup(){ stop "$out/bf16";stop "$out/e5m2"; };trap cleanup EXIT
start e5m2 31039 fp8_e5m2
wait_ready(){ local port=$1 dir=$2;for _ in $(seq 1 240);do if curl -fsS "http://127.0.0.1:$port/health" >/dev/null 2>&1;then return 0;fi;local p; p=$(cat "$dir/server.pid");if ! kill -0 "$p" 2>/dev/null;then echo "server exited: $dir" >&2;tail -50 "$dir/server.log" >&2;return 1;fi;sleep 5;done;return 1; }
wait_ready 31039 "$out/e5m2"
start bf16 31040 bf16;wait_ready 31040 "$out/bf16"
export GEMMA4_RUN_OUT="$out";"$venv/bin/python" "$repo/control/gemma4-e4b-rtx3090-hicache/runs/run-e5m2-swa-boundary.py" | tee "$out/client.stdout"
cleanup;trap - EXIT
printf '{"status":"MEASURED"}\n' > "$out/run-status.json"
