#!/usr/bin/env bash
# Gate-3 baseline soak driver (Run A: Ready Horizon OFF).
# Mirrors gate2-run2.sh but with a long read-soak phase + nvidia-smi sampler.
# Config-only; does not touch any engine .py.
# Usage: gate3_soak.sh --tag <tag> --agents K [--launch WRAPPER] [--rt RT] [--budget SEC] [--cmax SEC]
set -u

TAG=""
AGENTS=""
LAUNCH="/root/direct-launch-gate1.sh"
RT=400
BUDGET=7200
CMAX=900
WT=4
GPU_INTERVAL=5

while [ $# -gt 0 ]; do
  case "$1" in
    --tag) TAG="$2"; shift 2;;
    --agents) AGENTS="$2"; shift 2;;
    --launch) LAUNCH="$2"; shift 2;;
    --rt) RT="$2"; shift 2;;
    --budget) BUDGET="$2"; shift 2;;
    --cmax) CMAX="$2"; shift 2;;
    --gpu-interval) GPU_INTERVAL="$2"; shift 2;;
    *) echo "unknown arg $1"; exit 2;;
  esac
done
if [ -z "$TAG" ] || [ -z "$AGENTS" ]; then
  echo "usage: gate3_soak.sh --tag <tag> --agents K [--launch W] [--rt N] [--budget S] [--cmax S]"
  exit 2
fi

BASE=/root
EVID="$BASE/evidence-gate3-$TAG"
STORAGE="/data/l3/p2io-gate3-$TAG"
ENGINE_LOG="$BASE/engine-gate3-$TAG.log"
STATUS="$BASE/gate3-$TAG-status.log"
LOCK="/tmp/p2io-gate3-$TAG.lock"

mkdir -p "$EVID"
note() { echo "$(date +%H:%M:%S) $*" | tee -a "$STATUS"; }

if ! mkdir "$LOCK" 2>/dev/null; then
  echo "$(date +%H:%M:%S) duplicate launch blocked (lock $LOCK exists)" | tee -a "$STATUS"
  exit 0
fi
note "== gate3 soak ($TAG) stage: begin agents=$AGENTS wt=$WT rt=$RT budget=${BUDGET}s launch=$LAUNCH =="

find "$STORAGE" -mindepth 1 -delete 2>/dev/null || true
mkdir -p "$STORAGE"

touch /tmp/t38c-on
rm -f /tmp/t38c-probe.log

cd /root
PATH=/root/miniconda3/envs/sglang-patch/bin:$PATH \
  MAX_SIZE=64G \
  SGLANG_HICACHE_EXTENT_BACKEND_FILE_SIZE=96G \
  STORAGE_DIR=$STORAGE L3_BACKEND=extent \
  SGLANG_PORT=8024 \
  setsid nohup bash "$LAUNCH" \
  > "$ENGINE_LOG" 2>&1 < /dev/null &
ENGINE_WRAP=$!
note "engine launched (wrapper pid $ENGINE_WRAP, log $ENGINE_LOG)"

ok=0
for i in $(seq 1 90); do
  code=$(curl -s -o /dev/null -w %{http_code} http://127.0.0.1:8024/health 2>/dev/null)
  if [ "$code" = "200" ]; then ok=1; break; fi
  sleep 10
done
if [ "$ok" != "1" ]; then
  note "FAIL health not 200 (tail: $(tail -c 400 "$ENGINE_LOG" | tr "\n" " "))"
  exit 1
fi
note "engine healthy"

MAIN=$(ps -eo pid,args | grep "python3 -m sglang.launch_server" | grep -v grep | awk '{print $1}' | head -1)
SCHED=$(ps -eo pid,args | grep "sglang::schedul" | grep -v grep | awk '{print $1}' | head -1)
echo "$SCHED" > "$BASE/gate3-$TAG-sched-pid.txt"
note "main pid=$MAIN scheduler pid=${SCHED:-none}"

# nvidia-smi sampler: GPU util + mem every $GPU_INTERVAL seconds -> gpu-util.csv
(
  echo "ts_unix,util_gpu,mem_used_mib"
  while [ -e "$LOCK" ] && kill -0 "$ENGINE_WRAP" 2>/dev/null; do
    line=$(nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader,nounits 2>/dev/null | tr -d ' ')
    echo "$(date +%s),${line:-NA,NA}" >> "$EVID/gpu-util.csv"
    sleep "$GPU_INTERVAL"
  done
) &
SAMP=$!

curl -s http://127.0.0.1:8024/metrics > "$EVID/boot-metrics.txt" 2>/dev/null || true

cd /root/p2-0
SGLANG_PORT=8024 STORAGE_DIR=$STORAGE \
  /root/miniconda3/envs/sglang-patch/bin/python /root/gate2_load.py \
  --agents "$AGENTS" --write-turns "$WT" --read-turns "$RT" \
  --evidence-dir "$EVID" --time-budget "$BUDGET" --client-max-time "$CMAX" \
  --snapshot-interval 5 \
  >> "$EVID/driver.log" 2>&1
DRIVER_RC=$?
note "driver finished rc=$DRIVER_RC"

sleep 3
curl -s http://127.0.0.1:8024/metrics > "$EVID/metrics-final.txt" 2>/dev/null || true
cp /tmp/t38c-probe.log "$EVID/t38c-probe.log" 2>/dev/null || true
grep -a 'Mamba Cache is allocated\|max_mamba_cache_size\|Creating storage backend' "$ENGINE_LOG" \
  | head -5 > "$EVID/engine-alloc.txt" 2>/dev/null || true
grep -a 'evt=restore_success\|evt=restore_disposition\|evt=extent_write\|hicache_dropped\|evt=forced_drop\|evt=prefetch_issued\|evt=prefetch_io_done\|evt=restore_retry\|evt=restore_state' \
  "$ENGINE_LOG" 2>/dev/null | head -200 > "$EVID/engine-events.txt" 2>/dev/null || true

kill -TERM "$MAIN" 2>/dev/null
sleep 20
ALIVE=$(ps -eo pid,comm | grep -cE "sglang::|python3" || true)
GPU=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader 2>/dev/null)
note "engine SIGTERMed, remaining python procs=$ALIVE, gpu_mib=$GPU"

# stop sampler after engine down
kill "$SAMP" 2>/dev/null
wait "$SAMP" 2>/dev/null
sleep 1
rm -f /tmp/t38c-on
rmdir "$LOCK" 2>/dev/null || true
note "== gate3 soak ($TAG) stage: COMPLETE (rc=$DRIVER_RC) =="
echo "GATE3_${TAG}_COMPLETE rc=$DRIVER_RC" >> "$STATUS"
