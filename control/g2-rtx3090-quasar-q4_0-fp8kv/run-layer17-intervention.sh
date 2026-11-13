#!/usr/bin/env bash
set -Eeuo pipefail
KV=${1:?bf16 or e5m2}; MODE=${2:?noop or reverse}; PORT=${3:?}
KV_ARG=bf16; [[ $KV == e5m2 ]] && KV_ARG=fp8_e5m2
ROOT=/home/ubuntu/workspaces/3rdparty/sglang-hicache
RUNS=/data/sglang-hicache/g2-quasar-runs
OUT="$RUNS/g2-4k-l17-intervention-${KV}-${MODE}-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$OUT"
exec 9>/tmp/f1-r16b-gpu-exclusive.lock
flock -n 9 || { echo LOCK_BUSY >&2; exit 90; }
export PYTHONPATH="/data/sglang-hicache/g2-quasar-runs/aot-sm86-package:$ROOT/python:/home/ubuntu/venvs/sglang-3090/lib/python3.12/site-packages:$ROOT/python/sglang/kernels/aot/python"
export SGLANG_ENABLE_JIT_DEEPGEMM=0 SGLANG_GEMMA4_CAPTURE_LOGITS=1 SGLANG_GEMMA4_LOGITS_FILE="$OUT/forward"
export G2_4K_ATTN_REPLACE_LAYER=17 G2_4K_ATTN_REPLACE_POSITION=4095
# Intervention artifacts are indexed by upstream, not by replacement cache dtype.
SRC=$KV
export G2_4K_ATTN_REPLACE_FILE="$RUNS/g2-layer17-${SRC}-$([[ $MODE == noop ]] && echo noop || echo reverse-cache).attention.pt"
export G2_4K_ATTN_OUTPUT_FILE="$OUT/layer17-attention.pt" G2_4K_ATTN_APPLIED_FILE="$OUT/layer17-attention-applied.pt"
export G2_4K_ATTN_BACKEND_CAPTURE="$OUT/layer17-backend-input.pt"
export GEMMA4_MODEL_IDENTITY="{\"model\":\"gemma-4-E4B-it-QUASAR-Q4_0.gguf\",\"source_head\":\"$(cd "$ROOT" && git rev-parse HEAD)\",\"kv\":\"$KV\",\"intervention\":\"$MODE\"}"
cd "$ROOT"
setsid /home/ubuntu/venvs/sglang-3090/bin/python -m sglang.launch_server --model-path /data/models/gemma4-quasar-q4_0/gemma-4-E4B-it-QUASAR-Q4_0.gguf --tokenizer-path /data/models/gemma4-quasar-q4_0/gemma-4-E4B-it-QUASAR-Q4_0.gguf --load-format gguf --quantization gguf --dtype bfloat16 --kv-cache-dtype "$KV_ARG" --context-length 4608 --mem-fraction-static 0.85 --chunked-prefill-size 2048 --attention-backend triton --disable-prefill-cuda-graph --disable-decode-cuda-graph --host 127.0.0.1 --port "$PORT" --max-running-requests 1 --disable-radix-cache >"$OUT/server.log" 2>&1 &
PID=$!; echo "$PID" >"$OUT/server.pid"
cleanup(){ kill -TERM -- -"$PID" 2>/dev/null || kill -TERM "$PID" 2>/dev/null || true; for _ in $(seq 1 120); do kill -0 "$PID" 2>/dev/null || break; sleep 1; done; kill -KILL -- -"$PID" 2>/dev/null || true; wait "$PID" 2>/dev/null || true; }
trap cleanup EXIT
for _ in $(seq 1 720); do curl -fsS "http://127.0.0.1:$PORT/model_info" >"$OUT/model-info.json" 2>/dev/null && break; kill -0 "$PID" || { echo SERVER_EXITED; exit 1; }; sleep 1; done
test -s "$OUT/model-info.json"
/home/ubuntu/venvs/sglang-3090/bin/python - "$OUT" "$PORT" <<'PY'
import json,sys,urllib.request
from pathlib import Path
o=Path(sys.argv[1]);p=json.load(open('/data/sglang-hicache/g2-quasar-runs/e5m2-milestone-20261102T184505Z/4k-prompt.json'))['input_ids'];assert len(p)==4096
req={'model':'gemma-4-E4B-it-QUASAR-Q4_0.gguf','prompt':p,'temperature':0,'top_p':1,'top_k':1,'max_tokens':1,'return_token_ids':True,'stream':False}
r=urllib.request.Request(f'http://127.0.0.1:{sys.argv[2]}/v1/completions',data=json.dumps(req).encode(),headers={'Content-Type':'application/json'}); response=urllib.request.urlopen(r,timeout=1200).read();(o/'response.json').write_bytes(response);print(json.loads(response)['choices'][0]['token_ids'],flush=True)
PY
/home/ubuntu/venvs/sglang-3090/bin/python - "$OUT" <<'PY'
import sys,torch,glob,os
from pathlib import Path
o=Path(sys.argv[1]);rows=[]
for f in glob.glob(str(o/'forward.*.logits')):
 r=torch.load(f,map_location='cpu',weights_only=True)
 if r.get('forward_mode')=='EXTEND':
  ps=r['positions'].tolist()
  if max(ps)==4095: rows.append((f,r,ps))
assert len(rows)==1,[(Path(x[0]).name,x[2][0],x[2][-1]) for x in rows]
f,r,ps=rows[0];assert min(ps)==2048 and r['output'].shape==(1,262144)
print('RESULT',os.path.basename(f),'token',int(r['output'].float().argmax()),flush=True)
PY
printf '%s\n' "$OUT" >> "$RUNS/g2-4k-runs.txt"
echo "$OUT"
