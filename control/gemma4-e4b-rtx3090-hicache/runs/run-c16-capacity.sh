#!/usr/bin/env bash
set -euo pipefail
repo=/home/ubuntu/workspaces/3rdparty/sglang-hicache
venv=/home/ubuntu/venvs/sglang-3090
model=/data/sglang-hicache/gemma4/model
out="/data/sglang-hicache/gemma4/runs/$(date -u +%Y%m%dT%H%M%SZ)-c16-capacity-autosized-fraction-${MEM_FRACTION_STATIC:-.95}"
mkdir -p "$out"
exec 9>/tmp/f1-r16b-gpu-exclusive.lock
flock -n 9 || { echo GPU-lock-unavailable >&2; exit 90; }
export PYTHONPATH="$repo/python:/data/sglang-hicache/gemma4/aot-sm86-build:$repo/3rdparty/sglang/python/sglang/kernels/aot/python${PYTHONPATH:+:$PYTHONPATH}"
export LD_LIBRARY_PATH="$venv/lib/python3.12/site-packages/torch/lib:/usr/local/cuda-12.9/lib64${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export SGLANG_CACHE_DIR=/data/sglang-hicache/gemma4/cache HF_HOME=/data/sglang-hicache/gemma4/hf-home
"$venv/bin/python" - "$out" <<'PY'
import json,random,sys
from pathlib import Path
out=Path(sys.argv[1]); rng=random.Random(20261024)
# Disjoint span per input slot; radix caching is disabled for independent requests.
ids=[rng.randrange(1,261000) for _ in range(16*32769+32769)]
(out/'frozen-ids.json').write_text(json.dumps({'seed':20261024,'ids':ids},separators=(',',':'))+'\n')
PY
(cd "$repo"; "$venv/bin/python" -m sglang.launch_server --model-path "$model" --trust-remote-code --host 127.0.0.1 --port 31046 --context-length 65536 --max-running-requests 16 --mem-fraction-static "${MEM_FRACTION_STATIC:-.95}" --chunked-prefill-size 2048 --max-prefill-tokens 16384 --disable-radix-cache --kv-cache-dtype fp8_e5m2 --attention-backend triton --cuda-graph-max-bs-decode 16 --enable-metrics --log-level info) >"$out/server.log" 2>&1 & pid=$!
echo "$pid" >"$out/server.pid"
nvidia-smi --query-gpu=timestamp,utilization.gpu,memory.used --format=csv --loop-ms=500 >"$out/gpu-samples.csv" & monitor=$!
cleanup(){ kill -TERM "$monitor" 2>/dev/null || true; kill -TERM "$pid" 2>/dev/null || true; for _ in $(seq 1 60); do kill -0 "$pid" 2>/dev/null || break; sleep 2; done; pkill -TERM -P "$pid" 2>/dev/null || true; kill -TERM "$pid" 2>/dev/null || true; }
trap cleanup EXIT
ready=0
for _ in $(seq 1 240); do if curl -fsS http://127.0.0.1:31046/health >/dev/null 2>&1; then ready=1; break; fi; kill -0 "$pid" 2>/dev/null || { tail -100 "$out/server.log" >&2; exit 2; }; sleep 5; done
[[ $ready == 1 ]] || { tail -100 "$out/server.log" >&2; exit 3; }
GEMMA4_RUN_OUT="$out" "$venv/bin/python" - <<'PY'
import concurrent.futures,json,time,urllib.request,statistics,os,threading
from pathlib import Path
out=Path(os.environ['GEMMA4_RUN_OUT']);ids=json.loads((out/'frozen-ids.json').read_text())['ids'];url='http://127.0.0.1:31046/generate';lock=threading.Lock();events=[]
def snapshot(kind,reqid=None):
 try:
  txt=urllib.request.urlopen('http://127.0.0.1:31046/metrics',timeout=5).read().decode()
  keys=('num_running_reqs','running_requests','token_usage','kv_token_usage','max_total_num_tokens','max_total_num_tokens_swa','kv_used_tokens','kv_used_tokens_swa','retracted')
  vals=[line for line in txt.splitlines() if line and not line.startswith('#') and any(k in line for k in keys)]
 except Exception as e: vals=[f'metrics_error {e!r}']
 with lock: events.append({'monotonic':time.monotonic(),'kind':kind,'request_id':reqid,'metrics':vals})
def req(i,n,gate=None):
 if gate: gate.wait()
 body={'input_ids':ids[i:i+n],'sampling_params':{'temperature':0,'max_new_tokens':1}}
 q=urllib.request.Request(url,data=json.dumps(body).encode(),headers={'Content-Type':'application/json'});start=time.perf_counter();snapshot('submit')
 try:
  r=json.loads(urllib.request.urlopen(q,timeout=1800).read());dur=time.perf_counter()-start;rid=r.get('meta_info',{}).get('id');snapshot('complete',rid)
  return {'ok':True,'id':rid,'prompt_tokens':n,'elapsed_s':dur,'meta':r.get('meta_info',{}),'text':r.get('text','')}
 except Exception as e:return {'ok':False,'prompt_tokens':n,'elapsed_s':time.perf_counter()-start,'error':repr(e)}
rows=[]
for n in [16384,32767]:
 gate=threading.Event();t=time.perf_counter()
 with concurrent.futures.ThreadPoolExecutor(max_workers=16) as ex:
  fs=[ex.submit(req,i*n,n,gate) for i in range(16)];gate.set();rs=[f.result() for f in fs]
 elapsed=time.perf_counter()-t;ok=[r for r in rs if r['ok']];row={'case':f'C16-burst-{n}','all_ok':len(ok)==16,'request_count':16,'successful_requests':len(ok),'aggregate_input_tokens':sum(r['prompt_tokens'] for r in ok),'wall_s':elapsed,'aggregate_input_tps':sum(r['prompt_tokens'] for r in ok)/elapsed if elapsed else 0,'request_latency_s':[r['elapsed_s'] for r in rs],'p50_s':statistics.median(r['elapsed_s'] for r in rs),'p95_s':sorted(r['elapsed_s'] for r in rs)[14],'requests':rs};rows.append(row);(out/f'c16-burst-{n}.json').write_text(json.dumps(row,indent=2)+'\n');print(json.dumps({k:v for k,v in row.items() if k!='requests'}),flush=True)
 if len(ok)<16:break
(out/'runtime-metrics.json').write_text(json.dumps(events,indent=2)+'\n')
(out/'summary.json').write_text(json.dumps({'status':'MEASURED_NOT_ACCEPTANCE','kv_dtype':'fp8_e5m2','max_running_requests':16,'context_length':65536,'max_total_tokens':'auto-profiled','cases':rows},indent=2)+'\n')
PY
cleanup; trap - EXIT
nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader >"$out/gpu-after.csv"
printf '%s\n' "$out"
