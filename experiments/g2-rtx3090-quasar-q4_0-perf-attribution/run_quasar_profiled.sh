#!/usr/bin/env bash
set -Eeuo pipefail
ROOT=/home/ubuntu/workspaces/3rdparty/sglang-hicache
RUNS=/data/sglang-hicache/g2-quasar-runs
MODEL=/data/models/gemma4-quasar-q4_0/gemma-4-E4B-it-QUASAR-Q4_0.gguf
TOKENIZER=/data/sglang-hicache/gemma4/model
OVERLAY=$RUNS/20261107T-g2-first-logits/head-kernel-shadow
AOT=$RUNS/20261107T-g2-first-logits/aot-sm86-package
VENV=/home/ubuntu/venvs/sglang-3090
# Use the installed Nsight Systems CLI; the similarly named binary bundled with
# Nsight Compute is a different tool and left an agent/service orphan in a probe.
NSYS=/usr/local/cuda-12.9/bin/nsys
LOCK=/tmp/f1-r16b-gpu-exclusive.lock
BASE=${1:?usage: run_quasar_profiled.sh RUN_DIR c1|c8|c32 capture_seconds}
C=${2:?missing concurrency}; SECONDS_CAPTURE=${3:?missing capture window}
[[ "$C" =~ ^(1|8|32)$ && "$SECONDS_CAPTURE" =~ ^[0-9]+$ ]] || exit 2
[[ "$BASE" = "$RUNS"/* && ! -e "$BASE" ]] || { echo "invalid/existing run directory" >&2; exit 3; }
exec 9>"$LOCK"; flock -n 9 || { echo GPU_LOCK_BUSY >&2; exit 90; }
mkdir -p "$BASE"; exec 8>"$BASE/run.lock"; flock -n 8
PORT=31382
if ss -ltn | grep -q ":${PORT}\\b"; then echo "port busy" >&2; exit 91; fi
export PYTHONNOUSERSITE=1 SGLANG_ENABLE_JIT_DEEPGEMM=0 SGLANG_ENABLE_METRICS_DEVICE_TIMER=1 SGLANG_FORCE_STREAM_INTERVAL=1 SGLANG_RADIX8K_PROFILER_NVTX=1 SGLANG_ENABLE_NVTX_SCHEDULER=1 SGLANG_GGUF_DISPATCH_TRACE=1 SGLANG_GGUF_DISPATCH_TRACE_FILE="$BASE/gguf-dispatch.jsonl"
export PYTHONPATH="$OVERLAY:$AOT:$ROOT/python:$VENV/lib/python3.12/site-packages:$ROOT/python/sglang/kernels/aot/python" LD_LIBRARY_PATH="$VENV/lib/python3.12/site-packages/torch/lib:/usr/local/cuda-12.9/lib64${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" SGLANG_CACHE_DIR=/home/ubuntu/.cache/sglang HF_HOME=/data/sglang-hicache/gemma4/hf-home
[[ "$(sha256sum "$MODEL"|awk '{print $1}')" = 7d6269096c9acbce4422fd1aa3a249436b01288868961e48ca9bb2541997f669 ]]
python3 "$ROOT/experiments/g2-quasar-radix8k-prefix-benchmark/generate_fixture.py" --tokenizer "$TOKENIZER" --out "$BASE/fixture.json" > "$BASE/fixture-meta.json"
cp /data/sglang-hicache/g2-quasar-runs/20261111T-g2-quasar-radix8k-prefix-e5m2-run4/fixture.json.sha256 "$BASE/fixture.json.sha256"
cat > "$BASE/manifest.txt" <<EOF
model_sha256=7d6269096c9acbce4422fd1aa3a249436b01288868961e48ca9bb2541997f669
compute_dtype=bfloat16
kv_cache_dtype=fp8_e5m2
TP1; Triton; Radix L1; HiCache L2/L3 off
c=$C; prefix=7168; extend=1024; prompt=8192; greedy_output=256
max_running_requests=32; context=8450; mem_fraction_static=.88; chunked_prefill=8192; max_prefill_tokens=16384
Decode full CUDA Graph max_bs=32 buckets=1,2,4,8,12,16,24,32; Prefill Graph disabled
nsys=$NSYS; trace=cuda,nvtx,osrt; cuda-graph-trace=graph; cudaProfilerApi signal delimited in scheduler
SGLANG_GGUF_DISPATCH_TRACE=1; logger per Linear invocation (shape/type/route)
head=$(git -C "$ROOT" rev-parse HEAD); dirty_tree=preserved
extend_overlay_sha256=$(sha256sum "$OVERLAY/sglang/kernels/ops/attention/extend_attention.py"|awk '{print $1}')
aot_common_ops_sha256=$(sha256sum "$AOT/sm86/common_ops.abi3.so"|awk '{print $1}')
EOF
# Per-Linear dispatch identity is logged during one exact-hit cohort; the GPU trace is delimited in the CUDA-owning scheduler.
SERVER_PID=''; NSYS_PID=''; MONITOR_PID=''
cleanup(){ set +e
 if [[ -n "$SERVER_PID" ]] && kill -0 "$SERVER_PID" 2>/dev/null; then
   kill -TERM "$SERVER_PID" 2>/dev/null || true
   for _ in $(seq 1 90); do kill -0 "$SERVER_PID" 2>/dev/null || break; sleep 1; done
   pkill -TERM -P "$SERVER_PID" 2>/dev/null || true
   kill -KILL "$SERVER_PID" 2>/dev/null || true
 fi
 if [[ -n "$MONITOR_PID" ]]; then kill "$MONITOR_PID" 2>/dev/null || true; wait "$MONITOR_PID" 2>/dev/null || true; fi
 if [[ -n "$NSYS_PID" ]]; then kill -INT "$NSYS_PID" 2>/dev/null || true; wait "$NSYS_PID" 2>/dev/null || true; fi
 if ss -ltnp | grep -q ":${PORT}\\b"; then echo PORT_REMAINS > "$BASE/cleanup-warning.txt"; fi
 nvidia-smi --query-gpu=timestamp,utilization.gpu,memory.used --format=csv,noheader > "$BASE/gpu-after.csv"
 sha256sum "$BASE"/* > "$BASE/artifacts.sha256" 2>/dev/null || true
}
trap cleanup EXIT INT TERM
cp /data/sglang-hicache/g2-quasar-runs/20261111T-g2-quasar-radix8k-prefix-e5m2-run4/fixture.json "$BASE/fixture.json"
"$NSYS" profile --trace=cuda,nvtx,osrt --sample=none --cpuctxsw=none --cuda-graph-trace=graph --cuda-event-trace=false --capture-range=cudaProfilerApi --capture-range-end=stop --force-overwrite=true -o "$BASE/nsys" "$VENV/bin/python" -m sglang.launch_server --model-path "$MODEL" --tokenizer-path "$TOKENIZER" --load-format gguf --quantization gguf --dtype bfloat16 --kv-cache-dtype fp8_e5m2 --host 127.0.0.1 --port "$PORT" --context-length 8450 --max-running-requests 32 --max-queued-requests 32 --mem-fraction-static .88 --chunked-prefill-size 8192 --max-prefill-tokens 16384 --attention-backend triton --schedule-policy fcfs --cuda-graph-backend-decode full --cuda-graph-max-bs-decode 32 --cuda-graph-bs-decode 1 2 4 8 12 16 24 32 --cuda-graph-backend-prefill disabled --enable-metrics --enable-request-time-stats-logging --log-level info > "$BASE/nsys-launch.log" 2>&1 & NSYS_PID=$!
for _ in $(seq 1 120); do SERVER_PID=$(pgrep -f "[p]ython.*-m sglang.launch_server.*--port $PORT"|head -1||true); [[ -n "$SERVER_PID" ]]&&break;sleep .25;done
[[ -n "$SERVER_PID" ]]||{ echo SERVER_CHILD_NOT_FOUND >&2;exit 5; }; echo "$SERVER_PID" > "$BASE/server.pid"
(nvidia-smi --query-gpu=timestamp,utilization.gpu,memory.used --format=csv,noheader -lms 200 > "$BASE/gpu-samples.csv") & MONITOR_PID=$!
for _ in $(seq 1 1200); do
  if curl -fsS "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; then break; fi
  if ! kill -0 "$SERVER_PID" 2>/dev/null; then tail -100 "$BASE/nsys-launch.log"; exit 6; fi
  sleep 1
done
curl -fsS "http://127.0.0.1:$PORT/model_info" > "$BASE/model-info.json"
"$VENV/bin/python" - "$BASE" "$PORT" "$C" <<'PY'
import json,sys,urllib.request
from pathlib import Path
p=Path(sys.argv[1]);port=sys.argv[2];c=int(sys.argv[3]);f=json.load(open(p/'fixture.json'))
def post(ids,rid,n):
 b={'rid':rid,'input_ids':[ids],'sampling_params':{'temperature':0,'top_p':1,'max_new_tokens':n,'min_new_tokens':n,'logit_bias':{'1':-100,'105':-100,'106':-100},'ignore_eos':False,'stop':[],'stop_strs':[],'stop_token_ids':[]},'return_token_ids':True};q=urllib.request.Request(f'http://127.0.0.1:{port}/generate',data=json.dumps(b).encode(),headers={'Content-Type':'application/json'});o=json.load(urllib.request.urlopen(q,timeout=7200));o=o[0] if isinstance(o,list) and len(o)==1 else o;(p/f'{rid}.json').write_text(json.dumps(o,indent=2)+'\n');return o
r=post(f['prefix_ids'],'primer',1);v=post(f['prompts']['validation'],'validation',256)
if v.get('meta_info',{}).get('cached_tokens')!=7168:raise RuntimeError('prefix hit validation failed')
print(json.dumps({'primer':r.get('meta_info',{}).get('completion_tokens'),'validation_hit':v['meta_info']['cached_tokens'],'validation_output':len(v.get('output_ids',[]))}))
PY
scheduler_pid=$(pgrep -f '^sglang::scheduler'|head -1||true); [[ -n "$scheduler_pid" ]]||{ echo SCHEDULER_NOT_FOUND >&2;exit 7; };echo "$scheduler_pid" > "$BASE/scheduler.pid"
kill -STOP "$NSYS_PID" 2>/dev/null || true
"$VENV/bin/python" - "$BASE" "$PORT" "$C" <<'PY'
import json,os,signal,sys,threading,time,urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
p=Path(sys.argv[1]);port=sys.argv[2];c=int(sys.argv[3]);f=json.load(open(p/'fixture.json'));sched=int((p/'scheduler.pid').read_text());gate=threading.Event()
def send(i):
 key=f'c{c}-r1-i{i}';rid=f'profile-c{c}-i{i}';body={'rid':rid,'input_ids':[f['prompts'][key]],'sampling_params':{'temperature':0,'top_p':1,'max_new_tokens':256,'min_new_tokens':256,'logit_bias':{'1':-100,'105':-100,'106':-100},'ignore_eos':False,'stop':[],'stop_strs':[],'stop_token_ids':[]},'return_token_ids':True};gate.wait();q=urllib.request.Request(f'http://127.0.0.1:{port}/generate',data=json.dumps(body).encode(),headers={'Content-Type':'application/json'});o=json.load(urllib.request.urlopen(q,timeout=7200));o=o[0] if isinstance(o,list) and len(o)==1 else o;m=o.get('meta_info',{});assert len(o.get('output_ids',[]))==256 and m.get('cached_tokens')==7168;return {'rid':rid,'cached_tokens':m.get('cached_tokens'),'output':len(o.get('output_ids',[])),'ids':o.get('output_ids',[]),'meta':m}
with ThreadPoolExecutor(max_workers=c) as ex:
 fs=[ex.submit(send,i) for i in range(c)];time.sleep(2);os.kill(sched,signal.SIGUSR1);t=time.time();gate.set();rs=[x.result() for x in fs];time.sleep(float(os.environ.get('PROFILE_HOLD','30')));os.kill(sched,signal.SIGUSR2)
base=Path('/data/sglang-hicache/g2-quasar-runs/20261111T-g2-quasar-radix8k-prefix-e5m2-run4'); recfile=base/('records-c1.json' if c==1 else 'records-c2-c32.json'); old=json.loads(recfile.read_text()); wave=next(r for r in old if r['concurrency']==c and r['round']==1); previous={x['rid'].replace('radix8k-perf-',''):x['output_ids_sha256'] for x in wave['requests']}; import hashlib
for x in rs:
 key=x['rid'].replace('profile-','') + '_0'; x['baseline_output_ids_sha256']=previous.get(key); x['output_ids_sha256']=hashlib.sha256(json.dumps(x['ids'],separators=(',',':')).encode()).hexdigest(); x['output_ids_match_baseline']=x['output_ids_sha256']==x['baseline_output_ids_sha256']
(p/'profile-responses.json').write_text(json.dumps(rs,indent=2)+'\n');(p/'profile-interval.json').write_text(json.dumps({'capture_start_epoch':t,'concurrency':c,'count':len(rs)},indent=2)+'\n');print(json.dumps({'profiles':c,'all_prefix_hit':all(x['cached_tokens']==7168 for x in rs),'all_outputs':all(x['output']==256 for x in rs),'all_greedy_ids_match_baseline':all(x['output_ids_match_baseline'] for x in rs)}))
PY
kill -TERM -- "-$SERVER_PID" 2>/dev/null || kill -TERM "$SERVER_PID" 2>/dev/null || true; sleep 5; kill -KILL -- "-$SERVER_PID" 2>/dev/null || true; SERVER_PID=''; wait "$NSYS_PID"||true;NSYS_PID=''
"$NSYS" stats --report cuda_gpu_kern_sum,cuda_gpu_trace,cuda_gpu_mem_time_sum --format csv --force-overwrite=true "$BASE/nsys.nsys-rep" > "$BASE/nsys-stats.csv" 2> "$BASE/nsys-stats.err" || true
