#!/usr/bin/env bash
set -euo pipefail
repo=/home/ubuntu/workspaces/3rdparty/sglang-hicache
venv=/home/ubuntu/venvs/sglang-3090
model=/data/sglang-hicache/gemma4/model
kind=${RADIX8K_PROFILE_KIND:?Set RADIX8K_PROFILE_KIND=prefill|decode}
concurrency=${RADIX8K_PROFILE_CONCURRENCY:?Set RADIX8K_PROFILE_CONCURRENCY=16|24|32}
seconds=${RADIX8K_PROFILE_SECONDS:-180}
capture_range=${RADIX8K_CAPTURE_RANGE:-none}
capture_end=()
[[ "$capture_range" == none ]] || capture_end=(--capture-range-end=stop)
out="/data/sglang-hicache/gemma4/runs/$(date -u +%Y%m%dT%H%M%SZ)-radix8k-profiler-${kind}-c${concurrency}"
mkdir -p "$out"
exec 9>/tmp/f1-r16b-gpu-exclusive.lock
flock -n 9 || { echo GPU-lock-unavailable >&2; exit 90; }
nsys_pid= server_pid= monitor_pid=
cleanup() {
  if [[ -n "$server_pid" ]]; then
    kill -TERM "$server_pid" 2>/dev/null || true
    for _ in $(seq 1 45); do kill -0 "$server_pid" 2>/dev/null || break; sleep 2; done
    pkill -TERM -P "$server_pid" 2>/dev/null || true
    kill -TERM "$server_pid" 2>/dev/null || true
    wait "$server_pid" 2>/dev/null || true
  fi
  if [[ -n "$monitor_pid" ]]; then kill -TERM "$monitor_pid" 2>/dev/null || true; wait "$monitor_pid" 2>/dev/null || true; fi
  nvidia-smi --query-gpu=timestamp,utilization.gpu,memory.used --format=csv,noheader >"$out/gpu-after.csv" 2>/dev/null || true
  if [[ -n "$nsys_pid" ]]; then wait "$nsys_pid" 2>/dev/null || true; fi
}
trap cleanup EXIT INT TERM
printf '%s\n' "$out" > /tmp/radix8k-profiler-current-run
export PYTHONPATH="$repo/python:/data/sglang-hicache/gemma4/aot-sm86-build:$repo/3rdparty/sglang/python/sglang/kernels/aot/python${PYTHONPATH:+:$PYTHONPATH}"
export LD_LIBRARY_PATH="$venv/lib/python3.12/site-packages/torch/lib:/usr/local/cuda-12.9/lib64${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export SGLANG_CACHE_DIR=/data/sglang-hicache/gemma4/cache HF_HOME=/data/sglang-hicache/gemma4/hf-home
export SGLANG_RADIX8K_PROFILER_NVTX=1 SGLANG_ENABLE_NVTX_SCHEDULER=1 SGLANG_ENABLE_METRICS_DEVICE_TIMER=1
export SGLANG_ENABLE_REQUEST_TIME_STATS_LOGGING=1 RADIX8K_OUT="$out" SGLANG_FORCE_STREAM_INTERVAL=1 SGLANG_RADIX8K_PROFILER_HOLD_PREFILL=1
cp /tmp/radix8k/fixture.json "$out/fixture.json"
cp /tmp/radix8k/fixture.sha256 "$out/fixture.sha256"
git -C "$repo" rev-parse HEAD > "$out/repo-head"
exec > >(tee -a "$out/driver.log") 2>&1
cd "$repo"
graph_bs=(1 2 4 8 12 16 24 32)
server_args=(--model-path "$model" --trust-remote-code --host 127.0.0.1 --port 31371 --context-length 8450 --max-running-requests "$concurrency" --prefill-max-requests "$concurrency" --max-prefill-tokens 16384 --chunked-prefill-size 8192 --mem-fraction-static .90 --kv-cache-dtype bf16 --attention-backend triton --cuda-graph-max-bs-decode 32 --cuda-graph-bs-decode "${graph_bs[@]}" --enable-metrics --enable-forward-pass-metrics --enable-request-time-stats-logging --log-level info)
# Capture continuously through the bounded service workload; analysis joins only
# forward labels carrying the profile RID/step identity.
/opt/nvidia/nsight-compute/2025.2.1/host/target-linux-x64/nsys profile --trace=cuda,nvtx,osrt --sample=none --cpuctxsw=none --cuda-graph-trace=graph --cuda-event-trace=false --capture-range="$capture_range" "${capture_end[@]}" --force-overwrite=true -o "$out/profile" "$venv/bin/python" -m sglang.launch_server "${server_args[@]}" >"$out/nsys-launch.log" 2>&1 & nsys_pid=$!
for _ in $(seq 1 100); do
  server_pid=$(pgrep -f '[p]ython.*-m sglang.launch_server.*--port 31371' | head -1 || true)
  [[ -n "$server_pid" ]] && break
  sleep .2
