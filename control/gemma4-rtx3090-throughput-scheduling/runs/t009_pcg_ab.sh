#!/usr/bin/env bash
# T009 prefill CUDA graph pilot: short-window A/B on the C-8 workload shape
# (40 clients x 5 rounds, 1024 in / 256 out, Poisson 8, seed 42). Same server
# config as the C-8 acceptance apart from the prefill graph backend, so the
# delta is the graph only.
#
# usage: t009_pcg_ab.sh <graph|eager> <out_dir>
set -euo pipefail
MODE=${1:?graph|eager}
OUT=${2:?out dir}
ROOT=/home/ubuntu/workspaces/3rdparty/sglang-hicache
VENV=/home/ubuntu/venvs/sglang-3090
DATA=/data/sglang-hicache/gemma4
MODEL=$DATA/model
PORT=31403
LOCK=/tmp/f1-r16b-gpu-exclusive.lock
BUCKETS="${T009_PCG_BUCKETS:-1024 1280 1536 2048 3584 4096}"

mkdir -p "$OUT"; rm -rf "$OUT/l3-extent" "$OUT/request-metrics"; mkdir -p "$OUT/request-metrics"

ARGS=(
  --model-path "$MODEL" --trust-remote-code --host 127.0.0.1 --port "$PORT"
  --context-length 131072 --max-running-requests 32 --mem-fraction-static .94
  --kv-cache-dtype fp8_e5m2 --attention-backend triton
  --cuda-graph-backend-decode full --cuda-graph-max-bs-decode 32
  --log-level info --enable-metrics --decode-log-interval 40
  --export-metrics-to-file --export-metrics-to-file-dir "$OUT/request-metrics"
  --skip-server-warmup --enable-hierarchical-cache --hicache-size 8
  --hicache-write-policy write_back --hicache-io-backend kernel
  --hicache-mem-layout page_first --hicache-host-memory-mode cache
  --hicache-storage-backend extent
  --hicache-storage-backend-extra-config "{\"storage_dir\":\"$OUT/l3-extent\",\"extent_size\":67108864,\"file_size\":34359738368,\"max_size\":34359738368,\"min_free_space\":1073741824}"
  --hicache-storage-prefetch-policy wait_complete
  --chunked-prefill-size 4096
)
if [[ $MODE == graph ]]; then
  ARGS+=(--cuda-graph-backend-prefill breakable --cuda-graph-bs-prefill $BUCKETS)
else
  ARGS+=(--cuda-graph-backend-prefill disabled)
fi
printf '%q ' "${ARGS[@]}" > "$OUT/launch-argv.txt"; echo >> "$OUT/launch-argv.txt"

exec 9>"$LOCK"
flock -n 9 || { echo "GPU lock busy" >&2; exit 4; }

VENV_SITE=$VENV/lib/python3.12/site-packages
AOT=/data/sglang-hicache/g2-quasar-runs/20261110T-g2-postrope-e5m2-quality/aot-sm86-package
OVERLAY=$ROOT/control/gemma4-w4a16-3090-performance-capacity/runs/overlay
RUNS=$ROOT/control/gemma4-w4a16-3090-performance-capacity/runs
export PYTHONNOUSERSITE=1 SGLANG_GEMMA4_SWA_POOL_TOKENS=65536
export PYTHONPATH="$RUNS:$AOT:$ROOT/python:$VENV_SITE:$ROOT/python/sglang/kernels/aot/python:$OVERLAY"
export LD_LIBRARY_PATH="$VENV_SITE/torch/lib:/usr/local/cuda-12.9/lib64"
export SGLANG_CACHE_DIR=$DATA/cache HF_HOME=$DATA/cache/hf-home HF_DATASETS_CACHE=$DATA/cache/datasets
export SGLANG_ENABLE_METRICS_DEVICE_TIMER=1 SGLANG_ENABLE_NVTX_SCHEDULER=1
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True

( "$VENV/bin/python" -m sglang.launch_server "${ARGS[@]}" > "$OUT/server.log" 2>&1 ) &
SPID=$!
cleanup() {
  pkill -TERM -P $SPID 2>/dev/null || true
  kill -TERM $SPID 2>/dev/null || true
  for _ in $(seq 1 60); do kill -0 $SPID 2>/dev/null || break; sleep 1; done
  kill -KILL $SPID 2>/dev/null || true
  wait $SPID 2>/dev/null || true
}
trap cleanup EXIT

for _ in $(seq 1 600); do
  curl -sf "http://127.0.0.1:$PORT/health_generate" >/dev/null 2>&1 && break
  kill -0 $SPID 2>/dev/null || { echo SERVER_DIED; tail -30 "$OUT/server.log"; exit 5; }
  sleep 1
done
curl -sf "http://127.0.0.1:$PORT/health_generate" >/dev/null || { echo SERVER_NOT_READY; exit 5; }

nvidia-smi --query-gpu=memory.used --format=csv,noheader > "$OUT/gpu-used-after-capture.txt"
grep -E "Capture target prefill|max_total_num_tokens|available_gpu_mem" "$OUT/server.log" | tail -5 > "$OUT/capture-summary.txt" || true

cd "$ROOT"
timeout -k 60 1800 "$VENV/bin/python" benchmark/hicache/bench_multiturn.py \
  --num-clients 40 --num-rounds 5 --request-length 1024 --output-length 256 \
  --distribution poisson --request-rate 8 --seed 42 --max-parallel 64 \
  --disable-auto-run --fixed-history-tokens --host 127.0.0.1 --port "$PORT" \
  --model-path "$MODEL" \
  --dataset-path /data/sglang-hicache/datasets/ShareGPT_V3_unfiltered_cleaned_split.json \
  --log-file "$OUT/perf.jsonl" --tag T009-pcg-ab --request-hash-log "$OUT/hashes.jsonl" \
  > "$OUT/bench.log" 2>&1 || echo "BENCH_RC=$?" >> "$OUT/bench.log"

curl -sf "http://127.0.0.1:$PORT/metrics" > "$OUT/metrics-at-end.prom" || true
nvidia-smi --query-gpu=memory.used --format=csv,noheader > "$OUT/gpu-used-end.txt"
grep -c "cuda graph: True" "$OUT/server.log" > "$OUT/count-prefill-graph-true.txt" || true
grep -c "cuda graph: False" "$OUT/server.log" > "$OUT/count-prefill-graph-false.txt" || true
grep -E "forward_execution_seconds_total" "$OUT/metrics-at-end.prom" > "$OUT/extend-decode-seconds.prom" || true
echo "AB_DONE mode=$MODE"
