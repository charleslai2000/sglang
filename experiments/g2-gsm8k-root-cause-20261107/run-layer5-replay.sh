#!/usr/bin/env bash
set -Eeuo pipefail
OUT=/data/sglang-hicache/g2-quasar-runs/20261107T-g2-first-logits
ROOT=/home/ubuntu/workspaces/3rdparty/sglang-hicache
RID=${RID:-g2-l5-doc24}
DOC_ID=${DOC_ID:-24}
CAPTURE_LAYER=${CAPTURE_LAYER:-5}
API_PORT=${API_PORT:-31224}
CAPTURE_TAG=${CAPTURE_TAG:-l5-replay}
export PYTHONNOUSERSITE=1
export PYTHONPATH="$OUT/aot-sm86-package:$OUT/head-kernel-shadow:$ROOT/python:/home/ubuntu/venvs/sglang-3090/lib/python3.12/site-packages:$ROOT/python/sglang/kernels/aot/python"
export SGLANG_ENABLE_JIT_DEEPGEMM=0
export GEMMA4_MODEL_IDENTITY='{"model_revision":"7d6269096c9acbce4422fd1aa3a249436b01288868961e48ca9bb2541997f669","model_sha256":"7d6269096c9acbce4422fd1aa3a249436b01288868961e48ca9bb2541997f669"}'
export SGLANG_GEMMA4_CAPTURE_LOGITS=1
export SGLANG_GEMMA4_CAPTURE_LAYERS=1
export SGLANG_GEMMA4_CAPTURE_PLE=1
export GEMMA4_PLE_CAPTURE_LAYER=5
export GEMMA4_PLE_CAPTURE_FILE="$OUT/$CAPTURE_TAG-ple"
export SGLANG_GEMMA4_LOGITS_FILE="$OUT/$CAPTURE_TAG-logits"
export SGLANG_GEMMA4_LAYERS_FILE="$OUT/$CAPTURE_TAG-layers"
export G2_L5_CAPTURE=1
export G2_L5_CAPTURE_RID="$RID"
export G2_CAPTURE_LAYER="$CAPTURE_LAYER"
export G2_CAPTURE_STAGES=${CAPTURE_STAGES:-}
if [[ ${DIAG_FP32:-0} == 1 ]]; then
  export SGLANG_GGUF_Q4_0_FP32_DEQUANT_GEMM=1
fi
if [[ -n ${ATTN_REPLACE_FILE:-} ]]; then
  export G2_4K_ATTN_REPLACE_FILE="$ATTN_REPLACE_FILE"
  export G2_4K_ATTN_REPLACE_LAYER=${ATTN_REPLACE_LAYER:-0}
  export G2_4K_ATTN_REPLACE_POSITION=${ATTN_REPLACE_POSITION:-1103}
  export G2_4K_ATTN_APPLIED_FILE=${ATTN_APPLIED_FILE:-$OUT/$CAPTURE_TAG-attn-applied.pt}
fi
export DOC_ID API_PORT CAPTURE_TAG
export G2_L5_CAPTURE_POSITION=${CAPTURE_POSITION:-1103}
export G2_L5_CAPTURE_FILE="$OUT/$CAPTURE_TAG-ops"
exec 9>/tmp/f1-r16b-gpu-exclusive.lock
GPU_LOCK_HELD=0
flock -n 9 || { echo GPU_LOCK_BUSY; exit 90; }
GPU_LOCK_HELD=1
cd /tmp
setsid /home/ubuntu/venvs/sglang-3090/bin/python -m sglang.launch_server \
  --model-path /data/models/gemma4-quasar-q4_0/gemma-4-E4B-it-QUASAR-Q4_0.gguf \
  --tokenizer-path /data/sglang-hicache/gemma4/model --load-format gguf --quantization gguf \
  --dtype bfloat16 --kv-cache-dtype bf16 --context-length 8192 --mem-fraction-static .88 \
  --chunked-prefill-size 2048 --attention-backend triton --disable-prefill-cuda-graph \
  --disable-decode-cuda-graph --disable-radix-cache --max-running-requests 1 \
  --host 127.0.0.1 --port "$API_PORT" --random-seed 666360643 --log-level info >"$OUT/$CAPTURE_TAG-server.log" 2>&1 &
PID=$!
cleanup(){ kill -TERM -- -"$PID" 2>/dev/null || true; for _ in $(seq 1 60); do kill -0 "$PID" 2>/dev/null || break; sleep 1; done; nvidia-smi --query-gpu=memory.used,utilization.gpu --format=csv,noheader >"$OUT/$CAPTURE_TAG-gpu-after.csv"; }
trap cleanup EXIT INT TERM
for _ in $(seq 1 900); do curl -fsS "http://127.0.0.1:$API_PORT/model_info" >/dev/null 2>&1 && break; kill -0 "$PID" || { tail -100 "$OUT/$CAPTURE_TAG-server.log"; exit 2; }; sleep 1; done
PYTHONNOUSERSITE=1 PYTHONPATH="$ROOT/python:/home/ubuntu/venvs/sglang-3090/lib/python3.12/site-packages" /home/ubuntu/venvs/sglang-3090/bin/python - <<'PY'
import json,requests
from pathlib import Path
import os
D=Path('/data/sglang-hicache/g2-quasar-runs/20261107T-g2-first-logits')
doc_id=int(os.environ.get('DOC_ID','24'))
x=next(json.loads(s) for s in (D/'prompts.jsonl').open() if json.loads(s)['doc_id']==doc_id)
r=requests.post(f"http://127.0.0.1:{os.environ['API_PORT']}/generate",json={'input_ids':x['prompt_token_ids'],'sampling_params':{'temperature':0,'top_k':1,'max_new_tokens':1,'stop':['Question:','</s>','<|im_end|>']},'rid':os.environ['RID']},timeout=3600)
r.raise_for_status();(D/f"{os.environ['CAPTURE_TAG']}-api-doc{doc_id}.json").write_text(json.dumps({'prompt_ids_sha256':x['prompt_ids_sha256'],'response':r.json()},separators=(',',':')));print(r.json()['output_ids'],r.json()['meta_info']['prompt_tokens'])
PY
