#!/usr/bin/env bash
set -Eeuo pipefail
ROOT=/home/ubuntu/workspaces/3rdparty/sglang-hicache; RUNS=/data/sglang-hicache/g2-quasar-runs
ARM=${1:?A, B or C}; PORT=${2:?port}
case "$ARM" in A) REPLACE="$RUNS/g2-layer17-bf16-A.attention.pt";; B) REPLACE="$RUNS/g2-layer17-bf16-B.attention.pt";; C) REPLACE="$RUNS/g2-layer17-bf16-C.attention.pt";; *) exit 2;; esac
OUT="$RUNS/g2-4k-l17-abc-bf16-${ARM}-$(date -u +%Y%m%dT%H%M%SZ)"; mkdir -p "$OUT"
exec 9>/tmp/f1-r16b-gpu-exclusive.lock; flock -n 9 || { echo LOCK_BUSY >&2; exit 90; }
# Build a private package overlay with correct namespace-package routing: use the
# repo package for all normal modules and override only extend_attention.py.
OV=/tmp/g2-t003-server-overlay; rm -rf "$OV"; mkdir -p "$OV/sglang/kernels/ops/attention"
/home/ubuntu/venvs/sglang-3090/bin/python - "$OV/sglang/kernels/ops/attention/extend_attention.py" <<'PY'
import subprocess,sys
from pathlib import Path
Path(sys.argv[1]).write_bytes(subprocess.check_output(['git','show','HEAD:python/sglang/kernels/ops/attention/extend_attention.py'],cwd='/home/ubuntu/workspaces/3rdparty/sglang-hicache'))
PY
cat >"$OV/sglang/kernels/ops/attention/__init__.py" <<PY
__path__ = ["$OV/sglang/kernels/ops/attention", "$ROOT/python/sglang/kernels/ops/attention"]
PY
cat >"$OV/sglang/kernels/ops/__init__.py" <<PY
__path__ = ["$OV/sglang/kernels/ops", "$ROOT/python/sglang/kernels/ops"]
PY
cat >"$OV/sglang/kernels/__init__.py" <<PY
__path__ = ["$OV/sglang/kernels", "$ROOT/python/sglang/kernels"]
PY
cat >"$OV/sglang/__init__.py" <<PY
__path__ = ["$OV/sglang", "$ROOT/python/sglang"]
PY
export PYTHONPATH="$OV:$ROOT/python:/data/sglang-hicache/g2-quasar-runs/aot-sm86-package:/home/ubuntu/venvs/sglang-3090/lib/python3.12/site-packages:$ROOT/python/sglang/kernels/aot/python"
export SGLANG_ENABLE_JIT_DEEPGEMM=0 SGLANG_GEMMA4_CAPTURE_LOGITS=1 SGLANG_GEMMA4_LOGITS_FILE="$OUT/forward"
export G2_4K_ATTN_REPLACE_LAYER=17 G2_4K_ATTN_REPLACE_POSITION=4095 G2_4K_ATTN_REPLACE_FILE="$REPLACE" G2_4K_ATTN_OUTPUT_FILE="$OUT/layer17-attention.pt" G2_4K_ATTN_APPLIED_FILE="$OUT/layer17-attention-applied.pt"
# Fail closed if any worker would resolve the dirty checkout kernel instead.
cd /tmp
PYTHONPATH="$PYTHONPATH" /home/ubuntu/venvs/sglang-3090/bin/python - <<'PY'
import sglang.kernels.ops.attention.extend_attention as e
assert e.__file__.startswith('/tmp/g2-t003-server-overlay/'), e.__file__
from pathlib import Path
assert 'BF16_KV_COMPUTE' not in Path(e.__file__).read_text(), e.__file__
print('ISOLATED_KERNEL', e.__file__, flush=True)
PY
export GEMMA4_MODEL_IDENTITY="{\"model\":\"gemma-4-E4B-it-QUASAR-Q4_0.gguf\",\"source_head\":\"$(cd "$ROOT" && git rev-parse HEAD)\",\"kv\":\"bf16\",\"intervention\":\"T003-${ARM}\"}"
cd /tmp
setsid /home/ubuntu/venvs/sglang-3090/bin/python -m sglang.launch_server --model-path /data/models/gemma4-quasar-q4_0/gemma-4-E4B-it-QUASAR-Q4_0.gguf --tokenizer-path /data/models/gemma4-quasar-q4_0/gemma-4-E4B-it-QUASAR-Q4_0.gguf --load-format gguf --quantization gguf --dtype bfloat16 --kv-cache-dtype bf16 --context-length 4608 --mem-fraction-static 0.85 --chunked-prefill-size 2048 --attention-backend triton --disable-prefill-cuda-graph --disable-decode-cuda-graph --host 127.0.0.1 --port "$PORT" --max-running-requests 1 --disable-radix-cache >"$OUT/server.log" 2>&1 &
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
r=urllib.request.Request(f'http://127.0.0.1:{sys.argv[2]}/v1/completions',data=json.dumps(req).encode(),headers={'Content-Type':'application/json'});b=urllib.request.urlopen(r,timeout=1200).read();(o/'response.json').write_bytes(b);print(json.loads(b)['choices'][0]['token_ids'],flush=True)
PY
/home/ubuntu/venvs/sglang-3090/bin/python - "$OUT" <<'PY'
import sys,torch,glob,os
from pathlib import Path
o=Path(sys.argv[1]);rows=[]
for f in glob.glob(str(o/'forward.*.logits')):
 r=torch.load(f,map_location='cpu',weights_only=True)
 if r.get('forward_mode')=='EXTEND' and r['positions'].numel()==2048 and int(r['positions'][0])==2048 and int(r['positions'][-1])==4095 and r['output'].shape==(1,262144):rows.append((f,r))
assert len(rows)==1,[(Path(x[0]).name) for x in rows]
f,r=rows[0];print('RESULT',os.path.basename(f),'top1',int(r['output'].float().argmax()),flush=True)
PY
printf '%s\n' "$OUT" >> "$RUNS/g2-4k-runs.txt"; echo "$OUT"
