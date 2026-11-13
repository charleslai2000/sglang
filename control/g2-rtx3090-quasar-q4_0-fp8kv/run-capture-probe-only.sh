#!/usr/bin/env bash
set -Eeuo pipefail
KV=${1:?BF16 or fp8_e5m2}
PORT=${2:?}
ROOT=/home/ubuntu/workspaces/3rdparty/sglang-hicache
OUT=/data/sglang-hicache/g2-quasar-runs/g2-4k-probe-only-${KV}-$(date -u +%Y%m%dT%H%M%SZ)
mkdir -p "$OUT"
exec 9>/tmp/f1-r16b-gpu-exclusive.lock
flock -n 9 || { echo LOCK_BUSY >&2; exit 90; }
export PYTHONPATH="/data/sglang-hicache/g2-quasar-runs/aot-sm86-package:$ROOT/python:/home/ubuntu/venvs/sglang-3090/lib/python3.12/site-packages:$ROOT/python/sglang/kernels/aot/python"
export SGLANG_ENABLE_JIT_DEEPGEMM=0 SGLANG_GEMMA4_CAPTURE_LOGITS=1 SGLANG_GEMMA4_CAPTURE_LAYERS=0 SGLANG_GEMMA4_CAPTURE_LAYER_POSITIONS=1 SGLANG_GEMMA4_LAYERS_FILE="$OUT/layer" SGLANG_GEMMA4_LOGITS_FILE="$OUT/forward"
export G2_4K_BOUNDARY_ALL=1 G2_4K_ATTN_PROBE_FILE="$OUT/probe" G2_4K_ATTN_PROBE_LAYER=17 G2_4K_ATTN_PROBE_POSITIONS=4095 G2_4K_ATTN_PROBE_FULL_Q=0
export G2_4K_ATTN_FILE="$OUT/attn" G2_4K_ATTN_SNAPSHOT=1 G2_4K_ATTN_LAYER=17 G2_4K_ATTN_LAYERS=17 G2_4K_ATTN_PROBE_POSITIONS=4095
export GEMMA4_MODEL_IDENTITY="{\"model\":\"gemma-4-E4B-it-QUASAR-Q4_0.gguf\",\"source_head\":\"$(cd "$ROOT" && git rev-parse HEAD)\",\"kv\":\"$KV\"}"
export G2_4K_BOUNDARY_FILE="$OUT/boundary" G2_4K_BOUNDARY_POSITIONS=4095 G2_4K_BOUNDARY_LAYERS=0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27,28,29,30,31,32,33,34,35,36,37,38,39,40,41
export G2_4K_KV_WRITE_FILE="$OUT/current-kv" G2_4K_KV_LAYERS=17
cd "$ROOT"
setsid /home/ubuntu/venvs/sglang-3090/bin/python -m sglang.launch_server --model-path /data/models/gemma4-quasar-q4_0/gemma-4-E4B-it-QUASAR-Q4_0.gguf --tokenizer-path /data/models/gemma4-quasar-q4_0/gemma-4-E4B-it-QUASAR-Q4_0.gguf --load-format gguf --quantization gguf --dtype bfloat16 --kv-cache-dtype "$KV" --context-length 4608 --mem-fraction-static 0.85 --chunked-prefill-size 2048 --attention-backend triton --disable-prefill-cuda-graph --disable-decode-cuda-graph --host 127.0.0.1 --port "$PORT" --max-running-requests 1 --disable-radix-cache >"$OUT/server.log" 2>&1 &
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
r=urllib.request.Request(f'http://127.0.0.1:{sys.argv[2]}/v1/completions',data=json.dumps(req).encode(),headers={'Content-Type':'application/json'}); response=urllib.request.urlopen(r,timeout=1200).read();(o/'response.json').write_bytes(response)
print('PROBE_REQUEST_TOKEN_IDS',json.loads(response)['choices'][0]['token_ids'],flush=True)
PY
printf '%s\n' "$OUT"
