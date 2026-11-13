#!/usr/bin/env bash
set -euo pipefail
repo=/home/ubuntu/workspaces/3rdparty/sglang-hicache
venv=/home/ubuntu/venvs/sglang-3090
model=/data/sglang-hicache/gemma4/model
out="/data/sglang-hicache/gemma4/runs/$(date -u +%Y%m%dT%H%M%SZ)-g32-prefill-baseline"
mkdir -p "$out"
exec 9>/tmp/f1-r16b-gpu-exclusive.lock
flock -n 9 || { echo GPU-lock-unavailable >&2; exit 90; }
export PYTHONPATH="$repo/python:/data/sglang-hicache/gemma4/aot-sm86-build:$repo/3rdparty/sglang/python/sglang/kernels/aot/python${PYTHONPATH:+:$PYTHONPATH}"
export LD_LIBRARY_PATH="$venv/lib/python3.12/site-packages/torch/lib:/usr/local/cuda-12.9/lib64${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export SGLANG_CACHE_DIR=/data/sglang-hicache/gemma4/cache HF_HOME=/data/sglang-hicache/gemma4/hf-home
export SGLANG_GEMMA4_CAPTURE_LAYERS=0 SGLANG_GEMMA4_CAPTURE_LOGITS=0
"$venv/bin/python" - "$out" <<'PY'
import json,random,sys
from pathlib import Path
out=Path(sys.argv[1]); rng=random.Random(20261023); ids=[rng.randrange(1,261000) for _ in range(32768)]
(out/'frozen-input-ids.json').write_text(json.dumps({'seed':20261023,'ids':ids},separators=(',',':'))+'\n')
PY
(cd "$repo"; "$venv/bin/python" -m sglang.launch_server --model-path "$model" --trust-remote-code --host 127.0.0.1 --port 31044 --context-length 32768 --max-running-requests 1 --max-total-tokens 32768 --mem-fraction-static .82 --disable-radix-cache --kv-cache-dtype bf16 --attention-backend triton --cuda-graph-max-bs-decode 1 --log-level info) >"$out/server.log" 2>&1 & pid=$!
echo "$pid" >"$out/server.pid"
nvidia-smi --query-gpu=timestamp,utilization.gpu,memory.used --format=csv --loop-ms=500 >"$out/gpu-samples.csv" & monitor=$!
cleanup(){ kill -TERM "$monitor" 2>/dev/null || true; kill -TERM "$pid" 2>/dev/null || true; for _ in $(seq 1 60); do kill -0 "$pid" 2>/dev/null || break; sleep 2; done; pkill -TERM -P "$pid" 2>/dev/null || true; kill -TERM "$pid" 2>/dev/null || true; }
trap cleanup EXIT
ready=0
for _ in $(seq 1 240); do if curl -fsS http://127.0.0.1:31044/health >/dev/null 2>&1; then ready=1; break; fi; kill -0 "$pid" 2>/dev/null || { tail -80 "$out/server.log" >&2; exit 2; }; sleep 5; done
[[ $ready == 1 ]] || { tail -80 "$out/server.log" >&2; exit 3; }
GEMMA4_RUN_OUT="$out" "$venv/bin/python" - <<'PY'
import json,os,time,urllib.request,hashlib
from pathlib import Path
out=Path(os.environ['GEMMA4_RUN_OUT']); ids=json.loads((out/'frozen-input-ids.json').read_text())['ids']; rows=[]
for n in (1024,4096,16384,32761):
 cases=[]
 for rep in range(3):
  payload={'input_ids':ids[:n],'sampling_params':{'temperature':0,'max_new_tokens':1}}
  req=urllib.request.Request('http://127.0.0.1:31044/generate',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'}); t=time.perf_counter()
  try:
   response=json.loads(urllib.request.urlopen(req,timeout=1200).read()); elapsed=time.perf_counter()-t; row={'tokens':n,'repeat':rep+1,'status':'HTTP_OK','elapsed_s':elapsed,'client_input_tokens_per_s':n/elapsed,'response_meta':response.get('meta_info',{}),'response_text':response.get('text',''),'system_clock_ns':time.time_ns()}
  except Exception as e:
   elapsed=time.perf_counter()-t; row={'tokens':n,'repeat':rep+1,'status':'FAILED','elapsed_s':elapsed,'error':repr(e)}
   if hasattr(e,'read'):
    try: row['error_body']=e.read().decode(errors='replace')
    except Exception: pass
  cases.append(row); rows.append(row); print(json.dumps(row))
  if row['status']!='HTTP_OK': break
 (out/f'n{n}-results.json').write_text(json.dumps(cases,indent=2)+'\n')
 if any(c['status']!='HTTP_OK' for c in cases): break
groups={}
for row in rows:
 groups.setdefault(str(row['tokens']),[]).append(row.get('client_input_tokens_per_s'))
summary={'status':'MEASURED_NOT_ACCEPTANCE','model_revision':'6cd26aaa2357fb2bad8c51699a7558a4d1a965bb','model_sha256':'19d89d2a4b3e401a3eae75ec08ab112810421a036c91d8c8226b686be7fe0c5d','kv_dtype':'bf16','max_running_requests':1,'cases':rows,'per_length_tok_s':groups}
(out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
PY
cleanup; trap - EXIT
nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader >"$out/gpu-after.csv"
printf '%s\n' "$out"
