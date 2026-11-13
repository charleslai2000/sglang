#!/usr/bin/env bash
set -Eeuo pipefail
ROOT=/home/ubuntu/workspaces/3rdparty/sglang-hicache
VENV=/home/ubuntu/venvs/sglang-3090
MODEL=/data/sglang-hicache/gemma4/model
RUNS=/data/sglang-hicache/gemma4/runs
LOCK=/tmp/f1-r16b-gpu-exclusive.lock
[[ -s "$MODEL/model.safetensors" ]] || { echo "W4A16 checkpoint missing" >&2; exit 2; }
[[ "$(sha256sum "$MODEL/model.safetensors" | awk '{print $1}')" = 19d89d2a4b3e401a3eae75ec08ab112810421a036c91d8c8226b686be7fe0c5d ]] || { echo "checkpoint SHA mismatch" >&2; exit 3; }
exec 9>"$LOCK"; flock -n 9 || { echo GPU_LOCK_BUSY >&2; exit 90; }
MODE=${1:-all}
case "$MODE" in perf) PORT=31371; CONTEXT=8192; MAX_RUNNING=16; MEM_FRACTION=.90; GRAPH_MAX=16;; capacity) PORT=31372; CONTEXT=65536; MAX_RUNNING=32; MEM_FRACTION=.94; GRAPH_MAX=32;; *) echo 'usage: run_w4a16_service.sh perf|capacity' >&2; exit 2;; esac
if ss -ltn | grep -q ":${PORT}\\b"; then echo "port $PORT busy" >&2; exit 91; fi
OUT="$RUNS/$(date -u +%Y%m%dT%H%M%SZ)-w4a16-${MODE}"
mkdir -p "$OUT"
OVERLAY="$ROOT/control/gemma4-w4a16-3090-performance-capacity/runs/overlay"
mkdir -p "$OVERLAY/sglang/kernels/ops/attention" "$OVERLAY/sglang/kernels"
cp "$ROOT/control/gemma4-w4a16-3090-performance-capacity/runs/extend_attention.py" "$OVERLAY/sglang/kernels/ops/attention/extend_attention.py"
[[ "$(sha256sum "$OVERLAY/sglang/kernels/ops/attention/extend_attention.py" | awk '{print $1}')" = 69a9f59d6817b3947feb38639d47c690e82947ead0e9af50a0200f02a4b34d4e ]] || { echo "baseline attention overlay SHA mismatch" >&2; exit 5; }
# Namespace overlay isolates the known-broken BF16 attention source while extending all other kernel packages.
export PYTHONPATH="$OVERLAY${PYTHONPATH:+:$PYTHONPATH}"
printf '%s\n' "$OUT" > /tmp/w4a16-current-run-path
export PYTHONNOUSERSITE=1
AOT=/data/sglang-hicache/g2-quasar-runs/20261110T-g2-postrope-e5m2-quality/aot-sm86-package
[[ "$(sha256sum "$AOT/sgl_kernel/sm86/common_ops.abi3.so" | awk '{print $1}')" = 22c9f5eb84e5e494df31f814aeffe5ba0aafb266fca2b56c99cfb5a3c1dea4c2 ]] || { echo "SM86 kernel artifact hash mismatch" >&2; exit 4; }
export PYTHONPATH="$AOT:$ROOT/python:/home/ubuntu/venvs/sglang-3090/lib/python3.12/site-packages:$ROOT/python/sglang/kernels/aot/python${PYTHONPATH:+:$PYTHONPATH}"
export LD_LIBRARY_PATH="$VENV/lib/python3.12/site-packages/torch/lib:/usr/local/cuda-12.9/lib64${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export SGLANG_CACHE_DIR=/data/sglang-hicache/gemma4/cache HF_HOME=/data/sglang-hicache/gemma4/hf-home
export PYTHONPATH="$ROOT/control/gemma4-w4a16-3090-performance-capacity/runs${PYTHONPATH:+:$PYTHONPATH}"
export GSM_PERF_OUT="$OUT" GSM_PERF_SOURCE_SHA="$(git -C "$ROOT" rev-parse HEAD)"
cd "$ROOT"
if [[ "$MODE" = perf ]]; then "$VENV/bin/python" control/gemma4-e4b-rtx3090-hicache-perf/runs/service_benchmark.py --prepare-only; fi
cat >"$OUT/manifest.txt" <<EOF
model=$MODEL
model_sha256=$(sha256sum "$MODEL/model.safetensors" | awk '{print $1}')
config_sha256=$(sha256sum "$MODEL/config.json" | awk '{print $1}')
source_head=$(git rev-parse HEAD)
branch=$(git branch --show-current)
source_dirty=$(test -n "$(git status --porcelain)" && echo yes || echo no)
python=$($VENV/bin/python --version 2>&1)
torch=$($VENV/bin/python -c 'import torch; print(torch.__version__)')
kv_cache_dtype=bf16
tp=1
attention_backend=triton
radix_cache=disabled
mode=$MODE
context_length=$CONTEXT
max_running_requests=$MAX_RUNNING
mem_fraction_static=$MEM_FRACTION
cuda_graph_max_bs_decode=$GRAPH_MAX
regular_sm86_common_ops=$AOT/sgl_kernel/sm86/common_ops.abi3.so
regular_sm86_common_ops_sha256=22c9f5eb84e5e494df31f814aeffe5ba0aafb266fca2b56c99cfb5a3c1dea4c2
w4a16_extend_attention_overlay=$OVERLAY/sglang/kernels/ops/attention/extend_attention.py
w4a16_extend_attention_overlay_sha256=69a9f59d6817b3947feb38639d47c690e82947ead0e9af50a0200f02a4b34d4e (HEAD^ baseline file; excludes failed uncommitted BF16_KV_COMPUTE branch)
run_scoped_sitecustomize=$ROOT/control/gemma4-w4a16-3090-performance-capacity/runs/sitecustomize.py
T004=SGLANG_GGUF_Q4_0_LLAMA_MMQ unset; W4A16 safetensors runtime path; no GGUF quantization
EOF
mkdir -p "$OUT"
"$VENV/bin/python" -m sglang.launch_server --model-path "$MODEL" --trust-remote-code --host 127.0.0.1 --port "$PORT" --context-length "$CONTEXT" --max-running-requests "$MAX_RUNNING" --mem-fraction-static "$MEM_FRACTION" --disable-radix-cache --kv-cache-dtype bf16 --attention-backend triton --cuda-graph-max-bs-decode "$GRAPH_MAX" --enable-metrics --log-level info >"$OUT/server.log" 2>&1 & SERVER_PID=$!
echo "$SERVER_PID" >"$OUT/server.pid"
nvidia-smi --query-gpu=timestamp,utilization.gpu,memory.used --format=csv --loop-ms=500 >"$OUT/gpu-samples.csv" & MONITOR_PID=$!
cleanup(){ set +e
 if [[ -n "${MONITOR_PID:-}" ]]; then kill -TERM "$MONITOR_PID" 2>/dev/null; wait "$MONITOR_PID" 2>/dev/null; fi
 if [[ -n "${SERVER_PID:-}" ]] && kill -0 "$SERVER_PID" 2>/dev/null; then kill -TERM "$SERVER_PID" 2>/dev/null; fi
 if [[ -n "${SERVER_PID:-}" ]]; then for _ in $(seq 1 60); do kill -0 "$SERVER_PID" 2>/dev/null || break; sleep 2; done; pkill -TERM -P "$SERVER_PID" 2>/dev/null; kill -TERM "$SERVER_PID" 2>/dev/null; wait "$SERVER_PID" 2>/dev/null; fi
 nvidia-smi --query-gpu=timestamp,utilization.gpu,memory.used --format=csv,noheader >"$OUT/gpu-after.csv"
 ss -ltnp | grep ":${PORT}\\b" >"$OUT/port-after.txt" 2>&1 || true
}
trap cleanup EXIT INT TERM
"$VENV/bin/python" - "$OUT" <<'PY'
import json,sys,time,urllib.request
from pathlib import Path
p=Path(sys.argv[1]);u='http://127.0.0.1:31371/health'
for _ in range(1200):
 try: urllib.request.urlopen(u,timeout=2).read();break
 except Exception: time.sleep(1)
else:
 raise SystemExit('service startup timeout; inspect server.log')
(p/'ready.json').write_text(json.dumps({'ready_epoch':time.time(),'pid':int((p/'server.pid').read_text())})+'\n')
PY
curl -fsS "http://127.0.0.1:$PORT/model_info" >"$OUT/model-info.json"
if [[ "$MODE" = perf ]]; then
  "$VENV/bin/python" control/gemma4-e4b-rtx3090-hicache-perf/runs/service_benchmark.py --run
else
  export W4A16_URL="http://127.0.0.1:$PORT/generate" W4A16_CAPACITY_ROUNDS=1 W4A16_CONTEXT_LENGTHS="4096,8192,16384,32767"
  "$VENV/bin/python" control/gemma4-w4a16-3090-performance-capacity/runs/c32_capacity.py
fi
