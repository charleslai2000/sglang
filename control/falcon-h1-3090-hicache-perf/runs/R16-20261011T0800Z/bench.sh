#!/usr/bin/env bash
set -euo pipefail
ROOT=/home/ubuntu/workspaces/3rdparty/sglang-hicache
RUN="$ROOT/control/falcon-h1-3090-hicache-perf/runs/R16-20261011T0800Z"
cd "$ROOT"
export PYTHONPATH="/tmp/f1-r3-kernel-overlay:$ROOT/python:$ROOT/python/sglang/kernels/aot/python${PYTHONPATH:+:$PYTHONPATH}"
run_case() {
  local label=$1 port=$2 inlen=$3 outlen=$4 conc=$5 rep=$6 prompts=$7
  /home/ubuntu/venvs/sglang-3090/bin/python -m sglang.benchmark.serving \
    --backend sglang --dataset-name random-ids --tokenizer /data/models/Falcon-H1-7B-Instruct-GPTQ-Int4 \
    --host 127.0.0.1 --port "$port" --num-prompts "$prompts" --random-input-len "$inlen" \
    --random-output-len "$outlen" --request-rate inf --max-concurrency "$conc" \
    --seed 20261011 --temperature 0 --tokenize-prompt --output-details --cache-report \
    --output-file "$RUN/${CONFIG}-${label}-c${conc}-r${rep}.jsonl"
}
for case in p-heavy d-heavy long-context; do
  case "$case" in
    p-heavy) inlen=2048; outlen=32; prompts=512 ;;
    d-heavy) inlen=256; outlen=256; prompts=512 ;;
    long-context) inlen=6144; outlen=64; prompts=256 ;;
  esac
  for conc in 1 4 8 16 32 64; do
    for rep in 1 2 3; do run_case "$case" "${PORT:?set PORT}" "$inlen" "$outlen" "$conc" "$rep" "$prompts"; done
  done
done
