#!/usr/bin/env bash
set -Eeuo pipefail
ROOT=/home/ubuntu/workspaces/3rdparty/sglang-hicache; VENV=/home/ubuntu/venvs/sglang-3090; DATA=/data/sglang-hicache/gemma4; MODEL=$DATA/model; OUT=$DATA/runs/20261115T-g1-e5m2-boundary-new; LOCK=/tmp/f1-r16b-gpu-exclusive.lock; AOT=/data/sglang-hicache/g2-quasar-runs/20261110T-g2-postrope-e5m2-quality/aot-sm86-package; OVERLAY=$ROOT/control/gemma4-w4a16-3090-performance-capacity/runs/overlay
[[ $(git -C "$ROOT" rev-parse HEAD) == 6b328d0a860d6aa507f3e2ecd625c9d6c4cb8539 ]]
[[ $(sha256sum "$MODEL/model.safetensors" | awk '{print $1}') == 19d89d2a4b3e401a3eae75ec08ab112810421a036c91d8c8226b686be7fe0c5d ]]
[[ $(sha256sum "$AOT/sgl_kernel/sm86/common_ops.abi3.so" | awk '{print $1}') == 22c9f5eb84e5e494df31f814aeffe5ba0aafb266fca2b56c99cfb5a3c1dea4c2 ]]
[[ $(sha256sum "$OVERLAY/sglang/kernels/ops/attention/extend_attention.py" | awk '{print $1}') == 69a9f59d6817b3947feb38639d47c690e82947ead0e9af50a0200f02a4b34d4e ]]
mkdir -p "$OUT"; exec 9>"$LOCK"; flock -n 9 || { echo GPU_LOCK_BUSY >&2; exit 90; }
export PYTHONNOUSERSITE=1 PYTHONPATH="$ROOT/control/gemma4-w4a16-3090-performance-capacity/runs:$AOT:$ROOT/python:$VENV/lib/python3.12/site-packages:$ROOT/python/sglang/kernels/aot/python:$OVERLAY"
export LD_LIBRARY_PATH="$VENV/lib/python3.12/site-packages/torch/lib:/usr/local/cuda-12.9/lib64"
export SGLANG_CACHE_DIR="$DATA/cache" HF_HOME="$DATA/cache/hf-home" HF_DATASETS_CACHE="$DATA/cache/datasets"
cd "$ROOT"
for DTYPE in bfloat16 fp8_e5m2; do
  PORT=31179; [[ $DTYPE == bfloat16 ]] || PORT=31180
  RUN=$OUT/$DTYPE; mkdir -p "$RUN"; PID=
  cleanup_one() { set +e; [[ -z "$PID" ]] || { kill -TERM "$PID" 2>/dev/null; wait "$PID" 2>/dev/null; }; nvidia-smi --query-gpu=timestamp,utilization.gpu,memory.used --format=csv,noheader > "$RUN/gpu-after.csv"; ss -ltnp | grep ":$PORT\\b" > "$RUN/port-after.txt" 2>&1; }
  trap cleanup_one EXIT INT TERM
  export G1_LOGITS_CAPTURE="$RUN/logits"
  "$VENV/bin/python" "$ROOT/control/gemma4-w4a16-3090-performance-capacity/runs/server_with_logits_capture.py" --model-path "$MODEL" --trust-remote-code --host 127.0.0.1 --port "$PORT" --context-length 2048 --max-running-requests 1 --max-total-tokens 4096 --mem-fraction-static .90 --disable-radix-cache --kv-cache-dtype "$DTYPE" --attention-backend triton --cuda-graph-max-bs-decode 1 --skip-server-warmup --log-level info > "$RUN/server.log" 2>&1 & PID=$!
  ready=0; for _ in $(seq 1 1200); do if curl -fsS "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; then ready=1; break; fi; kill -0 "$PID" 2>/dev/null || { tail -100 "$RUN/server.log"; exit 2; }; sleep 1; done; [[ $ready == 1 ]]
  for N in 512 513 514; do "$VENV/bin/python" "$ROOT/control/gemma4-w4a16-3090-performance-capacity/runs/boundary_server_probe.py" --url "http://127.0.0.1:$PORT" --dtype "$DTYPE" --fixture "$OUT/n$N.json" --output "$RUN/n$N.json" --capture-prefix "$RUN/logits"; done
  cleanup_one; trap - EXIT INT TERM; PID=
done
