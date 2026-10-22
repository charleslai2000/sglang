#!/usr/bin/env bash
set -euo pipefail
repo=/home/ubuntu/workspaces/3rdparty/sglang-hicache;venv=/home/ubuntu/venvs/sglang-3090;model=/data/sglang-hicache/gemma4/model;out="/data/sglang-hicache/gemma4/runs/$(date -u +%Y%m%dT%H%M%SZ)-g1-graph-replay";mkdir -p "$out";exec 9>/tmp/f1-r16b-gpu-exclusive.lock;flock -n 9 || { echo GPU-lock-unavailable >&2;exit 90; }
export PYTHONPATH="$repo/python:/data/sglang-hicache/gemma4/aot-sm86-build:$repo/3rdparty/sglang/python/sglang/kernels/aot/python${PYTHONPATH:+:$PYTHONPATH}";export LD_LIBRARY_PATH="$venv/lib/python3.12/site-packages/torch/lib:/usr/local/cuda-12.9/lib64${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}";export SGLANG_LOG_DECODE_GRAPH_KEY=1;export SGLANG_CACHE_DIR=/data/sglang-hicache/gemma4/cache;export HF_HOME=/data/sglang-hicache/gemma4/hf-home
(cd "$repo";"$venv/bin/python" -m sglang.launch_server --model-path "$model" --trust-remote-code --host 127.0.0.1 --port 31043 --context-length 1024 --max-running-requests 4 --max-total-tokens 2048 --mem-fraction-static .82 --disable-radix-cache --kv-cache-dtype fp8_e5m2 --attention-backend triton --cuda-graph-max-bs-decode 1 --log-level info) > "$out/server.log" 2>&1 & pid=$!;echo "$pid" > "$out/server.pid"
cleanup(){ kill -TERM "$pid" 2>/dev/null || true;sleep 5;pkill -TERM -P "$pid" 2>/dev/null || true;kill -TERM "$pid" 2>/dev/null || true; };trap cleanup EXIT
for _ in $(seq 1 240);do curl -fsS http://127.0.0.1:31043/health >/dev/null 2>&1 && break;kill -0 "$pid" 2>/dev/null || { tail -50 "$out/server.log";exit 2; };sleep 5;done
GEMMA4_RUN_OUT="$out" "$venv/bin/python" - <<'PY'
import concurrent.futures,json,time,urllib.request,os
from pathlib import Path
out=Path(os.environ['GEMMA4_RUN_OUT']);prompt=[6974,886,2822,13315,1003,506,7217,236761];url='http://127.0.0.1:31043/v1/completions'
def req(i):
 body={'prompt':prompt,'max_tokens':8,'temperature':0.0};r=urllib.request.Request(url,data=json.dumps(body).encode(),headers={'Content-Type':'application/json'});return json.loads(urllib.request.urlopen(r,timeout=300).read())
rows=[]
for i in range(4):
 with concurrent.futures.ThreadPoolExecutor(max_workers=4) as e: rs=list(e.map(req,range(4)))
 time.sleep(.5)
 logs=(out/'server.log').read_text();count=logs.count('Decode graph replay:')
 rows.append({'round':i,'requests':len(rs),'all_success':all('choices' in r for r in rs),'output_ids':[r['choices'][0].get('text') for r in rs],'graph_replay_log_count':count})
(out/'graph-replay-requests.json').write_text(json.dumps(rows,indent=2)+'\n');print(json.dumps(rows,indent=2))
PY
printf '{"status":"MEASURED"}\n' > "$out/run-status.json"
