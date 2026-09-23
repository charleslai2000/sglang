#!/usr/bin/env bash
# Gate2 two-phase run driver: write-saturate then read-verify.
# Usage: gate2-run2.sh --tag <tag> --agents K [--write-turns W] [--read-turns R]
set -u

TAG=""
AGENTS=""
WT=4
RT=8

while [ $# -gt 0 ]; do
  case "$1" in
    --tag) TAG="$2"; shift 2;;
    --agents) AGENTS="$2"; shift 2;;
    --write-turns) WT="$2"; shift 2;;
    --read-turns) RT="$2"; shift 2;;
    *) echo "unknown arg $1"; exit 2;;
  esac
done
if [ -z "$TAG" ] || [ -z "$AGENTS" ]; then
  echo "usage: gate2-run2.sh --tag <tag> --agents K [--write-turns W] [--read-turns R]"
  exit 2
fi

BASE=/root
EVID="$BASE/evidence-gate2-$TAG"
STORAGE="/data/l3/p2io-gate2-$TAG"
ENGINE_LOG="$BASE/engine-gate2-$TAG.log"
STATUS="$BASE/gate2-$TAG-status.log"
LOCK="/tmp/p2io-gate2-$TAG.lock"

mkdir -p "$EVID"
note() { echo "$(date +%H:%M:%S) $*" | tee -a "$STATUS"; }

if ! mkdir "$LOCK" 2>/dev/null; then
  echo "$(date +%H:%M:%S) duplicate launch blocked (lock $LOCK exists)" | tee -a "$STATUS"
  exit 0
fi
note "== gate2 ($TAG) stage: begin agents=$AGENTS wt=$WT rt=$RT =="

find "$STORAGE" -mindepth 1 -delete 2>/dev/null || true
mkdir -p "$STORAGE"

touch /tmp/t38c-on
rm -f /tmp/t38c-probe.log

cd /root
PATH=/root/miniconda3/envs/sglang-patch/bin:$PATH STORAGE_DIR=$STORAGE L3_BACKEND=extent \
  SGLANG_PORT=8024 setsid nohup bash /root/direct-launch-gate1.sh \
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
echo "$SCHED" > "$BASE/gate2-$TAG-sched-pid.txt"
note "main pid=$MAIN scheduler pid=$SCHED"

curl -s http://127.0.0.1:8024/metrics > "$EVID/boot-metrics.txt" 2>/dev/null || true

cd /root/p2-0
SGLANG_PORT=8024 STORAGE_DIR=$STORAGE \
  /root/miniconda3/envs/sglang-patch/bin/python /root/gate2_load.py \
  --agents "$AGENTS" --write-turns "$WT" --read-turns "$RT" \
  --evidence-dir "$EVID" --time-budget 10800 --client-max-time 900 \
  >> "$EVID/driver.log" 2>&1
DRIVER_RC=$?
note "driver finished rc=$DRIVER_RC"

sleep 3
curl -s http://127.0.0.1:8024/metrics > "$EVID/metrics-final.txt" 2>/dev/null || true
cp /tmp/t38c-probe.log "$EVID/t38c-probe.log" 2>/dev/null || true
grep -a 'Mamba Cache is allocated\|max_mamba_cache_size' "$ENGINE_LOG" \
  | head -3 > "$EVID/mamba-alloc.txt" 2>/dev/null || true
grep -a 'evt=restore_success\|evt=restore_disposition\|evt=extent_write\|hicache_dropped\|pc_outcome\|pc_storage_query' \
  "$ENGINE_LOG" 2>/dev/null | head -60 > "$EVID/engine-events.txt" 2>/dev/null || true

kill -TERM "$MAIN" 2>/dev/null
sleep 20
ALIVE=$(ps -eo pid,comm | grep -cE "sglang::|python3" || true)
GPU=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader 2>/dev/null)
note "engine SIGTERMed, remaining python procs=$ALIVE, gpu_mib=$GPU"
rm -f /tmp/t38c-on
rmdir "$LOCK" 2>/dev/null || true
note "== gate2 ($TAG) stage: COMPLETE (rc=$DRIVER_RC) =="
echo "GATE2_${TAG}_COMPLETE rc=$DRIVER_RC" >> "$STATUS"
