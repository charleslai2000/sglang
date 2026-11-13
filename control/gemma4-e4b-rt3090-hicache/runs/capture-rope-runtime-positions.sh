#!/usr/bin/env bash
set -euo pipefail
repo=/home/ubuntu/workspaces/3rdparty/sglang-hicache
venv=/home/ubuntu/venvs/sglang-3090
model=/data/sglang-hicache/gemma4/model
root=/data/sglang-hicache/gemma4/runs
out="$root/$(date -u +%Y%m%dT%H%M%SZ)-rope-runtime-positions"
mkdir -p "$out"/{bootstrap,bf16}
exec 9>/tmp/f1-r16b-gpu-exclusive.lock
flock -n 9 || { echo GPU-lock-unavailable >&2; exit 90; }
export SGLANG_GEMMA4_CAPTURE_LAYERS=1
export GEMMA4_MODEL_IDENTITY='{"model_revision":"6cd26aaa2357fb2bad8c51699a7558a4d1a965bb","model_sha256":"19d89d2a4b3e401a3eae75ec08ab112810421a036c91d8c8226b686be7fe0c5d"}'
export SGLANG_CACHE_DIR=/data/sglang-hicache/gemma4/cache HF_HOME=/data/sglang-hicache/gemma4/hf-home
export GEMMA4_ROPE_POSITION_CAPTURE=1 GEMMA4_ROPE_POSITION_CAPTURE_SCRIPT="$repo/control/gemma4-e4b-rt3090-hicache/runs/runtime-rope-position-capture.py" GEMMA4_ROPE_POSITION_OUT="$out/bf16/rope"
export PYTHONPATH="$repo/control/gemma4-e4b-rt3090-hicache/runs/rope-position-bootstrap:$repo/python:/data/sglang-hicache/gemma4/aot-sm86-build:$repo/3rdparty/sglang/python/sglang/kernels/aot/python${PYTHONPATH:+:$PYTHONPATH}"
export LD_LIBRARY_PATH="$venv/lib/python3.12/site-packages/torch/lib:/usr/local/cuda-12.9/lib64${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export SGLANG_GEMMA4_LAYERS_FILE="$out/bf16/forward" SGLANG_GEMMA4_CAPTURE_LOGITS=1 SGLANG_GEMMA4_LOGITS_FILE="$out/bf16/forward"
(cd "$repo"; "$venv/bin/python" -m sglang.launch_server --model-path "$model" --trust-remote-code --host 127.0.0.1 --port 31040 --context-length 1024 --max-running-requests 1 --max-total-tokens 1024 --mem-fraction-static .82 --disable-radix-cache --disable-cuda-graph --kv-cache-dtype bf16 --attention-backend triton --log-level info) >"$out/bf16/server.log" 2>&1 &
pid=$!; echo "$pid" >"$out/bf16/server.pid"
cleanup(){ kill -TERM "$pid" 2>/dev/null || true; for _ in $(seq 1 90); do kill -0 "$pid" 2>/dev/null || break; sleep 2; done; kill -KILL "$pid" 2>/dev/null || true; }
trap cleanup EXIT
for _ in $(seq 1 240); do curl -fsS http://127.0.0.1:31040/health >/dev/null 2>&1 && break; kill -0 "$pid" 2>/dev/null || { tail -80 "$out/bf16/server.log"; exit 1; }; sleep 5; done
python3 - "$out" <<'PY'
import json,sys,urllib.request
from pathlib import Path
out=Path(sys.argv[1]); ids=json.load(open('/data/sglang-hicache/gemma4/runs/20261022T172926Z-e5m2-swa-boundary/n512/bf16-request.json'))['prompt']
payload={'input_ids':ids,'sampling_params':{'temperature':0,'max_new_tokens':1}}
r=urllib.request.Request('http://127.0.0.1:31040/generate',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
response=json.loads(urllib.request.urlopen(r,timeout=300).read());(out/'request.json').write_text(json.dumps(payload)+'\n');(out/'response.json').write_text(json.dumps(response,indent=2)+'\n');(out/'rid.txt').write_text(response['meta_info']['id']+'\n')
PY
sleep 3
"$venv/bin/python" - "$out" <<'PY'
import json,sys
from pathlib import Path
root=Path(sys.argv[1]); rid=(root/'rid.txt').read_text().strip(); ms=[]
for p in (root/'bf16').glob('forward.*.manifest'):
 m=json.loads(p.read_text())
 if rid in m.get('rid',[]) and len(m.get('input_ids',[]))==512 and m.get('forward_mode')=='EXTEND': ms.append((p,m))
if len(ms)!=1: raise SystemExit(f'expect 1 bound N512 manifest; found {len(ms)}')
path,m=ms[0]; rows=[]
for p in (root/'bf16'/'rope').glob('*.jsonl'):
 for line in p.read_text().splitlines():
  r=json.loads(line)
  if r['positions_shape'][0]==512: rows.append((p,r))
if not rows: raise SystemExit('no N512 RoPE backend rows captured')
summary={'status':'MEASURED','rid':rid,'forward_id':m['forward_id'],'model_identity':m['model_identity'],'input_ids_match':m['input_ids']==json.loads((root/'request.json').read_text())['input_ids'],'manifest_positions':m['positions'],'rope_records':[{'file':str(p),'layer':r['layer'],'positions_shape':r['positions_shape'],'positions_dtype':r['positions_dtype'],'positions':r['positions'],'positions_sha256':r['positions_sha256'],'query_shape':r['query_shape'],'key_shape':r['key_shape']} for p,r in rows]}
(root/'rope-position-verification.json').write_text(json.dumps(summary,indent=2)+'\n'); print(json.dumps(summary,indent=2))
PY
cleanup; trap - EXIT
nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader >"$out/gpu-after.csv"
printf '%s\n' "$out"
