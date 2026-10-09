#!/usr/bin/env bash
# Phase-2 Decode/Mamba 9-cell runner (tester decbm-e1).
# Fixed matrix: pool{32,64,96} x conc{4,6,8}, all Graph ON, max_new=256.
# Each cell: launch engine (existing wrapper, untouched) -> gen_load -> evidence
# -> SIGTERM engine -> verify cleanup.  Fresh namespace per cell.
#
# Cell evidence: /root/evidence-gen-<pool>c<conc>/
# STORAGE_DIR:   /data/l3/p2io-gen-<pool>c<conc>/   (fresh per cell)
# engine log:    /root/engine-gen-<pool>c<conc>.log
# status:        /root/decbm-gen-<pool>c<conc>-status.log
# master log:    /root/decbm-master.log
#
# Usage: run-p2-decbm-cells.sh [gON|gOFF] [poollist] [conclist]
set -u

GRAPH=${1:-gON}
POOLS=${2:-"32 64 96"}
CONCS=${3:-"4 6 8"}
MAX_NEW=256
TURNS=10
BUDGET=900
SGL=/root/miniconda3/envs/sglang-patch/bin/python
BASE=/root
MASTER="$BASE/decbm-master-$GRAPH.log"

note() { echo "$(date +%H:%M:%S) $*" | tee -a "$MASTER"; }
preflight_ok() {
  # GPU must be idle and port 8024 free, no launch_server running.
  local mem
  mem=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits 2>/dev/null | tr -d ' ')
  if [ -z "$mem" ]; then echo "nvidia-smi failed"; return 1; fi
  if [ "$mem" -gt 200 ] 2>/dev/null; then echo "GPU mem not idle ($mem MiB)"; return 1; fi
  if ss -tln | grep -q ":8024 "; then echo "port 8024 in use"; return 1; fi
  local n
  n=$(ps -eo args | grep "launch_server" | grep -v grep | wc -l)
  if [ "$n" -ne 0 ]; then echo "launch_server procs present ($n)"; return 1; fi
  return 0
}

