#!/usr/bin/env bash
# Phase-2 cap e3: ratio-sweep runner (protocol §②).
# Usage: cap-ratio-run.sh --tag cX --ratio R --drv <path-to-cap_ratio_driver.py>
# Each tier: fresh namespace boot (ratio is the only sweep variable; all other
# flags fixed by direct-launch-cap-ratio.sh) -> cap_ratio_driver run -> collect
# boot-metrics / engine-alloc / mid-run / metrics-final -> SIGTERM engine ->
# confirm GPU back to idle.  Config/test-harness only.
set -u
TAG=""
RATIO=""
DRV="/root/cap_ratio_driver.py"
while [ $# -gt 0 ]; do
  case "$1" in
    --tag) TAG="$2"; shift 2;;
    --ratio) RATIO="$2"; shift 2;;
    --drv) DRV="$2"; shift 2;;
    *) echo "unknown arg $1"; exit 2;;
  esac
done
if [ -z "$TAG" ] || [ -z "$RATIO" ]; then
  echo "usage: cap-ratio-run.sh --tag <cX> --ratio <r> [--drv <path>]"; exit 2
fi

BASE=/root
EVID="/root/evidence-cap-sweep/$TAG"
STORAGE="/data/l3/p2io-cap-ratio-$TAG"
ENGINE_LOG="$BASE/engine-cap-ratio-$TAG.log"
STATUS="$BASE/cap-ratio-$TAG-status.log"
LOCK="/tmp/p2io-cap-ratio-$TAG.lock"
MAX_SIZE_ENV=200G
MTOKENS=600000        # top-grade; memory-computed pool wins unless it clamps (R2)
GPU_INTERVAL=5

mkdir -p "$EVID"
note() { echo "$(date +%H:%M:%S) $*" | tee -a "$STATUS"; }

if ! mkdir "$LOCK" 2>/dev/null; then
  echo "$(date +%H:%M:%S) duplicate launch blocked (lock $LOCK exists)" | tee -a "$STATUS"
  exit 0
fi
note "== cap-ratio ($TAG) stage: begin ratio=$RATIO =="
note "== capacity: MAX_SIZE=$MAX_SIZE_ENV MAX_TOTAL_TOKENS=$MTOKENS =="

find "$STORAGE" -mindepth 1 -delete 2>/dev/null || true
mkdir -p "$STORAGE"

cd /root
PATH=/root/miniconda3/envs/sglang-patch/bin:$PATH \
  MAX_SIZE=$MAX_SIZE_ENV \
  STORAGE_DIR=$STORAGE L3_BACKEND=extent \
  SGLANG_PORT=8024 MAX_TOTAL_TOKENS=$MTOKENS \
  KV_DTYPE=fp8_e4m3 MAMBA_RATIO=$RATIO \
  setsid nohup bash /root/direct-launch-cap-ratio.sh \
  > "$ENGINE_LOG" 2>&1 < /dev/null &
ENGINE_WRAP=$!
note "engine launched (wrapper pid $ENGINE_WRAP, log $ENGINE_LOG)"

ok=0
for i in $(seq 1 120); do
  code=$(curl -s -o /dev/null -w %{http_code} http://127.0.0.1:8024/health 2>/dev/null)
  if [ "$code" = "200" ]; then ok=1; break; fi
  sleep 10
done
if [ "$ok" != "1" ]; then
  note "FAIL health not 200 (tail: $(tail -c 500 "$ENGINE_LOG" | tr "\n" " "))"
  rmdir "$LOCK" 2>/dev/null || true
  exit 1
fi
note "engine healthy"

SCHED=$(ps -eo pid,args | grep "sglang::schedul" | grep -v grep | awk '{print $1}' | head -1)
echo "$SCHED" > "$BASE/cap-ratio-$TAG-sched-pid.txt"
note "scheduler pid=${SCHED:-none}"

# nvidia-smi sampler
(
  echo "ts_unix,util_gpu,mem_used_mib"
  while [ -e "$LOCK" ] && kill -0 "$ENGINE_WRAP" 2>/dev/null; do
    line=$(nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader,nounits 2>/dev/null | tr -d ' ')
    echo "$(date +%s),${line:-NA,NA}" >> "$EVID/gpu-util.csv"
    sleep "$GPU_INTERVAL"
  done
) &
SAMP=$!

sleep 5
curl -s http://127.0.0.1:8024/metrics > "$EVID/boot-metrics.txt" 2>/dev/null || true

CAP_TAG=$TAG CAP_RATIO=$RATIO \
SGLANG_PORT=8024 STORAGE_DIR=$STORAGE \
  /root/miniconda3/envs/sglang-patch/bin/python "$DRV" \
  --tag "$TAG" --ratio "$RATIO" \
  --evidence-dir "$EVID" \
  >> "$EVID/driver.log" 2>&1
DRIVER_RC=$?
note "driver finished rc=$DRIVER_RC"

sleep 3
curl -s http://127.0.0.1:8024/metrics > "$EVID/metrics-final.txt" 2>/dev/null || true
grep -a -E 'Mamba Cache is allocated|max_mamba_cache_size|Creating storage backend|ExtentFileBackend|KV Cache|kv_cache_dtype|fp8|max_running_requests was reduced|max_total_tokens=.*larger than the profiled value' \
  "$ENGINE_LOG" | head -20 > "$EVID/engine-alloc.txt" 2>/dev/null || true
grep -a -E 'evt=restore_success|evt=restore_disposition|evt=extent_write|hicache_dropped|evt=forced_drop|evt=prefetch_issued|evt=prefetch_io_done|evt=restore_retry|evt=restore_state|evt=extent_recycle|evt=restore_recompute|DEVICE_QUOTA|restore_recompute|restore.*timeout' \
  "$ENGINE_LOG" 2>/dev/null > "$EVID/engine-events.txt" 2>/dev/null || true

kill -TERM "$SCHED" 2>/dev/null
sleep 20
ALIVE=$(ps -eo pid,comm | grep -cE "sglang::|python3" || true)
GPU=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader 2>/dev/null)
note "engine SIGTERMed, remaining python procs=$ALIVE, gpu_mib=$GPU"

kill "$SAMP" 2>/dev/null
wait "$SAMP" 2>/dev/null
sleep 1
rmdir "$LOCK" 2>/dev/null || true
note "== cap-ratio ($TAG) stage: COMPLETE (rc=$DRIVER_RC) =="
echo "CAP_RATIO_${TAG}_COMPLETE rc=$DRIVER_RC" >> "$STATUS"
exit "$DRIVER_RC"