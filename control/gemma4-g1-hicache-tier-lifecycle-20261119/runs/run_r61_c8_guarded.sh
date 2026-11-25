#!/usr/bin/env bash
# Fail-closed C-8 launcher: bound the workload and hold the exclusive GPU lock.
set -Eeuo pipefail
ROOT=/home/ubuntu/workspaces/3rdparty/sglang-hicache
OUT=${OUT:?set OUT}
MODE=${MODE:-C}
RATE=${RATE:-8}
PORT=${PORT:-31401}
mkdir -p "$OUT"
exec 9>/tmp/f1-r16b-gpu-exclusive.lock
flock -n 9 || { echo GPU_LOCK_BUSY >&2; exit 90; }
export G1_GPU_LOCK_HELD=1
if ss -ltn | grep -Eq ":${PORT}\\b"; then echo PORT_BUSY >&2; exit 91; fi
if nvidia-smi --query-compute-apps=pid --format=csv,noheader | grep -Eq '^[0-9]+'; then echo GPU_PROCESS_BUSY >&2; exit 92; fi
nvidia-smi --query-gpu=timestamp,utilization.gpu,memory.used --format=csv > "$OUT/gpu-before.csv"
df -h /data > "$OUT/disk-before.txt"
printf 'started=%s mode=%s rate=%s port=%s head=%s\n' "$(date -Is)" "$MODE" "$RATE" "$PORT" "$(git -C "$ROOT" rev-parse HEAD)" > "$OUT/launch-intent.txt"
set +e
MODE="$MODE" RATE="$RATE" PORT="$PORT" SAMPLER=1 OUT="$OUT" timeout -k 30 6000 /tmp/run_c8_capture.sh > "$OUT/wrapper.log" 2>&1
RC=$?
set -e
printf 'wrapper_exit=%s finished=%s\n' "$RC" "$(date -Is)" > "$OUT/guarded-exit.txt"
nvidia-smi --query-gpu=timestamp,utilization.gpu,memory.used --format=csv > "$OUT/gpu-after.csv" 2>&1 || true
ss -ltnp | grep -E ":${PORT}\\b" > "$OUT/port-after.txt" 2>&1 || true
exit "$RC"
