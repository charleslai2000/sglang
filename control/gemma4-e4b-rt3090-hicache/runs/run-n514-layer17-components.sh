#!/usr/bin/env bash
set -euo pipefail
repo=/home/ubuntu/workspaces/3rdparty/sglang-hicache
venv=/home/ubuntu/venvs/sglang-3090
model=/data/sglang-hicache/gemma4/model
root=/data/sglang-hicache/gemma4/runs
out="$root/$(date -u +%Y%m%dT%H%M%SZ)-n514-layer17-same-forward"
mkdir -p "$out"/{bootstrap,components/component}
exec 9>/tmp/f1-r16b-gpu-exclusive.lock
flock -n 9 || { echo GPU-lock-unavailable >&2; exit 90; }
export PYTHONPATH="$repo/control/gemma4-e4b-rt3090-hicache/runs/rope-position-bootstrap:$repo/python:/data/sglang-hicache/gemma4/aot-sm86-build:$repo/3rdparty/sglang/python/sglang/kernels/aot/python${PYTHONPATH:+:$PYTHONPATH}"
export LD_LIBRARY_PATH="$venv/lib/python3.12/site-packages/torch/lib:/usr/local/cuda-12.9/lib64${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export SGLANG_GEMMA4_CAPTURE_LAYERS=1 GEMMA4_MODEL_IDENTITY='{"model_revision":"6cd26aaa2357fb2bad8c51699a7558a4d1a965bb","model_sha256":"19d89d2a4b3e401a3eae75ec08ab112810421a036c91d8c8226b686be7fe0c5d"}' GEMMA4_MODEL_SHA256=19d89d2a4b3e401a3eae75ec08ab112810421a036c91d8c8226b686be7fe0c5d
export SGLANG_CACHE_DIR=/data/sglang-hicache/gemma4/cache HF_HOME=/data/sglang-hicache/gemma4/hf-home
export GEMMA4_RUNTIME_HOOK_ENABLE=1 GEMMA4_RUNTIME_HOOK_PATH="$repo/control/gemma4-e4b-rt3090-hicache/runs" GEMMA4_RUNTIME_HOOK_INSTALL="$repo/control/gemma4-e4b-rt3090-hicache/runs/runtime-layer-components.py"
export GEMMA4_COMPONENT_LAYER=17 GEMMA4_COMPONENT_STATE_FILE="$out/components/component"
export SGLANG_GEMMA4_LAYERS_FILE="$out/forward" SGLANG_GEMMA4_CAPTURE_LOGITS=1 SGLANG_GEMMA4_LOGITS_FILE="$out/forward"
"$venv/bin/python" - "$out" <<'PY'
import json,random,sys
from pathlib import Path
out=Path(sys.argv[1]); src=json.loads(Path('/data/sglang-hicache/gemma4/runs/20261022T172926Z-e5m2-swa-boundary/n514/bf16-request.json').read_text()); ids=src['prompt'];
assert len(ids)==514
(out/'request.json').write_text(json.dumps({'input_ids':ids,'sampling_params':{'temperature':0,'max_new_tokens':1}},separators=(',',':'))+'\n')
PY
(cd "$repo"; "$venv/bin/python" -m sglang.launch_server --model-path "$model" --trust-remote-code --host 127.0.0.1 --port 31045 --context-length 4096 --max-running-requests 1 --max-total-tokens 4096 --mem-fraction-static .82 --disable-radix-cache --disable-cuda-graph --kv-cache-dtype bf16 --attention-backend triton --log-level info) >"$out/server.log" 2>&1 & pid=$!; echo "$pid" >"$out/server.pid"
cleanup(){ kill -TERM "$pid" 2>/dev/null || true; for _ in $(seq 1 60); do kill -0 "$pid" 2>/dev/null || break; sleep 2; done; pkill -TERM -P "$pid" 2>/dev/null || true; kill -TERM "$pid" 2>/dev/null || true; }
trap cleanup EXIT
for _ in $(seq 1 240); do curl -fsS http://127.0.0.1:31045/health >/dev/null 2>&1 && break; kill -0 "$pid" 2>/dev/null || { tail -80 "$out/server.log" >&2; exit 2; }; sleep 5; done
GEMMA4_RUN_OUT="$out" "$venv/bin/python" - <<'PY'
import json,os,time,urllib.request
from pathlib import Path
out=Path(os.environ['GEMMA4_RUN_OUT']); payload=json.loads((out/'request.json').read_text()); req=urllib.request.Request('http://127.0.0.1:31045/generate',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'}); t=time.perf_counter(); response=json.loads(urllib.request.urlopen(req,timeout=600).read()); (out/'response.json').write_text(json.dumps(response,indent=2)+'\n'); (out/'rid.txt').write_text(response['meta_info']['id']+'\n');(out/'client-result.json').write_text(json.dumps({'elapsed_s':time.perf_counter()-t,'meta_info':response.get('meta_info',{})},indent=2)+'\n')
PY
"$venv/bin/python" - "$out" <<'PY'
import json,sys
from pathlib import Path
out=Path(sys.argv[1]); rid=(out/'rid.txt').read_text().strip(); ids=json.loads((out/'request.json').read_text())['input_ids']; manifests=[]
for p in out.glob('forward.*.manifest'):
 m=json.loads(p.read_text())
 if m.get('rid')==[rid] and m.get('input_ids')==ids and m.get('forward_mode')=='EXTEND': manifests.append(m)
if len(manifests)!=1: raise SystemExit(f'expected one exact N514 EXTEND manifest; got {len(manifests)}')
m=manifests[0]; f=m['forward_id']; expected=['attention_norm_input','decoder_layer_output']
for name in expected:
 p=out/'components'/'component'/f'component.{rid}.{f}.layer17.{name}.json'; r=json.loads(p.read_text()); assert r['forward_id']==f and r['rid']==rid and r['model_sha256']=='19d89d2a4b3e401a3eae75ec08ab112810421a036c91d8c8226b686be7fe0c5d'; assert r['forward_mode']=='EXTEND' and r['step_input_ids']==ids and r['step_positions']==m['positions'] and len(r['value'])==514
assert m['model_identity']['model_sha256']=='19d89d2a4b3e401a3eae75ec08ab112810421a036c91d8c8226b686be7fe0c5d'
(out/'bound-forward.json').write_text(json.dumps({'status':'COMPLETE','rid':rid,'forward_id':f,'model_identity':m['model_identity'],'positions':[m['positions'][0],m['positions'][-1]],'input_tokens':len(ids),'components':expected},indent=2)+'\n');print(json.dumps({'run':str(out),'rid':rid,'forward_id':f,'status':'COMPLETE'}))
PY
cleanup; trap - EXIT
nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader >"$out/gpu-after.csv"
printf '%s\n' "$out"
