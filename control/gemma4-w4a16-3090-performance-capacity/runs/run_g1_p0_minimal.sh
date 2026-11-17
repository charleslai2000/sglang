#!/usr/bin/env bash
# Minimal real-request validation of production on_idle sanity and safe cleanup.
set -Eeuo pipefail
ROOT=/home/ubuntu/workspaces/3rdparty/sglang-hicache
VENV=/home/ubuntu/venvs/sglang-3090
DATA=/data/sglang-hicache/gemma4
LOCK=/tmp/f1-r16b-gpu-exclusive.lock
PORT=31401
BASE_OUT=/data/sglang-hicache/gemma4/runs/20261117T-g1-p0-minimal
OUT="$BASE_OUT/minimal-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$OUT"
exec 9>"$LOCK"
flock -n 9 || { echo GPU_LOCK_BUSY >&2; exit 90; }
ss -ltn | grep -q ":$PORT\\b" && { echo PORT_BUSY >&2; exit 91; } || true
if nvidia-smi --query-compute-apps=pid --format=csv,noheader | grep -q '[0-9]'; then
  echo GPU_PROCESS_BUSY >&2; exit 92
fi
export G1_GPU_LOCK_HELD=1 G1_PROD_OUT="$OUT/service" G1_PROD_PORT="$PORT"
export G1_PROD_KV=fp8_e5m2 G1_PROD_CONTEXT=131072 G1_PROD_MAX_RUNNING=32
export G1_PROD_MEM_FRACTION=.90 G1_PROD_GRAPH_BS=32 G1_PROD_RADIX=on G1_PROD_WARMUP=off
export G1_PROD_HICACHE=on G1_PROD_HICACHE_SIZE=2 G1_PROD_L3_DIR="$OUT/l3-extent"
export SGLANG_TREE_LIFECYCLE_TRACE=1 G1_P0_SANITY_RESULT_MARKER="$OUT/scheduler-lifecycle.markers"
export G1_P0_SANITY_PHASE=startup
PID=''
cleanup() {
  rc=$?
  trap - EXIT INT TERM
  if [[ -n "$PID" ]] && kill -0 "$PID" 2>/dev/null; then kill -TERM "$PID" 2>/dev/null || true; wait "$PID" || true; fi
  printf 'cleanup_exit=%s\n' "$rc" >> "$OUT/lifecycle.status"
  nvidia-smi --query-gpu=timestamp,utilization.gpu,memory.used --format=csv,noheader > "$OUT/gpu-after.csv" 2>&1 || true
  ss -ltnp | grep ":$PORT\\b" > "$OUT/port-after.txt" 2>&1 || true
}
trap cleanup EXIT
"$ROOT/control/gemma4-w4a16-3090-performance-capacity/runs/run_g1_prod_e5m2.sh" > "$OUT/service-launch.log" 2>&1 &
PID=$!
echo "launcher_pid=$PID" > "$OUT/lifecycle.status"
for _ in $(seq 1 1800); do
  if curl -fsS "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; then break; fi
  kill -0 "$PID" 2>/dev/null || { tail -80 "$OUT/service-launch.log"; exit 2; }
  sleep 1
done
curl -fsS "http://127.0.0.1:$PORT/health" >/dev/null
export G1_P0_SANITY_PHASE=production_on_idle
"$VENV/bin/python" - "$PORT" "$OUT" <<'PY'
import json, sys, time, urllib.request
from pathlib import Path
port, out = int(sys.argv[1]), Path(sys.argv[2])
url=f"http://127.0.0.1:{port}"
fixture=json.load(open('/data/sglang-hicache/gemma4/runs/20261115T-g1-prod-e5m2-hicache/shared-prefix-64k.json'))
ids=fixture['requests'][0]['input_ids'][:128]
body=json.dumps({'input_ids':[ids], 'sampling_params':{'temperature':0,'top_p':1,'max_new_tokens':1,'min_new_tokens':1,'ignore_eos':True}, 'return_token_ids':True}).encode()
req=urllib.request.Request(url+'/generate',data=body,headers={'Content-Type':'application/json'})
response=json.load(urllib.request.urlopen(req,timeout=300)); (out/'request.json').write_text(json.dumps(response,indent=2)+'\n')
cutoff=time.monotonic()+180
last=[]; quiet_since=None
while time.monotonic()<cutoff:
  state=json.load(urllib.request.urlopen(url+'/server_info',timeout=5))['internal_states']
  assert state, 'server_info has no scheduler internal_states'
  last=[]
  for s in state:
    p=s.get('g1_p0_hicache_pending',{})
    last.append({k:p.get(k) for k in ('running','waiting','result_queue','write_through','load_back','prefetch','backup','ongoing_backup','buffer_pipeline_idle')})
  idle=all(s.get('g1_p0_is_fully_idle') is True and all(
    p.get(k,0)==0 for k in ('running','waiting','result_queue','write_through','load_back','prefetch','backup','ongoing_backup')
  ) and p.get('buffer_pipeline_idle') is True for s in state)
  if idle:
    quiet_since=quiet_since or time.monotonic()
    if time.monotonic()-quiet_since>=5:
      out.joinpath('idle.json').write_text(json.dumps({'observed':True,'quiet_seconds':5,'state':last,'observed_at':time.time()},indent=2)+'\n')
      break
  else: quiet_since=None
  time.sleep(1)
else:
  out.joinpath('idle.json').write_text(json.dumps({'observed':False,'blocking_state':last,'observed_at':time.time()},indent=2)+'\n')
  raise SystemExit('idle timeout at 180s')
PY
if grep -q 'G1_P0_SANITY_CHECK_RESULT phase=production_on_idle status=PASS' "$OUT/scheduler-lifecycle.markers"; then
  echo 'sanity_check_executed=1 phase=production_on_idle result=PASS' >> "$OUT/lifecycle.status"
else
  echo 'sanity_check_executed=0 phase=production_on_idle result=UNKNOWN' >> "$OUT/lifecycle.status"
  exit 11
fi
kill -TERM "$PID" 2>/dev/null || true
wait "$PID" || true
PID=''
echo 'service_cleanup_complete=1' >> "$OUT/lifecycle.status"
echo "$OUT"
