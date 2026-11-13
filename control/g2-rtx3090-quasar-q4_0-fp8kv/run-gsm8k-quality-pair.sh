#!/usr/bin/env bash
set -Eeuo pipefail
ROOT=/home/ubuntu/workspaces/3rdparty/sglang-hicache
RUNS=/data/sglang-hicache/g2-quasar-runs
MODEL=/data/models/gemma4-quasar-q4_0/gemma-4-E4B-it-QUASAR-Q4_0.gguf
LOCK=/tmp/f1-r16b-gpu-exclusive.lock
BASE=${G2_RUN_TAG:-$(date -u +%Y%m%dT%H%M%SZ)-quasar-gsm8k}
mkdir -p "$RUNS"
exec 9>"$LOCK"; flock -n 9 || { echo GPU_LOCK_BUSY >&2; exit 90; }
export PYTHONNOUSERSITE=1
export PYTHONPATH="$RUNS/aot-sm86-package:$ROOT/python:/home/ubuntu/venvs/sglang-3090/lib/python3.12/site-packages:$ROOT/python/sglang/kernels/aot/python"
export SGLANG_ENABLE_JIT_DEEPGEMM=0
cleanup(){
  for port in 31221 31222; do
    for p in $(pgrep -f "sglang.launch_server.*--port $port" || true); do kill -TERM "$p" 2>/dev/null || true; done
  done
  sleep 4
  for port in 31221 31222; do ss -ltnp | grep -q ":${port}\\b" && echo "PORT_REMAINS $port" >&2 || true; done
  nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader > "$RUNS/$BASE-gpu-final.csv" 2>/dev/null || true
}
trap cleanup EXIT INT TERM
run_arm(){
  local arm=$1 dtype=$2 port=$3 out="$RUNS/$BASE-$1"; mkdir -p "$out"
  local ov=/tmp/g2-quality-head-kernel
  PYTHONPATH="$ov:$PYTHONPATH" /home/ubuntu/venvs/sglang-3090/bin/python - <<'PY'
import sglang.kernels.ops.attention.extend_attention as e
from pathlib import Path
assert e.__file__.startswith('/tmp/g2-quality-head-kernel/'),e.__file__
assert 'BF16_KV_COMPUTE' not in Path(e.__file__).read_text()
print('HEAD_KERNEL_OVERLAY',e.__file__)
PY
  (cd /tmp; PYTHONPATH="$ov:$PYTHONPATH" setsid /home/ubuntu/venvs/sglang-3090/bin/python -m sglang.launch_server \
    --model-path "$MODEL" --tokenizer-path "$MODEL" --load-format gguf --quantization gguf \
    --dtype bfloat16 --kv-cache-dtype "$dtype" --context-length 8192 \
    --mem-fraction-static 0.88 --chunked-prefill-size 2048 --attention-backend triton \
    --disable-prefill-cuda-graph --disable-decode-cuda-graph --disable-radix-cache \
    --max-running-requests 4 --host 127.0.0.1 --port "$port" --random-seed 666360643 --log-level info) >"$out/server.log" 2>&1 &
  local pid=$!; echo "$pid" >"$out/server.pid"; local ready=0
  for _ in $(seq 1 720); do if curl -fsS "http://127.0.0.1:$port/model_info" >"$out/model-info.json" 2>/dev/null; then ready=1; break; fi; if ! kill -0 "$pid" 2>/dev/null; then tail -100 "$out/server.log"; return 2; fi; sleep 1; done
  [[ $ready == 1 ]] || { echo "server readiness timeout $arm" >&2; return 3; }
  /home/ubuntu/venvs/sglang-3090/bin/python "$ROOT/control/g2-rtx3090-quasar-q4_0-fp8kv/eval_paired_gsm8k.py" --arm "$arm" --base-url "http://127.0.0.1:$port" --out "$out/eval" --workers 4 | tee "$out/eval-driver.log"
  for p in $(pgrep -f "sglang.launch_server.*--port $port" || true); do kill -TERM "$p" 2>/dev/null || true; done
  for _ in $(seq 1 120); do ss -ltnp | grep -q ":${port}\\b" || break; sleep 1; done
  ss -ltnp | grep -q ":${port}\\b" && { echo "port still listening $port" >&2; return 4; }
  nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader >"$out/gpu-after.csv"
}
run_arm bf16 bf16 31221
run_arm e5m2 fp8_e5m2 31222
/home/ubuntu/venvs/sglang-3090/bin/python "$ROOT/control/g2-rtx3090-quasar-q4_0-fp8kv/compare_paired_gsm8k.py" "$RUNS/$BASE-bf16/eval/results.jsonl" "$RUNS/$BASE-e5m2/eval/results.jsonl" --out "$RUNS/$BASE/paired.json"
printf '%s\n' "$RUNS/$BASE-bf16" "$RUNS/$BASE-e5m2"
