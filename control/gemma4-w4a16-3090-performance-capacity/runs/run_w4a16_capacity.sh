#!/usr/bin/env bash
set -Eeuo pipefail
ROOT=/home/ubuntu/workspaces/3rdparty/sglang-hicache; VENV=/home/ubuntu/venvs/sglang-3090; MODEL=/data/sglang-hicache/gemma4/model; PORT=31372
AOT=/data/sglang-hicache/g2-quasar-runs/20261110T-g2-postrope-e5m2-quality/aot-sm86-package
LOCK=/tmp/f1-r16b-gpu-exclusive.lock; RUNS=/data/sglang-hicache/gemma4/runs
[[ "$(sha256sum "$MODEL/model.safetensors"|awk '{print $1}')" = 19d89d2a4b3e401a3eae75ec08ab112810421a036c91d8c8226b686be7fe0c5d ]]
[[ "$(sha256sum "$AOT/sgl_kernel/sm86/common_ops.abi3.so"|awk '{print $1}')" = 22c9f5eb84e5e494df31f814aeffe5ba0aafb266fca2b56c99cfb5a3c1dea4c2 ]]
exec 9>"$LOCK"; flock -n 9 || { echo GPU_LOCK_BUSY >&2; exit 90; }
ss -ltn | grep -q ":${PORT}\\b" && { echo PORT_BUSY >&2; exit 91; } || true
OUT="$RUNS/$(date -u +%Y%m%dT%H%M%SZ)-w4a16-c32-capacity"; mkdir -p "$OUT"; echo "$OUT" >/tmp/w4a16-capacity-run-path
OVERLAY="$ROOT/control/gemma4-w4a16-3090-performance-capacity/runs"; export PYTHONNOUSERSITE=1
export PYTHONPATH="$OVERLAY:/data/sglang-hicache/g2-quasar-runs/20261110T-g2-postrope-e5m2-quality/aot-sm86-package:$ROOT/python:$VENV/lib/python3.12/site-packages:$ROOT/python/sglang/kernels/aot/python"
export LD_LIBRARY_PATH="$VENV/lib/python3.12/site-packages/torch/lib:/usr/local/cuda-12.9/lib64${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export SGLANG_CACHE_DIR=/data/sglang-hicache/gemma4/cache HF_HOME=/data/sglang-hicache/gemma4/hf-home GSM_PERF_OUT="$OUT" W4A16_URL="http://127.0.0.1:$PORT/generate"
cat >"$OUT/manifest.txt" <<EOF
model_sha256=$(sha256sum "$MODEL/model.safetensors"|awk '{print $1}')
config_sha256=$(sha256sum "$MODEL/config.json"|awk '{print $1}')
source_head=$(git -C "$ROOT" rev-parse HEAD)
mode=c32-capacity
context_length=65536
max_running_requests=32
mem_fraction_static=0.94
kv_cache_dtype=bf16
attention_backend=triton
radix_cache=disabled
tp=1
cuda_graph_decode_max_bs=32
capacity_requests=32 independent random input_ids; 4096/8192/16384/32767 each; each requires actual prefill and >=256 decode tokens
T004=disabled; safetensors W4A16 only
normal_sm86_common_ops_sha256=22c9f5eb84e5e494df31f814aeffe5ba0aafb266fca2b56c99cfb5a3c1dea4c2
clean_attention_override_sha256=69a9f59d6817b3947feb38639d47c690e82947ead0e9af50a0200f02a4b34d4e
EOF
cd "$ROOT"
"$VENV/bin/python" -m sglang.launch_server --model-path "$MODEL" --trust-remote-code --host 127.0.0.1 --port "$PORT" --context-length 65536 --max-running-requests 32 --mem-fraction-static .94 --disable-radix-cache --kv-cache-dtype bf16 --attention-backend triton --cuda-graph-max-bs-decode 32 --enable-metrics --log-level info >"$OUT/server.log" 2>&1 & PID=$!; echo "$PID" >"$OUT/server.pid"
nvidia-smi --query-gpu=timestamp,utilization.gpu,memory.used --format=csv --loop-ms=500 >"$OUT/gpu-samples.csv" & MON=$!
cleanup(){ set +e; kill -TERM "$MON" "$PID" 2>/dev/null; sleep 3; pkill -TERM -P "$PID" 2>/dev/null; kill -TERM "$PID" 2>/dev/null; wait "$PID" 2>/dev/null; wait "$MON" 2>/dev/null; nvidia-smi --query-gpu=timestamp,utilization.gpu,memory.used --format=csv,noheader >"$OUT/gpu-after.csv"; ss -ltnp|grep ":${PORT}\\b" >"$OUT/port-after.txt" 2>&1 || true; }
trap cleanup EXIT INT TERM
"$VENV/bin/python" -u - "$OUT" <<'PY'
import sys,time,urllib.request
from pathlib import Path
p=Path(sys.argv[1]); url='http://127.0.0.1:31372/health'
for _ in range(900):
 try: urllib.request.urlopen(url,timeout=3).read(); break
 except Exception: time.sleep(1)
else: raise SystemExit('health timeout; inspect server.log')
(p/'ready.json').write_text(str(time.time())+'\n')
PY
curl -fsS "http://127.0.0.1:$PORT/model_info" >"$OUT/model-info.json"
"$VENV/bin/python" -u control/gemma4-w4a16-3090-performance-capacity/runs/c32_capacity.py
