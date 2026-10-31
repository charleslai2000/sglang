#!/usr/bin/env bash
set -euo pipefail
repo=/home/ubuntu/workspaces/3rdparty/sglang-hicache
venv=/home/ubuntu/venvs/sglang-3090
model=/data/sglang-hicache/gemma4/model
out="/data/sglang-hicache/gemma4/runs/$(date -u +%Y%m%dT%H%M%SZ)-radix8k-prefix-benchmark"
mkdir -p "$out"
max_running_requests=${RADIX8K_MAX_RUNNING_REQUESTS:-16}
decode_graph_max_bs=${RADIX8K_DECODE_GRAPH_MAX_BS:-16}
decode_graph_bs=${RADIX8K_DECODE_GRAPH_BS:-}
benchmark_concurrency=${RADIX8K_BENCHMARK_CONCURRENCY:-}
exec 9>/tmp/f1-r16b-gpu-exclusive.lock
flock -n 9 || { echo GPU-lock-unavailable >&2; exit 90; }
trap 'kill -TERM "${monitor:-}" "${pid:-}" 2>/dev/null || true; sleep 3; pkill -TERM -P "${pid:-0}" 2>/dev/null || true; nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader >"$out/gpu-after.csv" 2>/dev/null || true' EXIT INT TERM
printf '%s\n' "$out" > /tmp/radix8k-current-run-path
export PYTHONPATH="$repo/python:/data/sglang-hicache/gemma4/aot-sm86-build:$repo/3rdparty/sglang/python/sglang/kernels/aot/python${PYTHONPATH:+:$PYTHONPATH}"
export LD_LIBRARY_PATH="$venv/lib/python3.12/site-packages/torch/lib:/usr/local/cuda-12.9/lib64${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export SGLANG_CACHE_DIR=/data/sglang-hicache/gemma4/cache HF_HOME=/data/sglang-hicache/gemma4/hf-home RADIX8K_OUT="$out" SGLANG_FORCE_STREAM_INTERVAL=1
cp /tmp/radix8k/fixture.json "$out/fixture.json"; cp /tmp/radix8k/fixture.sha256 "$out/fixture.sha256"
cd "$repo"
graph_bs_args=()
if [[ -n "$decode_graph_bs" ]]; then
  read -r -a graph_bs_args <<< "$decode_graph_bs"
fi
server_args=(--model-path "$model" --trust-remote-code --host 127.0.0.1 --port 31371 --context-length 8450 --max-running-requests "$max_running_requests" --mem-fraction-static .90 --kv-cache-dtype bf16 --attention-backend triton --cuda-graph-max-bs-decode "$decode_graph_max_bs" --enable-metrics --enable-forward-pass-metrics --enable-request-time-stats-logging --log-level info)
if (( ${#graph_bs_args[@]} )); then
  server_args+=(--cuda-graph-bs-decode "${graph_bs_args[@]}")
fi
"$venv/bin/python" -m sglang.launch_server "${server_args[@]}" >"$out/server.log" 2>&1 & pid=$!
echo "$pid" >"$out/server.pid"
nvidia-smi --query-gpu=timestamp,utilization.gpu,memory.used --format=csv --loop-ms=500 >"$out/gpu-samples.csv" & monitor=$!
"$venv/bin/python" - "$out" <<'PY'
import sys,time,urllib.request
from pathlib import Path
p=Path(sys.argv[1]);url='http://127.0.0.1:31371/health'
for _ in range(180):
 try: urllib.request.urlopen(url,timeout=2).read();p.joinpath('ready').write_text(str(time.time()));break
 except Exception:time.sleep(5)
else:raise SystemExit('health timeout')
PY
"$venv/bin/python" - "$out" <<'PY'
import json,sys,urllib.request
from pathlib import Path
p=Path(sys.argv[1]);f=json.load(open(p/'fixture.json'))
def post(ids,rid,new_tokens):
 b={'rid':rid,'input_ids':[ids],'sampling_params':{'temperature':0,'top_p':1,'max_new_tokens':new_tokens,'min_new_tokens':new_tokens,'logit_bias':{'1':-100,'105':-100,'106':-100},'ignore_eos':False,'stop':[],'stop_strs':[],'stop_token_ids':[]},'return_token_ids':True}
 q=urllib.request.Request('http://127.0.0.1:31371/generate',data=json.dumps(b).encode(),headers={'Content-Type':'application/json'})
 o=json.load(urllib.request.urlopen(q,timeout=1800));o=o[0] if isinstance(o,list) and len(o)==1 else o
 (p/(rid+'.json')).write_text(json.dumps(o,indent=2)+'\n')
 return o
primer=post(f['prefix_ids'],'radix8k-perf-primer',1)
if primer.get('meta_info',{}).get('completion_tokens') != 1: raise RuntimeError('prefix primer did not complete')
validation=post(f['prompts']['validation'],'radix8k-perf-validation',256)
meta=validation.get('meta_info',{})
if len(validation.get('output_ids',[])) != 256: raise RuntimeError(f"validation output={len(validation.get('output_ids',[]))}")
if meta.get('cached_tokens') != 7168: raise RuntimeError(f"validation cached_tokens={meta.get('cached_tokens')}")
print(json.dumps({'primer_meta':primer.get('meta_info'),'validation_meta':meta},default=str),flush=True)
PY
if [[ -n "$benchmark_concurrency" ]]; then
  read -r -a benchmark_args <<< "$benchmark_concurrency"
  "$venv/bin/python" "$repo/control/gemma4-e4b-rtx3090-radix-8k-perf/runs/radix8k_benchmark.py" --run --accepted-validation --concurrency "${benchmark_args[@]}"
else
  "$venv/bin/python" "$repo/control/gemma4-e4b-rtx3090-radix-8k-perf/runs/radix8k_benchmark.py" --run --accepted-validation
fi
printf '%s\n' "$out" > /tmp/radix8k-run-path

kill -TERM "$pid";for _ in $(seq 1 60);do kill -0 "$pid" 2>/dev/null||break;sleep 2;done
pkill -TERM -P "$pid" 2>/dev/null||true;kill -TERM "$pid" 2>/dev/null||true;wait "$pid"||true
kill -TERM "$monitor" 2>/dev/null||true;wait "$monitor" 2>/dev/null||true
unset pid monitor
nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader >"$out/gpu-after.csv"
printf '%s\n' "$out"
