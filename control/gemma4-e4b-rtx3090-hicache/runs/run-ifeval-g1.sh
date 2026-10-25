#!/usr/bin/env bash
set -euo pipefail

ROOT=/home/ubuntu/workspaces/3rdparty/sglang-hicache
VENV=/home/ubuntu/venvs/sglang-3090
DATA=/data/sglang-hicache/gemma4
OUT=${OUT:-$DATA/runs/$(date -u +%Y%m%dT%H%M%SZ)-ifeval-g1}
LOCK=/tmp/f1-r16b-gpu-exclusive.lock
mkdir -p "$OUT"
exec 9>"$LOCK"
flock -n 9 || { echo GPU-lock-unavailable >&2; exit 90; }
export PYTHONNOUSERSITE=1
export PYTHONPATH="$ROOT/python:$DATA/aot-sm86-build:$ROOT/3rdparty/sglang/python/sglang/kernels/aot/python:$ROOT/control/gemma4-e4b-rtx3090-hicache/runs${PYTHONPATH:+:$PYTHONPATH}"
export LD_LIBRARY_PATH="$VENV/lib/python3.12/site-packages/torch/lib:/usr/local/cuda-12.9/lib64${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export SGLANG_CACHE_DIR="$DATA/cache" HF_HOME="$DATA/cache/hf-home"
export HF_DATASETS_CACHE="$DATA/cache/datasets"
export GEMMA4_MODEL_IDENTITY='{"model_revision":"6cd26aaa2357fb2bad8c51699a7558a4d1a965bb","model_sha256":"19d89d2a4b3e401a3eae75ec08ab112810421a036c91d8c8226b686be7fe0c5d"}'

MODEL="$DATA/model"
DATASET="$DATA/ifeval/google_ifeval_train.jsonl"
printf '%s\n' "$(date -u +%FT%TZ)" > "$OUT/start-utc.txt"
sha256sum "$DATASET" | tee "$OUT/ifeval-data.sha256"
wc -l "$DATASET" | tee "$OUT/ifeval-data-lines.txt"

cleanup() {
  local p
  for p in $(pgrep -f 'sglang.launch_server.*--port (31165|31166)' || true); do
    kill -TERM "$p" 2>/dev/null || true
  done
  sleep 2
  nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader > "$OUT/gpu-cleanup.csv" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

summarize_samples() {
  local file="$1" out="$2" arm="$3"
  "$VENV/bin/python" - "$file" "$out" "$arm" <<'PY'
import json,sys
from pathlib import Path
p,out,arm=sys.argv[1:]
rows=[json.loads(x) for x in Path(p).read_text().splitlines() if x.strip()]
assert len(rows)==541,(arm,len(rows))
for row in rows:
    row["kv_arm"]=arm
Path(out).write_text("\n".join(json.dumps(x,ensure_ascii=False) for x in rows)+"\n")
print(arm,"rows",len(rows))
PY
}

run_arm() {
  local arm="$1" dtype="$2" port="$3" dir="$OUT/$1"
  mkdir -p "$dir"
  printf '%s\n' "$dtype" > "$dir/kv-dtype.txt"
  (cd "$ROOT"; "$VENV/bin/python" -m sglang.launch_server \
    --model-path "$MODEL" --trust-remote-code --host 127.0.0.1 --port "$port" \
    --context-length 131072 --max-running-requests 1 --mem-fraction-static .94 \
    --disable-radix-cache --kv-cache-dtype "$dtype" --attention-backend triton \
    --cuda-graph-max-bs-decode 1 --skip-server-warmup --log-level info) \
    >"$dir/server.log" 2>&1 &
  local pid=$!; echo "$pid" > "$dir/server.pid"
  local ready=0
  for _ in $(seq 1 360); do
    if curl -fsS "http://127.0.0.1:$port/health" >/dev/null 2>&1; then ready=1; break; fi
    if ! kill -0 "$pid" 2>/dev/null; then tail -100 "$dir/server.log"; return 2; fi
    sleep 3
  done
  if [[ "$ready" != 1 ]]; then echo "server readiness timeout: $arm" >&2; return 3; fi

  printf '%s\n' "$pid" > "$dir/server-pid.txt"
  cp "$dir/server.log" "$dir/server-ready.log"
  local eval_status=0
  OPENAI_API_KEY=unused LM_EVAL_MODEL=gemma-chat-preserve-messages \
    "$VENV/bin/python" "$ROOT/control/gemma4-e4b-rtx3090-hicache/runs/ifeval_lm_eval.py" run \
      --model gemma-chat-preserve-messages \
      --model_args "model=google/gemma-4-E4B-it-qat-w4a16-ct,base_url=http://127.0.0.1:${port}/v1/chat/completions,tokenizer=${MODEL},tokenizer_backend=huggingface,tokenized_requests=false,trust_remote_code=true,timeout=1800,max_gen_toks=1280,max_length=131073" \
      --tasks ifeval_official \
      --include_path "$ROOT/control/gemma4-e4b-rtx3090-hicache/runs" \
      --apply_chat_template --fewshot_as_multiturn false --num_fewshot 0 --batch_size 1 \
      --gen_kwargs 'temperature=0.0,max_gen_toks=1280,until=[]' \
      --output_path "$dir/lm-eval" --log_samples \
      2>&1 | tee "$dir/lm-eval.log" || eval_status=$?

  kill -TERM "$pid" 2>/dev/null || true
  for _ in $(seq 1 90); do kill -0 "$pid" 2>/dev/null || break; sleep 2; done
  pkill -TERM -P "$pid" 2>/dev/null || true
  kill -TERM "$pid" 2>/dev/null || true
  sleep 3
  if ss -ltnp | grep -q ":${port}\\b"; then echo "port $port still listening" >&2; return 4; fi
  nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader > "$dir/gpu-after.csv"
  if [[ "$eval_status" -ne 0 ]]; then return "$eval_status"; fi
  local samples
  samples=$(find "$dir/lm-eval" -maxdepth 2 -type f -name 'samples_ifeval_official_*.jsonl' -print -quit)
  [[ -n "$samples" ]] || { echo "missing harness sample log for $arm" >&2; return 5; }
  summarize_samples "$samples" "$dir/samples.jsonl" "$arm"
}

run_arm bf16 bf16 31165
run_arm e5m2 fp8_e5m2 31166
printf '%s\n' "$(date -u +%FT%TZ)" > "$OUT/end-utc.txt"
nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader > "$OUT/gpu-after.csv"
"$VENV/bin/python" "$ROOT/control/gemma4-e4b-rtx3090-hicache/runs/verify-ifeval-g1.py" \
  "$OUT/bf16/samples.jsonl" "$OUT/e5m2/samples.jsonl" \
  --out "$OUT/paired-scores.json"
printf '%s\n' "$OUT"
