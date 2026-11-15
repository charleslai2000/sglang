#!/usr/bin/env bash
set -Eeuo pipefail
ROOT=/home/ubuntu/workspaces/3rdparty/sglang-hicache
VLLM=/home/ubuntu/venvs/vllm-gemma4
DATA=/data/sglang-hicache/gemma4
MODEL=$DATA/model
SAMPLES=$DATA/runs/20261114T-gsm8k-w4a16-bf16-e5m2-paired/bf16/samples.jsonl
OUT=$DATA/runs/20261115T-g1-bf16-gsm8k-explicit-bos/vllm-reference
LOCK=/tmp/f1-r16b-gpu-exclusive.lock
[[ $(sha256sum "$MODEL/model.safetensors" | awk '{print $1}') == 19d89d2a4b3e401a3eae75ec08ab112810421a036c91d8c8226b686be7fe0c5d ]]
[[ -s "$DATA/runs/20261115T-g1-bf16-gsm8k-explicit-bos/samples.jsonl" ]]
mkdir -p "$OUT"; exec 9>"$LOCK"; flock -n 9 || { echo GPU_LOCK_BUSY >&2; exit 90; }
export PYTHONNOUSERSITE=1
export HF_HOME="$DATA/cache/hf-home" HF_HUB_CACHE="$DATA/cache/hf-home/hub" HF_DATASETS_CACHE="$DATA/cache/datasets"
export LD_LIBRARY_PATH="$VLLM/lib/python3.12/site-packages/torch/lib:$VLLM/lib/python3.12/site-packages/nvidia/cu13/lib:/usr/local/cuda-13.0/lib64${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
PID=
cleanup() { set +e; [[ -z "$PID" ]] || { kill -TERM "$PID" 2>/dev/null; wait "$PID" 2>/dev/null; }; nvidia-smi --query-gpu=timestamp,utilization.gpu,memory.used --format=csv,noheader > "$OUT/gpu-after.csv"; ss -ltnp | grep ':31203\b' > "$OUT/port-after.txt" 2>&1; }
trap cleanup EXIT INT TERM
"$VLLM/bin/vllm" serve "$MODEL" --host 127.0.0.1 --port 31203 --dtype bfloat16 --kv-cache-dtype auto --max-model-len 8192 --max-num-seqs 16 --gpu-memory-utilization .90 --enforce-eager --disable-log-requests --generation-config vllm --trust-remote-code --no-enable-prefix-caching --served-model-name google/gemma-4-E4B-it-qat-w4a16-ct --override-generation-config '{"temperature":0.0,"top_p":1.0,"top_k":-1}' > "$OUT/server.log" 2>&1 & PID=$!
ready=0
for _ in $(seq 1 900); do if curl -fsS http://127.0.0.1:31203/health >/dev/null 2>&1; then ready=1; break; fi; kill -0 "$PID" 2>/dev/null || { tail -100 "$OUT/server.log"; exit 2; }; sleep 1; done
[[ $ready == 1 ]]
"$VLLM/bin/python" "$ROOT/control/gemma4-w4a16-3090-performance-capacity/runs/compare_gsm8k_vllm.py" --samples "$SAMPLES" --out "$OUT/records.json" --model "$MODEL" --service vllm --url http://127.0.0.1:31203/v1/completions --add-bos --docs "$(seq -s, 0 1318)" --timeout 1800 --resume
kill -TERM "$PID"; wait "$PID" || true; PID=
for _ in $(seq 1 180); do ! ss -ltn | grep -q ':31203 ' && break; sleep 1; done
"$VLLM/bin/python" "$ROOT/control/gemma4-w4a16-3090-performance-capacity/runs/score_gsm8k_vllm_reference.py" "$OUT/records.json" "$DATA/runs/20261115T-g1-bf16-gsm8k-explicit-bos/samples.jsonl" --out "$OUT/summary.json"
sha256sum "$OUT/records.json" "$OUT/summary.json" "$OUT/server.log" > "$OUT/SHA256SUMS"
