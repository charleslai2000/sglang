#!/usr/bin/env bash
set -euo pipefail
ROOT=/home/ubuntu/workspaces/3rdparty/sglang-hicache
RUN="$ROOT/control/falcon-h1-3090-hicache-perf/runs/R16-20261011T0800Z"
config=$1
case "$config" in
 gpu-only) port=30128; launch="$RUN/launch_gpu_only.sh" ;;
 gpu-host) port=30129; launch="$RUN/launch_gpu_host.sh" ;;
 *) echo "usage: $0 gpu-only|gpu-host" >&2; exit 2 ;;
esac
export PORT=$port CONFIG=$config
export PYTHONPATH="/tmp/f1-r3-kernel-overlay:$ROOT/python:$ROOT/python/sglang/kernels/aot/python${PYTHONPATH:+:$PYTHONPATH}"
trials=${TRIALS:-3}
concurrencies=${CONCURRENCIES:-'1 4 8 16 32 64'}
for trial in $(seq 1 "$trials"); do
  if ss -ltn | grep -q ":$port "; then echo "port $port already occupied" >&2; exit 3; fi
  "$launch" > "$RUN/$config-server-trial$trial.log" 2>&1 &
  server=$!
  cleanup() {
    kill -TERM "$server" 2>/dev/null || true
    for _ in $(seq 1 30); do kill -0 "$server" 2>/dev/null || break; sleep 1; done
    kill -KILL "$server" 2>/dev/null || true
    wait "$server" 2>/dev/null || true
    for _ in $(seq 1 20); do
      if ! ss -ltn | grep -q ":$port "; then break; fi
      sleep 1
    done
  }
  trap cleanup EXIT INT TERM
  ready=0
  for _ in $(seq 1 120); do
    if curl -fsS "http://127.0.0.1:$port/health" >/dev/null 2>&1; then ready=1; break; fi
    if ! kill -0 "$server" 2>/dev/null; then break; fi
    sleep 2
  done
  if [[ $ready != 1 ]]; then cat "$RUN/$config-server-trial$trial.log"; exit 1; fi
  for case in p-heavy d-heavy long-context; do
    case "$case" in
      p-heavy) inlen=1024; outlen=16; prompts=32 ;;
      d-heavy) inlen=128; outlen=64; prompts=32 ;;
      long-context) inlen=4096; outlen=8; prompts=16 ;;
    esac
    for conc in $concurrencies; do
      /home/ubuntu/venvs/sglang-3090/bin/python -m sglang.benchmark.serving \
        --backend sglang --model /data/models/Falcon-H1-7B-Instruct-GPTQ-Int4 --dataset-name random-ids --tokenizer /data/models/Falcon-H1-7B-Instruct-GPTQ-Int4 \
        --host 127.0.0.1 --port "$port" --num-prompts "$prompts" --random-input-len "$inlen" \
        --random-output-len "$outlen" --request-rate inf --max-concurrency "$conc" \
        --seed 20261011 --temperature 0 --tokenize-prompt --output-details --cache-report \
        --output-file "$RUN/${config}-${case}-c${conc}-trial${trial}.jsonl" \
        > "$RUN/${config}-${case}-c${conc}-trial${trial}.log" 2>&1
    done
  done
  cleanup; trap - EXIT INT TERM
  nvidia-smi --query-gpu=memory.used --format=csv,noheader | grep -qx '1 MiB'
done
