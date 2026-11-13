#!/usr/bin/env bash
set -Eeuo pipefail
OUT=/data/sglang-hicache/g2-quasar-runs/20261107T-g2-first-logits
ROOT=/home/ubuntu/workspaces/3rdparty/sglang-hicache
export PYTHONNOUSERSITE=1
export PYTHONPATH="$OUT/aot-sm86-package:$OUT/head-kernel-shadow:$ROOT/python:/home/ubuntu/venvs/sglang-3090/lib/python3.12/site-packages:$ROOT/python/sglang/kernels/aot/python"
export SGLANG_ENABLE_JIT_DEEPGEMM=0
export GEMMA4_MODEL_IDENTITY='{"model_revision":"7d6269096c9acbce4422fd1aa3a249436b01288868961e48ca9bb2541997f669","model_sha256":"7d6269096c9acbce4422fd1aa3a249436b01288868961e48ca9bb2541997f669"}'
export SGLANG_GEMMA4_CAPTURE_LOGITS=1
export SGLANG_GEMMA4_CAPTURE_LAYERS=1
export SGLANG_GEMMA4_CAPTURE_LAYER_POSITIONS=1
export SGLANG_GEMMA4_LOGITS_FILE="$OUT/closure3-logits"
export SGLANG_GEMMA4_LAYERS_FILE="$OUT/closure3-layers"
exec 9>/tmp/f1-r16b-gpu-exclusive.lock
flock -n 9 || { echo GPU_LOCK_BUSY; exit 90; }
cd /tmp
setsid /home/ubuntu/venvs/sglang-3090/bin/python -m sglang.launch_server \
  --model-path /data/models/gemma4-quasar-q4_0/gemma-4-E4B-it-QUASAR-Q4_0.gguf \
  --tokenizer-path /data/sglang-hicache/gemma4/model --load-format gguf --quantization gguf \
  --dtype bfloat16 --kv-cache-dtype bf16 --context-length 8192 --mem-fraction-static .88 \
  --chunked-prefill-size 2048 --attention-backend triton --disable-prefill-cuda-graph \
  --disable-decode-cuda-graph --disable-radix-cache --max-running-requests 1 \
  --host 127.0.0.1 --port 31223 --random-seed 666360643 --log-level info >"$OUT/closure3-server.log" 2>&1 &
PID=$!
cleanup(){ kill -TERM -- -"$PID" 2>/dev/null || true; for _ in $(seq 1 60); do kill -0 "$PID" 2>/dev/null || break; sleep 1; done; nvidia-smi --query-gpu=memory.used,utilization.gpu --format=csv,noheader >"$OUT/closure3-gpu-after.csv"; }
trap cleanup EXIT INT TERM
for _ in $(seq 1 900); do curl -fsS http://127.0.0.1:31223/model_info >"$OUT/closure3-model-info.json" 2>/dev/null && break; kill -0 "$PID" || { tail -100 "$OUT/closure2-server.log"; exit 2; }; sleep 1; done
PYTHONNOUSERSITE=1 PYTHONPATH="$ROOT/python:/home/ubuntu/venvs/sglang-3090/lib/python3.12/site-packages" /home/ubuntu/venvs/sglang-3090/bin/python "$ROOT/experiments/g2-gsm8k-root-cause-20261107/collect_closure_service.py"
