#!/usr/bin/env bash
set -Eeuo pipefail
ROOT=/home/ubuntu/workspaces/3rdparty/sglang-hicache
RUNS=/data/sglang-hicache/g2-quasar-runs
MODEL=/data/models/gemma4-quasar-q4_0/gemma-4-E4B-it-QUASAR-Q4_0.gguf
OVERLAY=$RUNS/20261107T-g2-first-logits/head-kernel-shadow
AOT=$RUNS/20261107T-g2-first-logits/aot-sm86-package
LOCK=/tmp/f1-r16b-gpu-exclusive.lock
ARM=${1:?run_longctx.sh REQUESTS CONTEXT DECODE_TOKENS RUN_DIR PORT [MODE]}
REQS=${1}; CTX=${2}; DECODE=${3}; BASE=${4}; PORT=${5}; MODE=${6:-barrier}
SERVE_CTX=$((CTX + DECODE + 512))
[[ "$BASE" = "$RUNS"/* ]] || { echo "run dir must be under $RUNS" >&2; exit 2; }
[[ ! -e "$BASE" ]] || { echo "REFUSE_EXISTING_RUN_DIR $BASE" >&2; exit 4; }
exec 9>"$LOCK"; flock -n 9 || { echo GPU_LOCK_BUSY >&2; exit 90; }
mkdir -p "$BASE"
export PYTHONNOUSERSITE=1 SGLANG_ENABLE_JIT_DEEPGEMM=0
export PYTHONPATH="$OVERLAY:$AOT:$ROOT/python:/home/ubuntu/venvs/sglang-3090/lib/python3.12/site-packages:$ROOT/python/sglang/kernels/aot/python"
OVERLAY_FILE=$OVERLAY/sglang/kernels/ops/attention/extend_attention.py
OVERLAY_SHA=$(sha256sum "$OVERLAY_FILE" | cut -d' ' -f1)
AOT_SHA=$(sha256sum "$AOT/sm86/common_ops.abi3.so" | cut -d' ' -f1)
[[ "$OVERLAY_SHA" = 69a9f59d6817b3947feb38639d47c690e82947ead0e9af50a0200f02a4b34d4e ]]
[[ "$AOT_SHA" = 22c9f5eb84e5e494df31f814aeffe5ba0aafb266fca2b56c99cfb5a3c1dea4c2 ]]
python3 - "$OVERLAY_FILE" "$BASE" <<'PY'
import hashlib,subprocess,sys
from pathlib import Path
p,out=map(Path,sys.argv[1:]); blob=subprocess.check_output(['git','hash-object',str(p)],text=True).strip(); head=subprocess.check_output(['git','rev-parse','HEAD:python/sglang/kernels/ops/attention/extend_attention.py'],text=True).strip()
assert blob==head,(blob,head)
(out/'source-identity.txt').write_text(f'overlay_sha256={hashlib.sha256(p.read_bytes()).hexdigest()}\noverlay_blob={blob}\nhead_blob={head}\nworktree_sha256={hashlib.sha256(Path("python/sglang/kernels/ops/attention/extend_attention.py").read_bytes()).hexdigest()}\naot_common_ops_abi3_sha256=22c9f5eb84e5e494df31f814aeffe5ba0aafb266fca2b56c99cfb5a3c1dea4c2\n')
PY
cat > "$BASE/manifest.txt" <<EOF
model_sha256=7d6269096c9acbce4422fd1aa3a249436b01288868961e48ca9bb2541997f669
kv_cache_dtype=fp8_e5m2
compute_dtype=bfloat16
prompt_context_tokens=$CTX
context_length=$SERVE_CTX
max_running_requests=$REQS
max_queued_requests=$REQS
mem_fraction_static=0.88
chunked_prefill_size=2048
attention_backend=triton
cuda_graph_prefill=false
cuda_graph_decode=false
radix_cache=false
tp_size=1
requests=$REQS
independent_prompt_tokens=$CTX
decode_tokens=$DECODE
client_mode=$MODE
head_overlay_sha256=$OVERLAY_SHA
aot_sha256=$AOT_SHA
EOF
sha256sum "$MODEL" > "$BASE/model-sha256.txt"
SERVER_PID=''
GPU_MONITOR_PID=''
cleanup(){ set +e
 if [[ -n "$GPU_MONITOR_PID" ]]; then kill "$GPU_MONITOR_PID" 2>/dev/null || true; wait "$GPU_MONITOR_PID" 2>/dev/null || true; fi
 if [[ -n "$SERVER_PID" ]] && kill -0 "$SERVER_PID" 2>/dev/null; then
  kill -TERM -- "-$SERVER_PID" 2>/dev/null || kill -TERM "$SERVER_PID" 2>/dev/null
  for _ in $(seq 1 90); do kill -0 "$SERVER_PID" 2>/dev/null || break; sleep 1; done
  kill -KILL -- "-$SERVER_PID" 2>/dev/null || true; wait "$SERVER_PID" 2>/dev/null || true
 fi
 if ss -ltnp | grep -q ":${PORT}\\b"; then echo PORT_REMAINS > "$BASE/cleanup-warning.txt"; fi
 nvidia-smi --query-gpu=timestamp,memory.used,utilization.gpu --format=csv,noheader > "$BASE/gpu-after.csv"
}
trap cleanup EXIT INT TERM
(cd /tmp && setsid /home/ubuntu/venvs/sglang-3090/bin/python -m sglang.launch_server \
 --model-path "$MODEL" --tokenizer-path /data/sglang-hicache/gemma4/model --load-format gguf --quantization gguf \
 --dtype bfloat16 --kv-cache-dtype fp8_e5m2 --context-length "$SERVE_CTX" --mem-fraction-static 0.88 \
 --chunked-prefill-size 2048 --attention-backend triton --disable-prefill-cuda-graph --disable-decode-cuda-graph \
 --disable-radix-cache --skip-server-warmup --max-running-requests "$REQS" --max-queued-requests "$REQS" \
 --host 127.0.0.1 --port "$PORT" --random-seed 666360643 --log-level info) > "$BASE/server.log" 2>&1 &
SERVER_PID=$!; echo "$SERVER_PID" > "$BASE/server.pid"
(nvidia-smi --query-gpu=timestamp,memory.used,utilization.gpu --format=csv,noheader -lms 250 > "$BASE/gpu-samples.csv") & GPU_MONITOR_PID=$!
echo "$GPU_MONITOR_PID" > "$BASE/gpu-monitor.pid"
ready=0
for _ in $(seq 1 1200); do
 if curl -fsS "http://127.0.0.1:$PORT/model_info" > "$BASE/model-info.json" 2>/dev/null; then ready=1; break; fi
 if ! kill -0 "$SERVER_PID" 2>/dev/null; then tail -120 "$BASE/server.log"; exit 2; fi
 sleep 1
done
[[ "$ready" == 1 ]] || { echo SERVER_READY_TIMEOUT >&2; tail -120 "$BASE/server.log"; exit 3; }
python3 - "$BASE" <<'PY'
from pathlib import Path
import re,sys
p=Path(sys.argv[1]); lines=p.joinpath('server.log').read_text(errors='replace').splitlines()
(p/'pool-capacity.txt').write_text('\n'.join(x for x in lines if 'KV Cache is allocated' in x or 'max_total_num_tokens=' in x)+'\n')
PY
/home/ubuntu/venvs/sglang-3090/bin/python "$ROOT/experiments/g2-quasar-e5m2-longctx/longctx_capacity.py" \
 --url "http://127.0.0.1:$PORT" --requests "$REQS" --context "$CTX" --decode-tokens "$DECODE" --mode "$MODE" --prefill-timeout 3600 --out "$BASE/client" | tee "$BASE/client-driver.log"
python3 "$ROOT/experiments/g2-quasar-e5m2-longctx/analyze_longctx.py" "$BASE"
sha256sum "$BASE"/{manifest.txt,source-identity.txt,model-sha256.txt,model-info.json,pool-capacity.txt,gpu-samples.csv,server.log,client/fixture.json,client/client-summary.json,decode-batches.json,prefill-batches.json,server-analysis.json} > "$BASE/artifact-sha256.txt"
cat "$BASE/pool-capacity.txt"
