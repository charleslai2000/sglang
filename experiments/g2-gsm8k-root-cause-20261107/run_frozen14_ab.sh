#!/usr/bin/env bash
set -Eeuo pipefail
ROOT=/home/ubuntu/workspaces/3rdparty/sglang-hicache
RUN=/data/sglang-hicache/g2-quasar-runs/20261107T-g2-first-logits
MODEL=/data/models/gemma4-quasar-q4_0/gemma-4-E4B-it-QUASAR-Q4_0.gguf
PORT=${PORT:-31236}
ARM=${ARM:?Set ARM=a8 or fp32}
OUT="$RUN/diag14-$ARM"
mkdir -p "$OUT"
exec 9>/tmp/f1-r16b-gpu-exclusive.lock
flock -n 9 || { echo GPU_LOCK_BUSY; exit 90; }
export PYTHONNOUSERSITE=1
export PYTHONPATH="$RUN/aot-sm86-package:$RUN/head-kernel-shadow:$ROOT/python:/home/ubuntu/venvs/sglang-3090/lib/python3.12/site-packages:$ROOT/python/sglang/kernels/aot/python"
export SGLANG_ENABLE_JIT_DEEPGEMM=0
export GEMMA4_MODEL_IDENTITY='{"model_revision":"7d6269096c9acbce4422fd1aa3a249436b01288868961e48ca9bb2541997f669","model_sha256":"7d6269096c9acbce4422fd1aa3a249436b01288868961e48ca9bb2541997f669"}'
export SGLANG_GGUF_DISPATCH_TRACE=1
export SGLANG_GGUF_DISPATCH_TRACE_FILE="$OUT/dispatch.json"
export SGLANG_GGUF_EXTEND_PROBE_FILE="$OUT/layer0-qkv-extend-probe.pt"
export SGLANG_GGUF_EXTEND_PROBE_ROWS=1104
if [[ $ARM == fp32 ]]; then export SGLANG_GGUF_Q4_0_FP32_DEQUANT_GEMM=1; fi
export SGLANG_GGUF_EXTEND_PROBE_FILE="$OUT/layer0-qkv-extend-probe.pt"
export SGLANG_GGUF_EXTEND_PROBE_ROWS=1104
(cd /tmp; setsid /home/ubuntu/venvs/sglang-3090/bin/python -m sglang.launch_server \
 --model-path "$MODEL" --tokenizer-path /data/sglang-hicache/gemma4/model \
 --load-format gguf --quantization gguf --dtype bfloat16 --kv-cache-dtype bf16 \
 --context-length 8192 --mem-fraction-static .88 --chunked-prefill-size 2048 \
 --attention-backend triton --disable-prefill-cuda-graph --disable-decode-cuda-graph \
 --disable-radix-cache --max-running-requests 1 --host 127.0.0.1 --port "$PORT" \
 --random-seed 666360643 --log-level info) >"$OUT/server.log" 2>&1 &
PID=$!
cleanup(){ kill -TERM -- -"$PID" 2>/dev/null || true; for _ in $(seq 1 90); do kill -0 "$PID" 2>/dev/null || break; sleep 1; done; nvidia-smi --query-gpu=memory.used,utilization.gpu --format=csv,noheader >"$OUT/gpu-after.csv"; }
trap cleanup EXIT INT TERM
ready=0
for _ in $(seq 1 900); do if curl -fsS "http://127.0.0.1:$PORT/model_info" >"$OUT/model-info.json" 2>/dev/null; then ready=1; break; fi; kill -0 "$PID" 2>/dev/null || { tail -100 "$OUT/server.log"; exit 2; }; sleep 1; done
[[ $ready == 1 ]]
/home/ubuntu/venvs/sglang-3090/bin/python "$ROOT/experiments/g2-gsm8k-root-cause-20261107/eval_frozen14_ab.py" --base-url "http://127.0.0.1:$PORT" --fixture "$RUN/prompts.jsonl" --out "$OUT/results.json" --arm "$ARM"
