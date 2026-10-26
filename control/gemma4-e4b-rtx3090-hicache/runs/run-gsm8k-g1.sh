#!/usr/bin/env bash
set -euo pipefail
ROOT=/home/ubuntu/workspaces/3rdparty/sglang-hicache
VENV=/home/ubuntu/venvs/sglang-3090
DATA=/data/sglang-hicache/gemma4
RUN=${RUN:-$DATA/runs/20261026T-gsm8k-g1-final-bos}
LOCK=/tmp/f1-r16b-gpu-exclusive.lock
mkdir -p "$RUN"
if [[ ${GPU_LOCK_HELD:-0} == 0 ]]; then
  exec 9>"$LOCK"
  flock -n 9 || { echo GPU-lock-unavailable >&2; exit 90; }
fi
export PYTHONNOUSERSITE=1
export PYTHONPATH="$ROOT/control/gemma4-e4b-rtx3090-hicache/runs:$ROOT/python:$DATA/aot-sm86-build:$ROOT/3rdparty/sglang/python/sglang/kernels/aot/python${PYTHONPATH:+:$PYTHONPATH}"
export LD_LIBRARY_PATH="$VENV/lib/python3.12/site-packages/torch/lib:/usr/local/cuda-12.9/lib64${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export SGLANG_CACHE_DIR="$DATA/cache" HF_HOME="$DATA/cache/hf-home" HF_DATASETS_CACHE="$DATA/cache/datasets"
export GSM8K_DATA_DIR="$DATA/runs/gsm8k-prepare-20261026/data"
export GEMMA4_MODEL_IDENTITY='{"model_revision":"6cd26aaa2357fb2bad8c51699a7558a4d1a965bb","model_sha256":"19d89d2a4b3e401a3eae75ec08ab112810421a036c91d8c8226b686be7fe0c5d"}'
MODEL="$DATA/model"
cleanup() { for p in $(pgrep -f 'sglang.launch_server.*--port (31175|31176)' || true); do kill -TERM "$p" 2>/dev/null || true; done; sleep 3; nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader > "$RUN/gpu-cleanup.csv" 2>/dev/null || true; }
trap cleanup EXIT INT TERM
run_arm() {
 local arm=$1 dtype=$2 port=$3 dir="$RUN/$1"; mkdir -p "$dir"
 export GSM8K_STOP_AUDIT="$dir/stop-audit.jsonl"
 : > "$GSM8K_STOP_AUDIT"
 (cd "$ROOT"; "$VENV/bin/python" -m sglang.launch_server --model-path "$MODEL" --trust-remote-code --host 127.0.0.1 --port "$port" --context-length 8192 --max-running-requests 1 --mem-fraction-static .94 --disable-radix-cache --kv-cache-dtype "$dtype" --attention-backend triton --cuda-graph-max-bs-decode 1 --skip-server-warmup --log-level info) >"$dir/server.log" 2>&1 &
 local pid=$!; echo "$pid" > "$dir/server.pid"; local ready=0
 for _ in $(seq 1 360); do if curl -fsS "http://127.0.0.1:$port/health" >/dev/null 2>&1; then ready=1; break; fi; if ! kill -0 "$pid" 2>/dev/null; then tail -100 "$dir/server.log"; return 2; fi; sleep 3; done
 [[ $ready == 1 ]] || { echo "server readiness timeout: $arm" >&2; return 3; }
 OPENAI_API_KEY=unused "$VENV/bin/python" "$ROOT/control/gemma4-e4b-rtx3090-hicache/runs/gsm8k_lm_eval.py" \
   --model gsm8k-gemma-completions \
   --model_args "model=google/gemma-4-E4B-it-qat-w4a16-ct,base_url=http://127.0.0.1:${port}/v1/completions,tokenizer=$MODEL,tokenizer_backend=huggingface,tokenized_requests=false,trust_remote_code=true,timeout=1800,max_gen_toks=512,max_length=8193" \
   --tasks gsm8k_official --include_path "$ROOT/control/gemma4-e4b-rtx3090-hicache/runs" \
   --apply_chat_template --fewshot_as_multiturn false --num_fewshot 5 --batch_size 1 \
   --gen_kwargs 'temperature=0.0,max_gen_toks=512' --output_path "$dir/lm-eval" --log_samples 2>&1 | tee "$dir/lm-eval.log"
 kill -TERM "$pid" 2>/dev/null || true; for _ in $(seq 1 90); do kill -0 "$pid" 2>/dev/null || break; sleep 2; done; pkill -TERM -P "$pid" 2>/dev/null || true; kill -TERM "$pid" 2>/dev/null || true; sleep 3
 ss -ltnp | grep -q ":${port}\\b" && { echo "port still open: $port" >&2; return 4; } || true
 nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader > "$dir/gpu-after.csv"
 local f; f=$(find "$dir/lm-eval" -maxdepth 2 -type f -name 'samples_gsm8k_official_*.jsonl' -print -quit); [[ -n $f ]] || { echo "missing samples $arm" >&2; return 5; }
 cp "$f" "$dir/samples.jsonl"
"$VENV/bin/python" "$ROOT/control/gemma4-e4b-rtx3090-hicache/runs/verify_stop_audit.py" "$dir/samples.jsonl" "$dir/stop-audit.jsonl" --arm "$arm" --out "$dir/stop-audit-summary.json"
 "$VENV/bin/python" - "$dir/samples.jsonl" <<'PY'
import json,sys
p=sys.argv[1]; rows=[json.loads(x) for x in open(p) if x.strip()]
assert len(rows)==1319,(len(rows),p)
assert all(len(r.get('resps',[]))==1 for r in rows)
print('verified complete GSM8K samples',len(rows))
PY
}
run_arm bf16 bf16 31175
run_arm e5m2 fp8_e5m2 31176
"$VENV/bin/python" "$ROOT/control/gemma4-e4b-rtx3090-hicache/runs/verify_gsm8k.py" "$RUN/bf16/samples.jsonl" "$RUN/e5m2/samples.jsonl" --out "$RUN/paired-scores.json"
sha256sum "$RUN"/{bf16,e5m2}/samples.jsonl > "$RUN/samples.sha256"
printf '{"run_dir":"%s","checkpoint_revision":"6cd26aaa2357fb2bad8c51699a7558a4d1a965bb","checkpoint_sha256":"19d89d2a4b3e401a3eae75ec08ab112810421a036c91d8c8226b686be7fe0c5d","dataset_test_sha256":"752adc99f23132275139f1f7be57126b08735a55daf0c56859ee6df70abafbac","dataset_train_sha256":"6043ef64147b59871f4fd3adf669c306fe0a4c27e5a5c4bfb761f3f084895a13","lm_eval":"0.4.13","context_length":8192,"max_new_tokens":512,"fewshot":5,"bos_token_id":2,"generation":"greedy temperature=0; eos/turn-end stops; strict-match #### number"}\n' "$RUN" > "$RUN/run-manifest.json"
printf '%s\n' "$RUN"
