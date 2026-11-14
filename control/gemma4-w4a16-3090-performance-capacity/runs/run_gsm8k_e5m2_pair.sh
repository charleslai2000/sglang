#!/usr/bin/env bash
set -Eeuo pipefail
ROOT=/home/ubuntu/workspaces/3rdparty/sglang-hicache
VENV=/home/ubuntu/venvs/sglang-3090
DATA=/data/sglang-hicache/gemma4
OUT=/data/sglang-hicache/gemma4/runs/20261114T-gsm8k-w4a16-bf16-e5m2-paired
LOCK=/tmp/f1-r16b-gpu-exclusive.lock
MODEL=$DATA/model
AOT=/data/sglang-hicache/g2-quasar-runs/20261110T-g2-postrope-e5m2-quality/aot-sm86-package
OVERLAY=$ROOT/control/gemma4-w4a16-3090-performance-capacity/runs/overlay
[[ $(git -C "$ROOT" rev-parse HEAD) == 4c1673b5c7cfffcd1dc0bd3ef6104dc12af90472 ]]
[[ $(sha256sum "$MODEL/model.safetensors" | awk '{print $1}') == 19d89d2a4b3e401a3eae75ec08ab112810421a036c91d8c8226b686be7fe0c5d ]]
[[ $(sha256sum "$AOT/sgl_kernel/sm86/common_ops.abi3.so" | awk '{print $1}') == 22c9f5eb84e5e494df31f814aeffe5ba0aafb266fca2b56c99cfb5a3c1dea4c2 ]]
[[ $(sha256sum "$OVERLAY/sglang/kernels/ops/attention/extend_attention.py" | awk '{print $1}') == 69a9f59d6817b3947feb38639d47c690e82947ead0e9af50a0200f02a4b34d4e ]]
[[ -s "$OUT/train.jsonl" && -s "$OUT/test.jsonl" ]]
exec 9>"$LOCK"; flock -n 9 || { echo GPU_LOCK_BUSY >&2; exit 90; }
export PYTHONNOUSERSITE=1
export PYTHONPATH="$ROOT/control/gemma4-w4a16-3090-performance-capacity/runs:$AOT:$ROOT/python:/home/ubuntu/venvs/sglang-3090/lib/python3.12/site-packages:$ROOT/python/sglang/kernels/aot/python:$OVERLAY${PYTHONPATH:+:$PYTHONPATH}"
export LD_LIBRARY_PATH="$VENV/lib/python3.12/site-packages/torch/lib:/usr/local/cuda-12.9/lib64${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export SGLANG_CACHE_DIR="$DATA/cache" HF_HOME="$DATA/cache/hf-home" HF_DATASETS_CACHE="$DATA/cache/datasets"
export GSM8K_DATA_DIR="$OUT" GEMMA4_MODEL_IDENTITY='{"model_revision":"6cd26aaa2357fb2bad8c51699a7558a4d1a965bb","model_sha256":"19d89d2a4b3e401a3eae75ec08ab112810421a036c91d8c8226b686be7fe0c5d"}'
cd "$ROOT"
run_arm() {
 local arm=$1 dtype=$2 port=$3 dir="$OUT/$1" pid= ready=0
 mkdir -p "$dir"; : > "$dir/stop-audit.jsonl"
 export GSM8K_STOP_AUDIT="$dir/stop-audit.jsonl"
 "$VENV/bin/python" -m sglang.launch_server --model-path "$MODEL" --trust-remote-code --host 127.0.0.1 --port "$port" --context-length 8192 --max-running-requests 16 --max-total-tokens 8192 --mem-fraction-static .90 --disable-radix-cache --kv-cache-dtype "$dtype" --attention-backend triton --cuda-graph-max-bs-decode 16 --skip-server-warmup --log-level info >"$dir/server.log" 2>&1 &
 pid=$!; echo "$pid" > "$dir/server.pid"
 stop_server() {
   set +e
   kill -TERM "$pid" 2>/dev/null
   for _ in $(seq 1 90); do kill -0 "$pid" 2>/dev/null || break; sleep 2; done
   pkill -TERM -P "$pid" 2>/dev/null; kill -TERM "$pid" 2>/dev/null; wait "$pid" 2>/dev/null
   ss -ltnp | grep ":${port}\\b" >"$dir/port-after.txt" 2>&1
   nvidia-smi --query-gpu=timestamp,utilization.gpu,memory.used --format=csv,noheader >"$dir/gpu-after.csv"
 }
 trap 'stop_server' RETURN
 for _ in $(seq 1 1200); do if curl -fsS "http://127.0.0.1:$port/health" >/dev/null 2>&1; then ready=1; break; fi; if ! kill -0 "$pid" 2>/dev/null; then tail -100 "$dir/server.log"; return 2; fi; sleep 1; done
 [[ $ready == 1 ]] || { echo "server readiness timeout $arm" >&2; return 3; }
 curl -fsS "http://127.0.0.1:$port/model_info" > "$dir/model-info.json"
 export GSM8K_SOURCE_SHA=$(git rev-parse HEAD)
 OPENAI_API_KEY=unused "$VENV/bin/python" "$ROOT/control/gemma4-w4a16-3090-performance-capacity/runs/gsm8k_lm_eval.py" --model gsm8k-gemma-completions --model_args "model=google/gemma-4-E4B-it-qat-w4a16-ct,base_url=http://127.0.0.1:${port}/v1/completions,tokenizer=$MODEL,tokenizer_backend=huggingface,tokenized_requests=false,trust_remote_code=true,timeout=1800,max_gen_toks=512,max_length=8193" --tasks gsm8k_official --include_path "$ROOT/control/gemma4-w4a16-3090-performance-capacity/runs" --apply_chat_template --fewshot_as_multiturn false --num_fewshot 5 --batch_size 1 --gen_kwargs 'temperature=0.0,max_gen_toks=512' --output_path "$dir/lm-eval" --log_samples 2>&1 | tee "$dir/lm-eval.log"
 stop_server; trap - RETURN; pid=
 local samples; samples=$(find "$dir/lm-eval" -type f -name 'samples_gsm8k_official_*.jsonl' -print -quit)
 [[ -n "$samples" ]]
 "$VENV/bin/python" "$ROOT/control/gemma4-w4a16-3090-performance-capacity/runs/attach_gsm8k_audit.py" "$samples" "$dir/stop-audit.jsonl"
 cp "$samples" "$dir/samples.jsonl"
}
trap '[[ -z "${pid:-}" ]] || { kill -TERM "$pid" 2>/dev/null || true; wait "$pid" 2>/dev/null || true; }' EXIT INT TERM
run_arm bf16 bf16 31175
run_arm e5m2 fp8_e5m2 31176
"$VENV/bin/python" "$ROOT/control/gemma4-w4a16-3090-performance-capacity/runs/verify_gsm8k_pair.py" "$OUT/bf16/samples.jsonl" "$OUT/e5m2/samples.jsonl" --out "$OUT/paired-scores.json"
sha256sum "$OUT"/test.jsonl "$OUT"/train.jsonl "$OUT"/{bf16,e5m2}/samples.jsonl "$OUT"/{bf16,e5m2}/stop-audit.jsonl "$OUT"/paired-scores.json > "$OUT/SHA256SUMS"
