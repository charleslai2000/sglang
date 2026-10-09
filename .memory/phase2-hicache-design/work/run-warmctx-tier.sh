#!/usr/bin/env bash
# run-warmctx-tier.sh -- run ONE warm-context tier (32k/64k/128k) end-to-end.
# Serial lifecycle for a single tier (call once per tier; GPU is held for the
# duration of this tier and released at the end):
#   pre:  confirm GPU idle (15MiB) and no sglang procs
#   boot: fresh namespace under /data/l3/p2io-warmctx-<tier>, launch engine
#         with MAX_TOTAL_TOKENS sized for the tier
#   load: run gate2_warmctx.py (cold history-build + warm deltas)
#   post: SIGTERM engine by PID, confirm GPU back to 15MiB idle
#
# Usage: run-warmctx-tier.sh <32k|64k|128k> [--sessions N] [--warm-repeats N]
set -u

TIER="${1:?usage: run-warmctx-tier.sh <32k|64k|128k>}"
shift
SESSIONS=3
WARM_REPEATS=3
COLD_MAX_NEW=12
WARM_MAX_NEW=64
while [ $# -gt 0 ]; do
  case "$1" in
    --sessions) SESSIONS="$2"; shift 2;;
    --warm-repeats) WARM_REPEATS="$2"; shift 2;;
    --cold-max-new) COLD_MAX_NEW="$2"; shift 2;;
    --warm-max-new) WARM_MAX_NEW="$2"; shift 2;;
    *) echo "unknown arg $1"; exit 2;;
  esac
done

case "$TIER" in
  32k)  MAXTT=65536;  MINFREE=4G; MAXSZ=32G ;;
  64k)  MAXTT=131072; MINFREE=4G; MAXSZ=32G ;;
  128k) MAXTT=196608; MINFREE=2G; MAXSZ=24G ;;
  *) echo "tier must be 32k|64k|128k"; exit 2 ;;
esac

BASE=/root
EVID="$BASE/evidence-warmctx-$TIER"
STORAGE="/data/l3/p2io-warmctx-$TIER"
ENGINE_LOG="$BASE/engine-warmctx-$TIER.log"
STATUS="$BASE/warmctx-$TIER-status.log"
LOCK="/tmp/warmctx-$TIER.lock"
WRAPPER="$BASE/direct-launch-warmctx.sh"

mkdir -p "$EVID"
note() { echo "$(date +%H:%M:%S) $*" | tee -a "$STATUS"; }

if ! mkdir "$LOCK" 2>/dev/null; then
  echo "$(date +%H:%M:%S) duplicate launch blocked (lock $LOCK exists)" | tee -a "$STATUS"
  exit 0
fi
note "== warmctx tier=$TIER stage: begin sessions=$SESSIONS warm_repeats=$WARM_REPEATS max_total_tokens=$MAXTT =="

# Pre-check: GPU must be idle
GPU=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits 2>/dev/null | tr -d ' ')
if [ "${GPU:-9999}" -gt 64 ]; then
  note "ABORT GPU not idle (mem_used=$GPU MiB) -- another experiment holds the card"
  rmdir "$LOCK" 2>/dev/null || true
  exit 1
fi
note "GPU idle confirmed (mem_used=$GPU MiB)"

# Fresh namespace
find "$STORAGE" -mindepth 1 -delete 2>/dev/null || true
mkdir -p "$STORAGE"

cd /root
PATH=/root/miniconda3/envs/sglang-patch/bin:$PATH \
  MAX_SIZE=$MAXSZ \
  MIN_FREE=$MINFREE \
  MAX_TOTAL_TOKENS=$MAXTT \
  SGLANG_HICACHE_EXTENT_BACKEND_FILE_SIZE=96G \
  STORAGE_DIR=$STORAGE L3_BACKEND=extent \
  SGLANG_PORT=8024 \
  setsid nohup bash "$WRAPPER" \
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
  note "FAIL health not 200 (tail: $(tail -c 600 "$ENGINE_LOG" | tr "\n" " "))"
  rmdir "$LOCK" 2>/dev/null || true
  exit 1
fi
note "engine healthy"

MAIN=$(ps -eo pid,args | grep "python3 -m sglang.launch_server" | grep -v grep | awk '{print $1}' | head -1)
note "main pid=$MAIN"
echo "$MAIN" > "$BASE/warmctx-$TIER-main-pid.txt"

# Boot metrics
curl -s http://127.0.0.1:8024/metrics > "$EVID/boot-metrics.txt" 2>/dev/null || true

# Load: cold history-build + warm deltas
cd /root
SGLANG_PORT=8024 STORAGE_DIR=$STORAGE \
  MODEL_PATH=/root/models/Qwen3.5-9B-w4a16 \
  /root/miniconda3/envs/sglang-patch/bin/python /root/gate2_warmctx.py \
  --tier "$TIER" --sessions "$SESSIONS" --warm-repeats "$WARM_REPEATS" \
  --cold-max-new "$COLD_MAX_NEW" --warm-max-new "$WARM_MAX_NEW" \
  --evidence-dir "$EVID" --client-max-time 900 \
  > "$EVID/driver.log" 2>&1
DRIVER_RC=$?
note "driver finished rc=$DRIVER_RC"

# Post metrics
curl -s http://127.0.0.1:8024/metrics > "$EVID/metrics-final.txt" 2>/dev/null || true
grep -a 'Mamba Cache is allocated\|max_mamba_cache_size\|ExtentFileBackend\|Memory pool\|max_total_tokens' \
  "$ENGINE_LOG" | head -8 > "$EVID/engine-alloc.txt" 2>/dev/null || true
grep -a 'evt=restore_success\|evt=extent_write\|evt=restore_disposition\|evt=prefetch' \
  "$ENGINE_LOG" 2>/dev/null | head -100 > "$EVID/engine-events.txt" 2>/dev/null || true

# Engine teardown by PID + confirm idle
kill -TERM "$MAIN" 2>/dev/null
sleep 20
GPU=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits 2>/dev/null | tr -d ' ')
PROCS=$(ps -eo comm | grep -cE "sglang::" || true)
note "engine SIGTERMed, remaining sglang procs=$PROCS, gpu_mib=$GPU"

rmdir "$LOCK" 2>/dev/null || true
note "== warmctx tier=$TIER COMPLETE rc=$DRIVER_RC =="
echo "WARMCTX_${TIER}_COMPLETE rc=$DRIVER_RC gpu_mib=$GPU" >> "$STATUS"
exit "$DRIVER_RC"
