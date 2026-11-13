#!/usr/bin/env bash
set -Eeuo pipefail
ROOT=/home/ubuntu/workspaces/3rdparty/sglang-hicache
RUNS=/data/sglang-hicache/g2-quasar-runs
MODEL=/data/models/gemma4-quasar-q4_0/gemma-4-E4B-it-QUASAR-Q4_0.gguf
TOKENIZER=/data/sglang-hicache/gemma4/model
OVERLAY=$RUNS/20261107T-g2-first-logits/head-kernel-shadow
AOT=$RUNS/20261107T-g2-first-logits/aot-sm86-package
VENV=/home/ubuntu/venvs/sglang-3090
LOCK=/tmp/f1-r16b-gpu-exclusive.lock
BASE=${1:?usage: launch_quasar_radix8k.sh RUN_DIR}
[[ "$BASE" = "$RUNS"/* ]] || { echo "run directory must be under $RUNS" >&2; exit 2; }
[[ ! -e "$BASE" ]] || { echo "refusing existing run directory: $BASE" >&2; exit 4; }
exec 9>"$LOCK"; flock -n 9 || { echo GPU_LOCK_BUSY >&2; exit 90; }
mkdir -p "$BASE"
exec 8>"$BASE/run.lock"; flock -n 8
trap 'rmdir "$BASE" 2>/dev/null || true' EXIT INT TERM
PORT=31381
if ss -ltn | grep -q ":${PORT}\\b"; then echo "port $PORT busy" >&2; exit 91; fi
export PYTHONNOUSERSITE=1 SGLANG_ENABLE_JIT_DEEPGEMM=0 SGLANG_ENABLE_METRICS_DEVICE_TIMER=1 SGLANG_FORCE_STREAM_INTERVAL=1
export PYTHONPATH="$OVERLAY:$AOT:$ROOT/python:$VENV/lib/python3.12/site-packages:$ROOT/python/sglang/kernels/aot/python"
export LD_LIBRARY_PATH="$VENV/lib/python3.12/site-packages/torch/lib:/usr/local/cuda-12.9/lib64${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export SGLANG_CACHE_DIR=/home/ubuntu/.cache/sglang HF_HOME=/data/sglang-hicache/gemma4/hf-home
OVERLAY_FILE=$OVERLAY/sglang/kernels/ops/attention/extend_attention.py
OVERLAY_SHA=$(sha256sum "$OVERLAY_FILE" | awk '{print $1}')
AOT_SHA=$(sha256sum "$AOT/sm86/common_ops.abi3.so" | awk '{print $1}')
[[ "$OVERLAY_SHA" = 69a9f59d6817b3947feb38639d47c690e82947ead0e9af50a0200f02a4b34d4e ]]
[[ "$AOT_SHA" = 22c9f5eb84e5e494df31f814aeffe5ba0aafb266fca2b56c99cfb5a3c1dea4c2 ]]
[[ "$(sha256sum "$MODEL" | awk '{print $1}')" = 7d6269096c9acbce4422fd1aa3a249436b01288868961e48ca9bb2541997f669 ]]
python3 "$ROOT/experiments/g2-quasar-radix8k-prefix-benchmark/generate_fixture.py" --tokenizer "$TOKENIZER" --out "$BASE/fixture.json" > "$BASE/fixture-meta.json"
cat > "$BASE/manifest.txt" <<EOF
model=$MODEL
model_sha256=$(sha256sum "$MODEL" | awk '{print $1}')
tokenizer=$TOKENIZER
tokenizer_config_sha256=$(sha256sum "$TOKENIZER/tokenizer_config.json" | awk '{print $1}')
compute_dtype=bfloat16
kv_cache_dtype=fp8_e5m2
attention_backend=triton
tp_size=1
radix_cache=enabled; hicache_l2_l3=disabled
context_length=8450
max_running_requests=32
max_queued_requests=32
mem_fraction_static=0.88
chunked_prefill_size=8192
max_prefill_tokens=16384
schedule_policy=fcfs
prefix_tokens=7168
new_tokens=1024
prompt_tokens=8192
greedy_output_tokens=256
concurrency=1,2,4,8,16,24,32
trials=3_plus_1_warmup
cuda_graph_decode_backend=full
cuda_graph_decode_max_bs=32
cuda_graph_decode_bs=1,2,4,8,12,16,24,32
cuda_graph_prefill=disabled (multimodal Gemma default)
source_head=$(git -C "$ROOT" rev-parse HEAD)
source_dirty=yes; DeviceTimer enabled by SGLANG_ENABLE_METRICS_DEVICE_TIMER=1; not historical dirty patch identity
head_extend_overlay_sha256=$OVERLAY_SHA
aot_common_ops_abi3_sha256=$AOT_SHA
EOF
cat > "$BASE/source-identity.txt" <<EOF
head=$(git -C "$ROOT" rev-parse HEAD)
branch=$(git -C "$ROOT" branch --show-current)
source_tree_dirty=true
source_file_sha256=$(sha256sum "$ROOT/python/sglang/srt/utils/device_timer.py" | awk '{print $1}')
overlay_sha256=$OVERLAY_SHA
aot_common_ops_abi3_sha256=$AOT_SHA
fixture_builder_sha256=$(sha256sum "$ROOT/experiments/g2-quasar-radix8k-prefix-benchmark/generate_fixture.py" | awk '{print $1}')
EOF
SERVER_PID=''; MONITOR_PID=''
SELF_CLEANUP=1
cleanup(){ set +e
 SELF_CLEANUP=1
 if [[ -n "$MONITOR_PID" ]]; then kill "$MONITOR_PID" 2>/dev/null || true; wait "$MONITOR_PID" 2>/dev/null || true; fi
 if [[ -n "$SERVER_PID" ]] && kill -0 "$SERVER_PID" 2>/dev/null; then kill -TERM -- "-$SERVER_PID" 2>/dev/null || kill -TERM "$SERVER_PID" 2>/dev/null; sleep 5; kill -KILL -- "-$SERVER_PID" 2>/dev/null || true; wait "$SERVER_PID" 2>/dev/null || true; fi
 if ss -ltnp | grep -q ":${PORT}\\b"; then echo PORT_REMAINS > "$BASE/cleanup-warning.txt"; fi
 nvidia-smi --query-gpu=timestamp,memory.used,utilization.gpu --format=csv,noheader > "$BASE/gpu-after.csv"
 sha256sum "$BASE"/manifest.txt "$BASE"/source-identity.txt "$BASE"/fixture.json "$BASE"/fixture.json.sha256 "$BASE"/server.log "$BASE"/records-c1.json "$BASE"/raw-c1.jsonl "$BASE"/records-c2-c32.json "$BASE"/raw-c2-c32.jsonl "$BASE"/event-analysis.txt "$BASE"/gpu-samples.csv "$BASE"/gpu-after.csv > "$BASE"/artifact-sha256.txt 2>/dev/null || true
}
trap cleanup EXIT INT TERM
(cd /tmp && setsid "$VENV/bin/python" -m sglang.launch_server \
 --model-path "$MODEL" --tokenizer-path "$TOKENIZER" --load-format gguf --quantization gguf --dtype bfloat16 --kv-cache-dtype fp8_e5m2 \
 --host 127.0.0.1 --port "$PORT" --context-length 8450 --max-running-requests 32 --max-queued-requests 32 --mem-fraction-static .88 \
 --chunked-prefill-size 8192 --max-prefill-tokens 16384 --attention-backend triton --schedule-policy fcfs \
 --cuda-graph-backend-decode full --cuda-graph-max-bs-decode 32 --cuda-graph-bs-decode 1 2 4 8 12 16 24 32 --cuda-graph-backend-prefill disabled \
 --enable-metrics --enable-request-time-stats-logging --log-level info) > "$BASE/server.log" 2>&1 &
SERVER_PID=$!; echo "$SERVER_PID" > "$BASE/server.pid"
(nvidia-smi --query-gpu=timestamp,memory.used,utilization.gpu --format=csv,noheader -lms 500 > "$BASE/gpu-samples.csv") & MONITOR_PID=$!
ready=0
for _ in $(seq 1 1200); do
 if curl -fsS "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; then ready=1; break; fi
 if ! kill -0 "$SERVER_PID" 2>/dev/null; then tail -120 "$BASE/server.log"; exit 2; fi
 sleep 1
done
[[ "$ready" = 1 ]] || { echo SERVER_READY_TIMEOUT >&2; tail -120 "$BASE/server.log"; exit 3; }
printf '%s\n' "$(curl -fsS "http://127.0.0.1:$PORT/model_info")" > "$BASE/model-info.json"
"$VENV/bin/python" - "$BASE" "$PORT" <<'PY'
import json,sys,urllib.request
from pathlib import Path
p=Path(sys.argv[1]);port=sys.argv[2];f=json.loads((p/'fixture.json').read_text())
def post(ids,rid,n):
 b={'rid':rid,'input_ids':[ids],'sampling_params':{'temperature':0,'top_p':1,'max_new_tokens':n,'min_new_tokens':n,'logit_bias':{'1':-100.0,'105':-100.0,'106':-100.0},'ignore_eos':False,'stop':[],'stop_strs':[],'stop_token_ids':[]},'return_token_ids':True}
 q=urllib.request.Request(f'http://127.0.0.1:{port}/generate',data=json.dumps(b).encode(),headers={'Content-Type':'application/json'});o=json.loads(urllib.request.urlopen(q,timeout=1800).read());o=o[0] if isinstance(o,list) and len(o)==1 else o;m=o.get('meta_info',{});out=o.get('output_ids',[])
 if len(out)!=n or int(m.get('completion_tokens',len(out)))!=n:raise RuntimeError(f'{rid}: incomplete output')
 (p/f'{rid}.json').write_text(json.dumps(o,indent=2)+'\n');return o
prime=post(f['prefix_ids'],'radix8k-primer',1);v=post(f['prompts']['validation'],'radix8k-validation',256)
if v.get('meta_info',{}).get('cached_tokens')!=7168:raise RuntimeError(f"validation cached_tokens={v.get('meta_info',{}).get('cached_tokens')}")
print(json.dumps({'primer':prime.get('meta_info',{}).get('completion_tokens'),'validation_cached_tokens':v['meta_info']['cached_tokens'],'validation_output_tokens':len(v['output_ids'])}))
PY
export RADIX8K_OUT="$BASE" RADIX8K_URL="http://127.0.0.1:$PORT/generate"
"$VENV/bin/python" "$ROOT/experiments/g2-quasar-radix8k-prefix-benchmark/radix8k_benchmark.py" --run --accepted-validation --c1-only | tee "$BASE/driver-c1.log"
mv "$BASE/records.json" "$BASE/records-c1.json"; mv "$BASE/raw.jsonl" "$BASE/raw-c1.jsonl"
"$VENV/bin/python" "$ROOT/experiments/g2-quasar-radix8k-prefix-benchmark/radix8k_benchmark.py" --run --accepted-validation --concurrency 2 4 8 16 24 32 | tee "$BASE/driver-c2-c32.log"
mv "$BASE/records.json" "$BASE/records-c2-c32.json"; mv "$BASE/raw.jsonl" "$BASE/raw-c2-c32.jsonl"
python3 "$ROOT/experiments/g2-quasar-radix8k-prefix-benchmark/analyze_radix8k_events.py" "$BASE/server.log" --measured-only | tee "$BASE/event-analysis.txt"
python3 "$ROOT/experiments/g2-quasar-radix8k-prefix-benchmark/analyze_run.py" "$BASE" --records "$BASE/records-c1.json" "$BASE/records-c2-c32.json"
