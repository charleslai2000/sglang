#!/usr/bin/env bash
# Bounded startup-only capacity measurement. No requests are sent.
set -Eeuo pipefail
ROOT=/home/ubuntu/workspaces/3rdparty/sglang-hicache
PROD_RUNS=$ROOT/control/gemma4-w4a16-3090-performance-capacity/runs
VENV=/home/ubuntu/venvs/sglang-3090
OUT=${G1_CAPACITY_OUT:?set G1_CAPACITY_OUT}
PORT=${G1_CAPACITY_PORT:-31401}
LOCK=/tmp/f1-r16b-gpu-exclusive.lock
[[ ! -e "$OUT" ]] || { echo "OUTPUT_DIRECTORY_ALREADY_EXISTS:$OUT" >&2; exit 79; }
mkdir -p "$OUT"
[[ $(df -PB1 "$OUT" | awk 'NR==2 {print $4}') -gt 40000000000 ]] || { echo DISK_SPACE_BELOW_40GB >&2; exit 81; }
exec 9>"$LOCK"
flock -n 9 || { echo GPU_LOCK_BUSY >&2; exit 90; }
ss -ltn | grep -q ":$PORT\\b" && { echo "PORT_BUSY:$PORT" >&2; exit 91; } || true
if nvidia-smi --query-compute-apps=pid --format=csv,noheader | grep -q '[0-9]'; then echo GPU_PROCESS_BUSY >&2; exit 92; fi
export G1_PROD_OUT="$OUT/service" G1_PROD_PORT="$PORT" G1_GPU_LOCK_HELD=1
export G1_PROD_KV=fp8_e5m2 G1_PROD_CONTEXT=131072 G1_PROD_MAX_RUNNING=32
export G1_PROD_MAX_TOTAL_TOKENS=${G1_CAPACITY_MAX_TOTAL_TOKENS:-172032} G1_PROD_MEM_FRACTION=${G1_CAPACITY_MEM_FRACTION:-.90}
export G1_PROD_GRAPH_BS=32 G1_PROD_RADIX=on G1_PROD_HICACHE=on
export G1_PROD_HICACHE_SIZE=${G1_CAPACITY_HICACHE_SIZE_GB:-4}
export G1_PROD_L3_DIR="$OUT/service/l3-extent" G1_PROD_WARMUP=off G1_PROD_EXPORT_REQUEST_METRICS=off
export G1_PROD_EXTENT_SIZE=67108864 G1_PROD_EXTENT_FILE_SIZE=34359738368
export G1_PROD_EXTENT_MAX_SIZE=34359738368 G1_PROD_EXTENT_MIN_FREE_SPACE=10737418240
printf 'start_epoch=%s\nport=%s\nmax_total_tokens=%s\nhicache_size_decimal_gb=%s\nextent_file_bytes=34359738368\nworktree_head=%s\nprobe=no_requests_startup_capacity_only\ntimeout_s=1800\n' \
  "$(date +%s)" "$PORT" "$G1_PROD_MAX_TOTAL_TOKENS" "$G1_PROD_HICACHE_SIZE" "$(git -C "$ROOT" rev-parse HEAD)" > "$OUT/identity.txt"