done
[[ -n "$server_pid" ]] || { echo "profiled server child not found"; exit 5; }
echo "$server_pid" >"$out/server.pid"
echo "profiled service PID=$server_pid; scheduler PID will be resolved after readiness"
nvidia-smi --query-gpu=timestamp,utilization.gpu,memory.used --format=csv --loop-ms=200 >"$out/gpu-samples.csv" & monitor_pid=$!
"$venv/bin/python" - "$out" <<'PY'
import json,sys,time,urllib.request
from pathlib import Path
p=Path(sys.argv[1]); url='http://127.0.0.1:31371/health'
for _ in range(180):
 try:
  urllib.request.urlopen(url,timeout=2).read(); p.joinpath('ready').write_text(str(time.time())); break
 except Exception: time.sleep(5)
else: raise SystemExit('health timeout')
PY
echo "$server_pid" >"$out/server.pid"
scheduler_pid=$(pgrep -f "^sglang::scheduler" | head -1 || true)
[[ -n "$scheduler_pid" ]] || { echo "scheduler child not visible"; exit 7; }
echo "$scheduler_pid" >"$out/scheduler.pid"
"$venv/bin/python" - "$out" <<'PY'
import json,sys,urllib.request,os
from pathlib import Path
p=Path(sys.argv[1]); f=json.load(open(p/'fixture.json'))
def post(ids,rid,n):
 b={'rid':rid,'input_ids':[ids],'sampling_params':{'temperature':0,'top_p':1,'max_new_tokens':n,'min_new_tokens':n,'logit_bias':{'1':-100,'105':-100,'106':-100},'ignore_eos':False,'stop':[],'stop_strs':[],'stop_token_ids':[]},'return_token_ids':True}
 q=urllib.request.Request('http://127.0.0.1:31371/generate',data=json.dumps(b).encode(),headers={'Content-Type':'application/json'})
 o=json.load(urllib.request.urlopen(q,timeout=1800)); o=o[0] if isinstance(o,list) and len(o)==1 else o
 (p/(rid+'.json')).write_text(json.dumps(o,indent=2)+'\n'); return o
primer=post(f['prefix_ids'],'radix8k-profiler-primer',1)
if primer.get('meta_info',{}).get('completion_tokens') != 1: raise RuntimeError('primer failed')
if os.environ.get('RADIX8K_PROFILE_KIND') != 'decode':
 val=post(f['prompts']['validation'],'radix8k-profiler-validation',1)
 m=val.get('meta_info',{})
 if m.get('cached_tokens') != 7168: raise RuntimeError(f"invalid validation cache hit {m.get('cached_tokens')}")
 print(json.dumps({'validation':m},default=str),flush=True)
PY
if [[ "$kind" == decode ]]; then
  # Seed only the exact shared prefix; do not create 8,191-token near-duplicate hits.
  "$venv/bin/python" - "$out" <<'PY'
import json,sys,time,urllib.request
from pathlib import Path
p=Path(sys.argv[1]); f=json.load(open(p/'fixture.json'))
def post(ids,rid):
 b={'rid':rid,'input_ids':[ids],'sampling_params':{'temperature':0,'top_p':1,'max_new_tokens':1,'min_new_tokens':1,'logit_bias':{'1':-100,'105':-100,'106':-100},'ignore_eos':False,'stop':[],'stop_strs':[],'stop_token_ids':[]},'return_token_ids':True}
 q=urllib.request.Request('http://127.0.0.1:31371/generate',data=json.dumps(b).encode(),headers={'Content-Type':'application/json'})
 o=json.load(urllib.request.urlopen(q,timeout=1800)); o=o[0] if isinstance(o,list) and len(o)==1 else o
 (p/(rid+'.json')).write_text(json.dumps(o,indent=2)+'\\n'); return o
post(f['prompts']['validation'],'radix8k-profiler-prefix-primer')
PY
fi
"$venv/bin/python" "$repo/control/gemma4-e4b-rtx3090-radix-8k-profiler/runs/profile_window_client.py" --concurrency "$concurrency" --kind "$kind" --run-dir "$out" --profile-seconds "$seconds" --profile-trigger >"$out/profile-client.log"
# Stop the profiled service after the cohort, then wait for Nsight to flush/export.
cleanup
server_pid= monitor_pid=
wait "$nsys_pid" || true
nsys_pid=
printf '%s\n' "$out" > /tmp/radix8k-profiler-last-run
printf '%s\n' "$out"
