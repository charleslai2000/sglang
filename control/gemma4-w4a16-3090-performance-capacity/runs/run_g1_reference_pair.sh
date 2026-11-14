#!/usr/bin/env bash
set -Eeuo pipefail
ROOT=/home/ubuntu/workspaces/3rdparty/sglang-hicache
DATA=/data/sglang-hicache/gemma4
OUT=$DATA/runs/20261114T-g1-reference-pair
MODEL=$DATA/model
VLLM=/home/ubuntu/venvs/vllm-gemma4
SGLENV=/home/ubuntu/venvs/sglang-3090
AOT=/data/sglang-hicache/g2-quasar-runs/20261110T-g2-postrope-e5m2-quality/aot-sm86-package
OVERLAY=$ROOT/control/gemma4-w4a16-3090-performance-capacity/runs/overlay
LOCK=/tmp/f1-r16b-gpu-exclusive.lock
SAMPLES=$DATA/runs/20261114T-gsm8k-w4a16-bf16-e5m2-paired/bf16/samples.jsonl
mkdir -p "$OUT"; exec 9>"$LOCK"; flock -n 9 || { echo GPU_LOCK_BUSY >&2; exit 90; }
export HF_HOME=$DATA/cache/hf-home HF_HUB_CACHE=$DATA/cache/hf-home/hub HF_DATASETS_CACHE=$DATA/cache/datasets
cleanup() {
 set +e
 [[ -z "${SPID:-}" ]] || kill -TERM "$SPID" 2>/dev/null
 [[ -z "${VPID:-}" ]] || kill -TERM "$VPID" 2>/dev/null
 [[ -z "${SPID:-}" ]] || wait "$SPID" 2>/dev/null
 [[ -z "${VPID:-}" ]] || wait "$VPID" 2>/dev/null
 nvidia-smi --query-gpu=timestamp,memory.used,utilization.gpu --format=csv,noheader > "$OUT/gpu-after.csv"
}
trap cleanup EXIT INT TERM
# vLLM reference (same W4A16 safetensors; BF16 KV; eager; no prefix cache).
export PYTHONNOUSERSITE=1
"$VLLM/bin/vllm" serve "$MODEL" --host 127.0.0.1 --port 31201 --dtype bfloat16 --kv-cache-dtype auto --max-model-len 8192 --max-num-seqs 1 --gpu-memory-utilization .90 --enforce-eager --disable-log-requests --generation-config vllm --trust-remote-code --enable-log-outputs --no-enable-prefix-caching > "$OUT/vllm-server.log" 2>&1 & VPID=$!
ready=0
for i in $(seq 1 900); do curl -fsS http://127.0.0.1:31201/health >/dev/null 2>&1 && { ready=1; break; }; kill -0 "$VPID" 2>/dev/null || { tail -100 "$OUT/vllm-server.log"; exit 2; }; sleep 1; done
[[ $ready == 1 ]]
"$VLLM/bin/python" "$ROOT/control/gemma4-w4a16-3090-performance-capacity/runs/compare_gsm8k_vllm.py" --samples "$SAMPLES" --out "$OUT/vllm-representative.json" --model "$MODEL" --service vllm --url http://127.0.0.1:31201/v1/completions
kill -TERM "$VPID"; wait "$VPID" || true; VPID=
for i in $(seq 1 180); do ! ss -ltn | grep -q ':31201 ' && break; sleep 1; done
# SGLang matching reference; use prior verified AOT and frozen SM86 compatibility overlay.
export PYTHONNOUSERSITE=1
export PYTHONPATH="$ROOT/control/gemma4-w4a16-3090-performance-capacity/runs:$AOT:$ROOT/python:$SGLENV/lib/python3.12/site-packages:$ROOT/python/sglang/kernels/aot/python:$OVERLAY${PYTHONPATH:+:$PYTHONPATH}"
export LD_LIBRARY_PATH="$SGLENV/lib/python3.12/site-packages/torch/lib:/usr/local/cuda-12.9/lib64${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export SGLANG_CACHE_DIR=$DATA/cache
"$SGLENV/bin/python" -m sglang.launch_server --model-path "$MODEL" --trust-remote-code --host 127.0.0.1 --port 31202 --context-length 8192 --max-running-requests 1 --mem-fraction-static .90 --disable-radix-cache --kv-cache-dtype bf16 --attention-backend triton --disable-cuda-graph --log-level info > "$OUT/sglang-server.log" 2>&1 & SPID=$!
ready=0
for i in $(seq 1 900); do curl -fsS http://127.0.0.1:31202/health >/dev/null 2>&1 && { ready=1; break; }; kill -0 "$SPID" 2>/dev/null || { tail -100 "$OUT/sglang-server.log"; exit 3; }; sleep 1; done
[[ $ready == 1 ]]
"$SGLENV/bin/python" "$ROOT/control/gemma4-w4a16-3090-performance-capacity/runs/compare_gsm8k_vllm.py" --samples "$SAMPLES" --out "$OUT/sglang-representative.json" --model "$MODEL" --service sglang --url http://127.0.0.1:31202/v1/completions
kill -TERM "$SPID"; wait "$SPID" || true; SPID=
for i in $(seq 1 180); do ! ss -ltn | grep -q ':31202 ' && break; sleep 1; done
sha256sum "$OUT"/*.json "$OUT"/*.log > "$OUT/SHA256SUMS"
