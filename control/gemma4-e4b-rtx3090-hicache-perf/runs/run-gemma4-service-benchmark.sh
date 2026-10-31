#!/usr/bin/env bash
set -euo pipefail
repo=/home/ubuntu/workspaces/3rdparty/sglang-hicache
venv=/home/ubuntu/venvs/sglang-3090
model=/data/sglang-hicache/gemma4/model
out="/data/sglang-hicache/gemma4/runs/$(date -u +%Y%m%dT%H%M%SZ)-gemma4-bf16-decode-baseline"
mkdir -p "$out"
exec 9>/tmp/f1-r16b-gpu-exclusive.lock
flock -n 9 || { echo GPU-lock-unavailable >&2; exit 90; }
trap 'kill -TERM "${monitor:-}" "${pid:-}" 2>/dev/null || true; sleep 3; pkill -TERM -P "${pid:-0}" 2>/dev/null || true; nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader >"$out/gpu-after.csv"' EXIT INT TERM
export PYTHONPATH="$repo/python:/data/sglang-hicache/gemma4/aot-sm86-build:$repo/3rdparty/sglang/python/sglang/kernels/aot/python${PYTHONPATH:+:$PYTHONPATH}"
export LD_LIBRARY_PATH="$venv/lib/python3.12/site-packages/torch/lib:/usr/local/cuda-12.9/lib64${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export SGLANG_CACHE_DIR=/data/sglang-hicache/gemma4/cache HF_HOME=/data/sglang-hicache/gemma4/hf-home
export GSM_PERF_OUT="$out" GSM_PERF_SOURCE_SHA="$(git -C "$repo" rev-parse HEAD)"
"$venv/bin/python" "$repo/control/gemma4-e4b-rtx3090-hicache-perf/runs/service_benchmark.py" --prepare-only
(cd "$repo"; "$venv/bin/python" -m sglang.launch_server --model-path "$model" --trust-remote-code --host 127.0.0.1 --port 31371 --context-length 8192 --max-running-requests 16 --mem-fraction-static .90 --disable-radix-cache --kv-cache-dtype bf16 --attention-backend triton --cuda-graph-max-bs-decode 16 --enable-metrics --log-level info) >"$out/server.log" 2>&1 & pid=$!
echo "$pid" >"$out/server.pid"
nvidia-smi --query-gpu=timestamp,utilization.gpu,memory.used --format=csv --loop-ms=500 >"$out/gpu-samples.csv" & monitor=$!
"$venv/bin/python" - "$out" <<'PY'
import json,sys,time,urllib.request
from pathlib import Path
out=Path(sys.argv[1]);url='http://127.0.0.1:31371/health'
for _ in range(360):
 try:
  urllib.request.urlopen(url,timeout=2).read();break
 except Exception: time.sleep(5)
else: raise SystemExit('service startup timeout')
(out/'ready.json').write_text(json.dumps({'ready_utc':time.time(),'pid':int((out/'server.pid').read_text())})+'\n')
PY
"$venv/bin/python" - "$out" <<'PY'
import json,subprocess,sys
from pathlib import Path
out=Path(sys.argv[1]);j=json.loads(subprocess.check_output(['curl','-fsS','http://127.0.0.1:31371/model_info'],text=True))
(out/'runtime-capacity.json').write_text(json.dumps(j,indent=2)+'\\n')
PY
"$venv/bin/python" "$repo/control/gemma4-e4b-rtx3090-hicache-perf/runs/service_benchmark.py" --run
kill -TERM "$pid"; for _ in $(seq 1 60); do kill -0 "$pid" 2>/dev/null || break; sleep 2; done
pkill -TERM -P "$pid" 2>/dev/null || true; kill -TERM "$pid" 2>/dev/null || true; wait "$pid" || true
kill -TERM "$monitor" 2>/dev/null || true; wait "$monitor" 2>/dev/null || true
unset pid monitor
nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader >"$out/gpu-after.csv"
printf '%s\n' "$out"
trap - EXIT INT TERM
