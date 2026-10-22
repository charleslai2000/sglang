#!/usr/bin/env bash
set -euo pipefail
repo=/home/ubuntu/workspaces/3rdparty/sglang-hicache;venv=/home/ubuntu/venvs/sglang-3090;model=/data/sglang-hicache/gemma4/model;out="/data/sglang-hicache/gemma4/runs/$(date -u +%Y%m%dT%H%M%SZ)-g1-api-matrix";mkdir -p "$out";exec 9>/tmp/f1-r16b-gpu-exclusive.lock;flock -n 9 || { echo GPU-lock-unavailable >&2;exit 90; }
export PYTHONPATH="$repo/python:/data/sglang-hicache/gemma4/aot-sm86-build:$repo/3rdparty/sglang/python/sglang/kernels/aot/python${PYTHONPATH:+:$PYTHONPATH}";export LD_LIBRARY_PATH="$venv/lib/python3.12/site-packages/torch/lib:/usr/local/cuda-12.9/lib64${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}";export SGLANG_CACHE_DIR=/data/sglang-hicache/gemma4/cache;export HF_HOME=/data/sglang-hicache/gemma4/hf-home
(cd "$repo";"$venv/bin/python" -m sglang.launch_server --model-path "$model" --trust-remote-code --host 127.0.0.1 --port 31041 --context-length 2048 --max-running-requests 8 --max-total-tokens 4096 --mem-fraction-static .82 --kv-cache-dtype fp8_e5m2 --attention-backend triton --cuda-graph-max-bs-decode 1 --log-level info) > "$out/server.log" 2>&1 & pid=$!;echo $pid > "$out/server.pid"
cleanup(){ kill -TERM "$pid" 2>/dev/null || true;sleep 5;pkill -TERM -P "$pid" 2>/dev/null || true;kill -TERM "$pid" 2>/dev/null || true; };trap cleanup EXIT
for _ in $(seq 1 240);do curl -fsS http://127.0.0.1:31041/health >/dev/null 2>&1 && break;kill -0 "$pid" 2>/dev/null || { tail -50 "$out/server.log";exit 2; };sleep 5;done
GEMMA4_RUN_OUT="$out" "$venv/bin/python" - <<'PY' > "$out/client.json"
import concurrent.futures,json,time,urllib.request,statistics,os
from pathlib import Path
out=Path(os.environ['GEMMA4_RUN_OUT']);prompt=[6974,886,2822,13315,1003,506,7217,236761];url='http://127.0.0.1:31041/v1/completions'
def one(i,max_tokens=16,**kw):
 body={'prompt':prompt,'max_tokens':max_tokens,'temperature':0.0,**kw};t=time.perf_counter();req=urllib.request.Request(url,data=json.dumps(body).encode(),headers={'Content-Type':'application/json'});r=json.loads(urllib.request.urlopen(req,timeout=300).read());return {'ok':True,'latency_s':time.perf_counter()-t,'id':r.get('id'),'text':r.get('choices',[{}])[0].get('text',''),'usage':r.get('usage',{})}
rows=[]
for c in [1,2,4,8]:
 t=time.perf_counter()
 with concurrent.futures.ThreadPoolExecutor(max_workers=c) as ex:rs=list(ex.map(lambda i:one(i),range(c)))
 elapsed=time.perf_counter()-t;tokens=sum(x.get('usage',{}).get('completion_tokens',0) for x in rs);row={'concurrency':c,'requests':len(rs),'all_ok':all(x['ok'] for x in rs),'wall_s':elapsed,'aggregate_completion_tokens':tokens,'aggregate_output_tps':tokens/elapsed,'latency_s':[x['latency_s'] for x in rs],'p50_s':statistics.median(x['latency_s'] for x in rs),'max_s':max(x['latency_s'] for x in rs)};rows.append(row);print(json.dumps(row))
(out/'concurrency.json').write_text(json.dumps(rows,indent=2)+'\n')
# stop-string behavior
stop=one(99,64,stop=['f']);(out/'stop.json').write_text(json.dumps(stop,indent=2)+'\n')
PY
printf '{"status":"MEASURED"}\n' > "$out/run-status.json"
