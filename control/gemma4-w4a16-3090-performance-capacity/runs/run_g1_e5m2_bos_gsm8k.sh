#!/usr/bin/env bash
set -Eeuo pipefail
ROOT=/home/ubuntu/workspaces/3rdparty/sglang-hicache
VENV=/home/ubuntu/venvs/sglang-3090
DATA=/data/sglang-hicache/gemma4
MODEL=$DATA/model
OUT=$DATA/runs/20261115T-g1-e5m2-gsm8k-explicit-bos
BASE=$DATA/runs/20261115T-g1-bf16-gsm8k-explicit-bos
LOCK=/tmp/f1-r16b-gpu-exclusive.lock
AOT=/data/sglang-hicache/g2-quasar-runs/20261110T-g2-postrope-e5m2-quality/aot-sm86-package
OVERLAY=$ROOT/control/gemma4-w4a16-3090-performance-capacity/runs/overlay
[[ $(git -C "$ROOT" rev-parse HEAD) == 8eea0bc89e51ffc6f6da62988cc6217532ceb9bc ]]
[[ $(sha256sum "$MODEL/model.safetensors" | awk '{print $1}') == 19d89d2a4b3e401a3eae75ec08ab112810421a036c91d8c8226b686be7fe0c5d ]]
[[ -f "$BASE/samples.jsonl" && -f "$BASE/stop-audit.jsonl" ]]
[[ $(sha256sum "$AOT/sgl_kernel/sm86/common_ops.abi3.so" | awk '{print $1}') == 22c9f5eb84e5e494df31f814aeffe5ba0aafb266fca2b56c99cfb5a3c1dea4c2 ]]
[[ $(sha256sum "$OVERLAY/sglang/kernels/ops/attention/extend_attention.py" | awk '{print $1}') == 69a9f59d6817b3947feb38639d47c690e82947ead0e9af50a0200f02a4b34d4e ]]
mkdir -p "$OUT"; exec 9>"$LOCK"; flock -n 9 || { echo GPU_LOCK_BUSY >&2; exit 90; }
export PYTHONNOUSERSITE=1
export PYTHONPATH="$ROOT/control/gemma4-w4a16-3090-performance-capacity/runs:$AOT:$ROOT/python:$VENV/lib/python3.12/site-packages:$ROOT/python/sglang/kernels/aot/python:$OVERLAY${PYTHONPATH:+:$PYTHONPATH}"
export LD_LIBRARY_PATH="$VENV/lib/python3.12/site-packages/torch/lib:/usr/local/cuda-12.9/lib64${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export SGLANG_CACHE_DIR="$DATA/cache" HF_HOME="$DATA/cache/hf-home" HF_DATASETS_CACHE="$DATA/cache/datasets"
export GSM8K_DATA_DIR="$DATA/runs/20261114T-gsm8k-w4a16-bf16-e5m2-paired" GSM8K_PROMPT_PROTOCOL=gemma-explicit-bos-v1
export GEMMA4_MODEL_IDENTITY='{"model_revision":"6cd26aaa2357fb2bad8c51699a7558a4d1a965bb","model_sha256":"19d89d2a4b3e401a3eae75ec08ab112810421a036c91d8c8226b686be7fe0c5d"}'
export GSM8K_SOURCE_SHA=$(git -C "$ROOT" show 8eea0bc89e51ffc6f6da62988cc6217532ceb9bc:control/gemma4-w4a16-3090-performance-capacity/runs/gsm8k_completion_adapter.py | sha256sum | awk '{print $1}')
cd "$ROOT"
PID=
cleanup() { set +e; [[ -z "$PID" ]] || { kill -TERM "$PID" 2>/dev/null; wait "$PID" 2>/dev/null; }; nvidia-smi --query-gpu=timestamp,utilization.gpu,memory.used --format=csv,noheader > "$OUT/gpu-after.csv"; ss -ltnp | grep ':31178\b' > "$OUT/port-after.txt" 2>&1; }
trap cleanup EXIT INT TERM
: > "$OUT/stop-audit.jsonl"
"$VENV/bin/python" -m sglang.launch_server --model-path "$MODEL" --trust-remote-code --host 127.0.0.1 --port 31178 --context-length 8192 --max-running-requests 16 --max-total-tokens 8192 --mem-fraction-static .90 --disable-radix-cache --kv-cache-dtype fp8_e5m2 --attention-backend triton --cuda-graph-max-bs-decode 16 --skip-server-warmup --log-level info > "$OUT/server.log" 2>&1 & PID=$!
ready=0
for _ in $(seq 1 1200); do if curl -fsS http://127.0.0.1:31178/health >/dev/null 2>&1; then ready=1; break; fi; kill -0 "$PID" 2>/dev/null || { tail -100 "$OUT/server.log"; exit 2; }; sleep 1; done
[[ $ready == 1 ]]
curl -fsS http://127.0.0.1:31178/model_info > "$OUT/model-info.json"
export GSM8K_STOP_AUDIT="$OUT/stop-audit.jsonl"
OPENAI_API_KEY=unused "$VENV/bin/python" "$ROOT/control/gemma4-w4a16-3090-performance-capacity/runs/gsm8k_lm_eval.py" --model gsm8k-gemma-completions --model_args "model=google/gemma-4-E4B-it-qat-w4a16-ct,base_url=http://127.0.0.1:31178/v1/completions,tokenizer=$MODEL,tokenizer_backend=huggingface,tokenized_requests=false,trust_remote_code=true,timeout=1800,max_gen_toks=512,max_length=8193,add_bos_token=true" --tasks gsm8k_official --include_path "$ROOT/control/gemma4-w4a16-3090-performance-capacity/runs" --apply_chat_template --fewshot_as_multiturn false --num_fewshot 5 --batch_size 1 --gen_kwargs 'temperature=0.0,max_gen_toks=512' --output_path "$OUT/lm-eval" --log_samples 2>&1 | tee "$OUT/lm-eval.log"
kill -TERM "$PID"; wait "$PID" || true; PID=
for _ in $(seq 1 180); do ! ss -ltn | grep -q ':31178 ' && break; sleep 1; done
SAMPLES=$(find "$OUT/lm-eval" -type f -name 'samples_gsm8k_official_*.jsonl' -print -quit)
[[ -n "$SAMPLES" ]]
"$VENV/bin/python" "$ROOT/control/gemma4-w4a16-3090-performance-capacity/runs/attach_gsm8k_audit.py" "$SAMPLES" "$OUT/stop-audit.jsonl"
cp "$SAMPLES" "$OUT/samples.jsonl"
"$VENV/bin/python" "$ROOT/control/gemma4-w4a16-3090-performance-capacity/runs/verify_gsm8k_pair.py" "$BASE/samples.jsonl" "$OUT/samples.jsonl" --out "$OUT/paired-scores.json"
"$VENV/bin/python" "$ROOT/control/gemma4-w4a16-3090-performance-capacity/runs/summarize_gsm8k_e5m2_pair.py" "$BASE/samples.jsonl" "$OUT/samples.jsonl"
sha256sum "$BASE/samples.jsonl" "$OUT/samples.jsonl" "$OUT/stop-audit.jsonl" "$OUT/paired-scores.json" "$OUT/summary.json" "$OUT/model-info.json" > "$OUT/SHA256SUMS"
