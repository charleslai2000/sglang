#!/usr/bin/env bash
set -Eeuo pipefail
ROOT=/home/ubuntu/workspaces/3rdparty/sglang-hicache
RUN=/data/sglang-hicache/g2-quasar-runs/20261106T093500Z-quasar-gsm8k-g1protocol
MODEL=/data/models/gemma4-quasar-q4_0/gemma-4-E4B-it-QUASAR-Q4_0.gguf
exec 9>/tmp/f1-r16b-gpu-exclusive.lock
flock -n 9 || { echo GPU_LOCK_BUSY; exit 90; }
export PYTHONNOUSERSITE=1
export PYTHONPATH="/tmp/g2-quality-head-kernel:/data/sglang-hicache/g2-quasar-runs/aot-sm86-package:$ROOT/../../../../python:/home/ubuntu/venvs/sglang-3090/lib/python3.12/site-packages:/home/ubuntu/workspaces/3rdparty/sglang-hicache/python:/home/ubuntu/workspaces/3rdparty/sglang-hicache/python/sglang/kernels/aot/python"
export SGLANG_ENABLE_JIT_DEEPGEMM=0
PID=
cleanup(){ if [[ -n ${PID:-} ]]; then kill -TERM -- -"$PID" 2>/dev/null || kill -TERM "$PID" 2>/dev/null || true; fi; for p in $(pgrep -f 'sglang.launch_server.*--port 31221' || true); do kill -TERM "$p" 2>/dev/null || true; done; sleep 5; nvidia-smi --query-gpu=memory.used,utilization.gpu --format=csv,noheader > "$RUN/diag-gpu-after.csv" 2>/dev/null || true; }
trap cleanup EXIT INT TERM
(cd /tmp; setsid /home/ubuntu/venvs/sglang-3090/bin/python -m sglang.launch_server --model-path "$MODEL" --tokenizer-path "$MODEL" --load-format gguf --quantization gguf --dtype bfloat16 --kv-cache-dtype bf16 --context-length 8192 --mem-fraction-static .88 --chunked-prefill-size 2048 --attention-backend triton --disable-prefill-cuda-graph --disable-decode-cuda-graph --disable-radix-cache --max-running-requests 1 --host 127.0.0.1 --port 31221 --random-seed 666360643 --log-level info) >"$RUN/diag-server.log" 2>&1 &
PID=$!; ready=0
for _ in $(seq 1 720); do if curl -fsS http://127.0.0.1:31221/model_info >"$RUN/diag-model-info.json" 2>/dev/null; then ready=1; break; fi; if ! kill -0 "$PID" 2>/dev/null; then tail -80 "$RUN/diag-server.log"; exit 2; fi; sleep 1; done
[[ $ready == 1 ]] || exit 3
/home/ubuntu/venvs/sglang-3090/bin/python "$ROOT/control/g2-rtx3090-quasar-q4_0-fp8kv/replay_gsm8k_selected.py" --base-url http://127.0.0.1:31221 --fixture "$RUN/diagnostic-14.jsonl" --out "$RUN/diagnostic-14-cap2048.json" --max-tokens 2048
