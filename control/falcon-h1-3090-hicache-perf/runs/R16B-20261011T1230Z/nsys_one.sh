#!/usr/bin/env bash
set -euo pipefail
ROOT=/tmp/sglang-f1-r16b-clean
RUN=/home/ubuntu/workspaces/3rdparty/sglang-hicache/control/falcon-h1-3090-hicache-perf/runs/R16B-20261011T1230Z
cfg=$1 stage=$2
case "$cfg" in gpu-only) port=30138; launch="$RUN/launch_gpu_only.sh";; gpu-host) port=30139; launch="$RUN/launch_gpu_host.sh";; *) exit 2;; esac
if [[ $stage == p-heavy ]];then ilen=1024;olen=16;else ilen=128;olen=64;fi
export PYTHONPATH="/tmp/f1-r3-kernel-overlay:$ROOT/python:$ROOT/python/sglang/kernels/aot/python"
export SGLANG_ENABLE_HEALTH_ENDPOINT_GENERATION=false
exec 9>/tmp/f1-r16b-gpu-exclusive.lock
flock -x 9
nvidia-smi --query-gpu=memory.used,utilization.gpu --format=csv,noheader,nounits | awk -F, '($1+0)>32 || ($2+0)>2 { exit 1 }'
"$launch" > "$RUN/profile-${cfg}-server.log" 2>&1 & server=$!
cleanup(){ kill -TERM "$server" 2>/dev/null||true; for _ in $(seq 1 35); do kill -0 "$server" 2>/dev/null||break;sleep 1;done; kill -KILL "$server" 2>/dev/null||true;wait "$server" 2>/dev/null||true; }
trap cleanup EXIT INT TERM
for _ in $(seq 1 180);do grep -q 'The server is fired up and ready to roll!' "$RUN/profile-${cfg}-server.log"&&break;kill -0 "$server" 2>/dev/null||exit 1;sleep 2;done
grep -q 'The server is fired up and ready to roll!' "$RUN/profile-${cfg}-server.log"
nsys profile --trace=cuda,nvtx,osrt --sample=none --trace-fork-before-exec=true --cuda-graph-trace=node --force-overwrite=true --output="$RUN/nsys-${cfg}-${stage}" \
 env PYTHONPATH="$PYTHONPATH" SGLANG_ENABLE_HEALTH_ENDPOINT_GENERATION=false /home/ubuntu/venvs/sglang-3090/bin/python -m sglang.benchmark.serving \
 --backend sglang --model /data/models/Falcon-H1-7B-Instruct-GPTQ-Int4 --dataset-name random-ids --tokenizer /data/models/Falcon-H1-7B-Instruct-GPTQ-Int4 \
 --host 127.0.0.1 --port "$port" --num-prompts 16 --random-input-len "$ilen" --random-output-len "$olen" --request-rate inf --max-concurrency 4 \
 --seed 20261011 --temperature 0 --tokenize-prompt --output-details --output-file "$RUN/nsys-${cfg}-${stage}.jsonl" > "$RUN/nsys-${cfg}-${stage}.log" 2>&1
cleanup;trap - EXIT INT TERM
nvidia-smi --query-gpu=memory.used --format=csv,noheader | grep -qx '1 MiB'