run_cell() {
  local pool=$1 conc=$2
  local tag="gen-p${pool}-c${conc}"
  local EVID="$BASE/evidence-$tag"
  local STORAGE="/data/l3/p2io-$tag"
  local ENGINE_LOG="$BASE/engine-$tag.log"
  local STATUS="$BASE/decbm-$tag-status.log"
  local LOCK="/tmp/p2io-$tag.lock"
  local wrapper="$BASE/direct-launch-sweep-p${pool}-${GRAPH}.sh"

  mkdir -p "$EVID"
  local cnote; cnote() { echo "$(date +%H:%M:%S) $*" | tee -a "$STATUS"; }

  cnote "== cell $tag begin: pool=$pool conc=$conc graph=$GRAPH max_new=$MAX_NEW turns=$TURNS budget=$BUDGET wrapper=$wrapper =="

  if [ ! -x "$wrapper" ]; then
    cnote "FAIL wrapper missing: $wrapper"; return 2
  fi
  if ! preflight_ok > /tmp/preflight-$tag.txt 2>&1; then
    cnote "FAIL preflight: $(cat /tmp/preflight-$tag.txt)"; return 3
  fi
  cnote "preflight OK (gpu idle, port free)"

  if ! mkdir "$LOCK" 2>/dev/null; then
    cnote "FAIL lock exists $LOCK"; return 3
  fi

  # fresh namespace (dir does not exist for new cell names; create clean)
  if [ ! -d "$STORAGE" ]; then mkdir -p "$STORAGE"; fi
  cnote "storage=$STORAGE"

  cd /root
  PATH=/root/miniconda3/envs/sglang-patch/bin:$PATH \
    MAX_SIZE=64G \
    SGLANG_HICACHE_EXTENT_BACKEND_FILE_SIZE=96G \
    STORAGE_DIR=$STORAGE L3_BACKEND=extent \
    SGLANG_PORT=8024 \
    setsid nohup bash "$wrapper" \
    > "$ENGINE_LOG" 2>&1 < /dev/null &
  local wrap=$!
  cnote "engine launched (wrapper pid $wrap)"

  local ok=0
  for i in $(seq 1 90); do
    local code
    code=$(curl -s -o /dev/null -w %{http_code} http://127.0.0.1:8024/health 2>/dev/null)
    if [ "$code" = "200" ]; then ok=1; break; fi
    if ! kill -0 "$wrap" 2>/dev/null; then
      cnote "FAIL engine process exited during boot (tail: $(tail -c 400 "$ENGINE_LOG" | tr "\n" " "))"
      rmdir "$LOCK" 2>/dev/null || true
      return 4
    fi
    sleep 10
  done
  if [ "$ok" != "1" ]; then
    cnote "FAIL health not 200 (tail: $(tail -c 400 "$ENGINE_LOG" | tr "\n" " "))"
    kill -TERM "$wrap" 2>/dev/null
    sleep 10
    rmdir "$LOCK" 2>/dev/null || true
    return 4
  fi
  cnote "engine healthy"

  local main
  main=$(ps -eo pid,args | grep "python3 -m sglang.launch_server" | grep -v grep | awk '{print $1}' | head -1)
  cnote "main pid=$main"

  curl -s http://127.0.0.1:8024/metrics > "$EVID/boot-metrics.txt" 2>/dev/null || true
  grep -a 'Mamba Cache is allocated\|max_mamba_cache_size\|Creating storage backend\|Capture target decode CUDA graph' \
    "$ENGINE_LOG" | head -10 > "$EVID/engine-alloc.txt" 2>/dev/null || true

  # GPU sampler (subshell: no `local` inside)
  (
    echo "ts_unix,util_gpu,mem_used_mib"
    while [ -e "$LOCK" ] && kill -0 "$wrap" 2>/dev/null; do
      line=$(nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader,nounits 2>/dev/null | tr -d ' ')
      echo "$(date +%s),${line:-NA,NA}" >> "$EVID/gpu-util.csv"
      sleep 5
    done
  ) &
  local samp=$!

  # load driver (fixed trace; only --agents varies)
  cd /root/p2-0
  SGLANG_PORT=8024 STORAGE_DIR=$STORAGE \
    "$SGL" /root/gen_load.py --agents "$conc" --max-new "$MAX_NEW" --turns "$TURNS" \
      --budget "$BUDGET" --evidence-dir "$EVID" \
      >> "$EVID/driver.log" 2>&1
  local drc=$?
  cnote "driver finished rc=$drc"

  sleep 3
  curl -s http://127.0.0.1:8024/metrics > "$EVID/metrics-final.txt" 2>/dev/null || true

  # engine crash detection (OOM etc.)
  local oom
  oom=$(grep -a -i "CUDA out of memory\|OutOfMemoryError\|CUDA error\|exit code: -9\|SIGKILL" "$ENGINE_LOG" | tail -5)
  if [ -n "$oom" ]; then
    echo "$oom" > "$EVID/oom-evidence.txt"
    cnote "OOM/CRASH evidence: $oom"
  fi
  grep -a 'evt=' "$ENGINE_LOG" 2>/dev/null | head -100 > "$EVID/engine-events.txt" 2>/dev/null || true

  # engine teardown
  kill -TERM "$main" 2>/dev/null
  sleep 20
  local alive
  alive=$(ps -eo comm | grep -cE "python3|sglang::" || true)
  local gpu
  gpu=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader 2>/dev/null | tr -d ' ')
  cnote "engine SIGTERMed, remaining python/sglang procs=$alive, gpu_mib=$gpu"

  kill "$samp" 2>/dev/null
  wait "$samp" 2>/dev/null
  sleep 1
  rmdir "$LOCK" 2>/dev/null || true

  # summary line
  local req comp gtoks
  req=$(grep -o '"requests_total": [0-9]*' "$EVID"/run-*/verdict.json 2>/dev/null | head -1 | grep -o '[0-9]*')
  comp=$(grep -o '"requests_completed": [0-9]*' "$EVID"/run-*/verdict.json 2>/dev/null | head -1 | grep -o '[0-9]*')
  gtoks=$(grep -o '"generation_tokens_total": [0-9]*' "$EVID"/run-*/verdict.json 2>/dev/null | head -1 | grep -o '[0-9]*')
  cnote "SUMMARY cell=$tag rc=$drc requests=${req:-NA} completed=${comp:-NA} gen_tokens=${gtoks:-NA} oom=${oom:-none} final_gpu_mib=$gpu"
  note "CELL_DONE $tag rc=$drc requests=${req:-NA} completed=${comp:-NA} gen_tokens=${gtoks:-NA} oom=${oom:-none}"
  return 0
}

note "== decbm $GRAPH sweep begin: pools=($POOLS) concs=($CONCS) max_new=$MAX_NEW turns=$TURNS budget=$BUDGET =="
for pool in $POOLS; do
  for conc in $CONCS; do
    run_cell "$pool" "$conc"
  done
done
note "== decbm $GRAPH sweep COMPLETE =="
echo "DECBM_${GRAPH}_COMPLETE rc=0" >> "$MASTER"
