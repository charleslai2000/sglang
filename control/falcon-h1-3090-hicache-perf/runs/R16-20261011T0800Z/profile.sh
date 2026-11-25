#!/usr/bin/env bash
set -euo pipefail
ROOT=/home/ubuntu/workspaces/3rdparty/sglang-hicache
RUN="$ROOT/control/falcon-h1-3090-hicache-perf/runs/R16-20261011T0800Z"
config=$1
case "$config" in gpu-only) port=30128; launch="$RUN/launch_gpu_only.sh";; gpu-host) port=30129; launch="$RUN/launch_gpu_host.sh";; *) exit 2;; esac
export PYTHONPATH="/tmp/f1-r3-kernel-overlay:$ROOT/python:$ROOT/python/sglang/kernels/aot/python"
"$launch" > "$RUN/profile-$config-server.log" 2>&1 & server=$!
cleanup(){ kill -TERM "$server" 2>/dev/null || true; for _ in $(seq 1 30); do kill -0 "$server" 2>/dev/null || break; sleep 1; done; kill -KILL "$server" 2>/dev/null || true; wait "$server" 2>/dev/null || true; }
trap cleanup EXIT INT TERM
for _ in $(seq 1 120); do curl -fsS "http://127.0.0.1:$port/health" >/dev/null 2>&1 && break; sleep 2; done
for stage in p-heavy d-heavy; do
  if [[ $stage == p-heavy ]]; then inlen=1024; outlen=16; else inlen=128; outlen=64; fi
  nsys profile --trace=cuda,nvtx,osrt --sample=none --force-overwrite=true \
    --output="$RUN/nsys-$config-$stage" \
    env PYTHONPATH="$PYTHONPATH" /home/ubuntu/venvs/sglang-3090/bin/python -m sglang.benchmark.serving \
      --backend sglang --model /data/models/Falcon-H1-7B-Instruct-GPTQ-Int4 --dataset-name random-ids \
      --tokenizer /data/models/Falcon-H1-7B-Instruct-GPTQ-Int4 --host 127.0.0.1 --port "$port" \
      --num-prompts 32 --random-input-len "$inlen" --random-output-len "$outlen" \
      --request-rate inf --max-concurrency 8 --seed 20261011 --temperature 0 --tokenize-prompt \
      --output-details --output-file "$RUN/profile-$config-$stage.jsonl" \
      > "$RUN/profile-$config-$stage.log" 2>&1
done
cleanup; trap - EXIT INT TERM
nvidia-smi --query-gpu=memory.used --format=csv,noheader | grep -qx '1 MiB'