df -PB1 "$OUT" > "$OUT/disk-before.txt"
"$PROD_RUNS/run_g1_prod_e5m2.sh" 9>&- > "$OUT/launcher.log" 2>&1 &
LAUNCHER=$!
printf 'launcher_pid=%s\n' "$LAUNCHER" >> "$OUT/identity.txt"
cleanup() {
  local rc=$?
  trap - EXIT TERM INT
  set +e
  if kill -0 "$LAUNCHER" 2>/dev/null; then
    kill -TERM "$LAUNCHER" 2>/dev/null
    for _ in $(seq 1 300); do
      state=$(ps -o stat= -p "$LAUNCHER" 2>/dev/null | awk 'NR==1 {print $1}')
      [[ -z "$state" || "$state" == Z* || "$state" == X* ]] && break
      sleep 1
    done
    state=$(ps -o stat= -p "$LAUNCHER" 2>/dev/null | awk 'NR==1 {print $1}')
    if [[ -n "$state" && "$state" != Z* && "$state" != X* ]]; then
      echo "launcher_cleanup_timeout=1" >> "$OUT/identity.txt"
      kill -KILL "$LAUNCHER" 2>/dev/null
    fi
  fi
  wait "$LAUNCHER" 2>/dev/null
  printf 'cleanup_epoch=%s\nprobe_exit=%s\n' "$(date +%s)" "$rc" >> "$OUT/identity.txt"
  nvidia-smi --query-gpu=timestamp,utilization.gpu,memory.used --format=csv,noheader > "$OUT/gpu-after.csv" 2>&1
  ss -ltnp | grep ":$PORT\\b" > "$OUT/port-after.txt" 2>&1 || true
  exit "$rc"
}
trap cleanup EXIT
trap 'exit 143' TERM
trap 'exit 130' INT
ready=0
for _ in $(seq 1 1200); do
  if curl -fsS "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; then ready=1; break; fi
  if ! kill -0 "$LAUNCHER" 2>/dev/null; then tail -100 "$OUT/launcher.log" >&2; exit 2; fi
  sleep 1
done
[[ $ready == 1 ]] || { echo SERVICE_READINESS_TIMEOUT >&2; exit 3; }
printf 'service_ready_epoch=%s\n' "$(date +%s)" >> "$OUT/identity.txt"
curl -fsS "http://127.0.0.1:$PORT/metrics" > "$OUT/metrics.txt"
curl -fsS "http://127.0.0.1:$PORT/server_info" > "$OUT/server_info.json"
curl -fsS "http://127.0.0.1:$PORT/model_info" > "$OUT/model_info.json"
df -PB1 "$OUT" > "$OUT/disk-at-ready.txt"
printf 'capacity_snapshot_epoch=%s\n' "$(date +%s)" >> "$OUT/identity.txt"
# The only purpose of this process is to expose startup allocation logs/gauges.
# Stop the owned service immediately; do not submit a generation or cache request.
kill -TERM "$LAUNCHER"
wait "$LAUNCHER" || true
python3 - "$OUT" <<'PY'
import json, re, sys
from pathlib import Path
out = Path(sys.argv[1])
metrics = (out / "metrics.txt").read_text(errors="replace")
log = (out / "service/server.log").read_text(errors="replace")
names = (
    "sglang:max_total_num_tokens", "sglang:max_total_num_tokens_swa",
    "sglang:hicache_host_total_tokens", "sglang:hicache_host_used_tokens",
    "sglang:hicache_kv_pool_tokens", "sglang:hicache_kv_host_usable_tokens",
    "sglang:hicache_usable_tokens",
)
def series(name):
    found = {}
    for line in metrics.splitlines():
        if line.startswith(name + "{") or line.startswith(name + " "):
            label, _, value = line.partition(" ")
            try: found[label] = float(value)
            except ValueError: pass
    return found
pools = {}
for m in re.finditer(r"Allocating (full|swa) hierarchical KV host pool: (\d+) tokens, ([0-9.]+) GB host memory", log, re.I):
    pools[m.group(1).lower()] = {"tokens": int(m.group(2)), "host_memory_gb": float(m.group(3))}
maxima = {}
for name in ("max_total_num_tokens=",):
    maxima[name] = re.findall(re.escape(name) + r"(\d+)", log)
result = {
    "schema": "gemma4.hicache.startup_capacity_probe.v1",
    "identity": (out / "identity.txt").read_text(),
    "gpu_pool_capacity_gauges": {n: series(n) for n in names[:2]},
    "hicache_pool_gauges": {n: series(n) for n in names[2:]},
    "distinct_host_pool_allocations": pools,
    "host_pools_distinct_full_swa": set(pools) == {"full", "swa"},
    "configured_max_total_log": maxima,
    "hicache_warnings": [line for line in log.splitlines() if "host pool" in line.lower() and "smaller than" in line.lower()],
    "request_count": 0,
    "claim_scope": "startup allocation only; no cache movement/restore, throughput, correctness, idle sanity, or acceptance claims",
}
(out / "capacity.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps({k: result[k] for k in ("gpu_pool_capacity_gauges", "distinct_host_pool_allocations", "hicache_warnings", "request_count")}, indent=2))
PY
