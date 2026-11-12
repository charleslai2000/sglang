#!/usr/bin/env bash
set -euo pipefail
SRC=/mnt/data/nerun-dev/llamacpp-discriminator-20260917/llama.cpp
BUILD=/data/sglang-hicache/g2-quasar-runs/llamacpp-cuda-sm86-mmq-20261112
ROOT=/home/ubuntu/workspaces/3rdparty/sglang-hicache
mkdir -p "$BUILD/harness"
g++ -O2 -std=c++17 -I"$SRC/ggml/include" -I"$SRC/ggml/src" -I"$SRC/ggml/src/ggml-cuda" -I/usr/local/cuda-12.9/include "$ROOT/experiments/g2-quasar-gguf-matmul-optimization/llama_mmq_harness.cpp" -L"$BUILD/bin" -Wl,-rpath,"$BUILD/bin" -lggml-cuda -lggml-cpu -lggml -lggml-base -L/usr/local/cuda-12.9/lib64 -lcudart -o "$BUILD/harness/llama_mmq_harness"
