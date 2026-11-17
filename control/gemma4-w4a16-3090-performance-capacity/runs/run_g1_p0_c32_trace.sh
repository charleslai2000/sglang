#!/usr/bin/env bash
# One-shot P0 fault diagnostic. A run is complete only when the scheduler emits
# the explicit sanity_check completion marker after the client batch completes.
set -Eeuo pipefail
ROOT=/home/ubuntu/workspaces/3rdparty/sglang-hicache
VENV=/home/ubuntu/venvs/sglang-3090
DATA=/data/sglang-hicache/gemma4
BASE_OUT=${G1_P0_TRACE_OUT:?set G1_P0_TRACE_OUT}
PORT=${G1_PROD_PORT:-31401}
FIXTURE=${G1_P0_TRACE_FIXTURE:-$DATA/runs/20261115T-g1-prod-e5m2-hicache/shared-prefix-64k.json}
LOCK=/tmp/f1-r16b-gpu-exclusive.lock
OUT="$BASE_OUT/c32-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$OUT/c32"

# Refuse overlap; never delete the lock. The launcher owns this flock for its lifetime.
exec 9>"$LOCK"
flock -n 9 || { echo 'GPU_LOCK_BUSY' >&2; exit 90; }
if ss -ltn | grep -q ":$PORT\\b"; then echo "PORT_BUSY:$PORT" >&2; exit 91; fi
if nvidia-smi --query-compute-apps=pid --format=csv,noheader | grep -q '[0-9]'; then
  echo 'GPU_PROCESS_BUSY' >&2
  exit 92
fi

export SGLANG_TREE_LIFECYCLE_TRACE=1 G1_P0_EXPORT_TREE_EVENTS=1 G1_GPU_LOCK_HELD=1
export G1_P0_SANITY_RESULT_MARKER="$OUT/scheduler-lifecycle.markers"
export G1_P0_SANITY_PHASE=startup
export G1_PROD_OUT="$OUT" G1_PROD_PORT="$PORT"
export G1_PROD_KV=fp8_e5m2 G1_PROD_CONTEXT=131072 G1_PROD_MAX_RUNNING=32
export G1_PROD_MEM_FRACTION=.90 G1_PROD_GRAPH_BS=32 G1_PROD_RADIX=on G1_PROD_WARMUP=off
export G1_PROD_HICACHE=on G1_PROD_HICACHE_SIZE=2 G1_PROD_L3_DIR="$OUT/l3-extent"

LAUNCHER_PID=''
cleanup() {
  rc=$?
  trap - EXIT INT TERM
  if [[ -n "$LAUNCHER_PID" ]] && kill -0 "$LAUNCHER_PID" 2>/dev/null; then
    kill -TERM "$LAUNCHER_PID" 2>/dev/null || true
    wait "$LAUNCHER_PID" || true
  fi
  if [[ -f "$OUT/watchdog.pid" ]]; then
    watchdog_pid=$(<"$OUT/watchdog.pid")
    kill -TERM "$watchdog_pid" 2>/dev/null || true
  fi
  printf 'launcher_cleanup_exit=%s\n' "$rc" >> "$OUT/lifecycle.status"
  nvidia-smi --query-gpu=timestamp,utilization.gpu,memory.used --format=csv,noheader > "$OUT/gpu-after.csv" 2>&1 || true
  ss -ltnp | grep ":$PORT\\b" > "$OUT/port-after.txt" 2>&1 || true
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

export G1_P0_SANITY_RESULT_MARKER="$OUT/scheduler-lifecycle.markers"
"$ROOT/control/gemma4-w4a16-3090-performance-capacity/runs/run_g1_prod_e5m2.sh" \
  > "$OUT/launcher.log" 2>&1 &
LAUNCHER_PID=$!
printf 'launcher_pid=%s\n' "$LAUNCHER_PID" > "$OUT/lifecycle.status"

ready=0
blocked_states=''
for _ in $(seq 1 180); do
  if curl -fsS "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; then ready=1; break; fi
  if ! kill -0 "$LAUNCHER_PID" 2>/dev/null; then
    echo 'launcher exited before service ready' >&2
    tail -100 "$OUT/launcher.log" >&2 || true
    exit 2
  fi
  sleep 1
done
[[ "$ready" == 1 ]] || { echo 'service readiness timeout' >&2; exit 3; }
echo 'service_ready=1' >> "$OUT/lifecycle.status"

"$VENV/bin/python" "$ROOT/control/gemma4-w4a16-3090-performance-capacity/runs/g1_shared_prefix_hicache.py" \
  --action batch --fixture "$FIXTURE" --out "$OUT/c32" --count 32 \
  --prefix-tokens 63488 --total-tokens 65536 --new-tokens 32 \
  > "$OUT/c32/driver.stdout" 2> "$OUT/c32/driver.stderr"
echo 'client_requests_complete=32' >> "$OUT/lifecycle.status"

export G1_P0_SANITY_PHASE=production_on_idle
# Wait for scheduler-reported full idle and HiCache queue drain. Capture the
# metadata summary and, on violation, the complete bounded event sequence.
"$VENV/bin/python" - "$PORT" "$OUT" "$OUT/server.log" <<'PY'
import json, sys, time, urllib.request
from pathlib import Path
port, out, server_log = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
base = f"http://127.0.0.1:{port}"
def server_info():
    return json.loads(urllib.request.urlopen(base + "/server_info", timeout=5).read())
# Require the scheduler's own is_fully_idle gate (including its request queues
# and HiCache in-flight backup/load/prefetch lists) to stay true continuously.
quiet_since = None
for _ in range(1800):
    try:
        info = server_info()
    except Exception:
        time.sleep(1); continue
    states = info.get("internal_states") or []
    idle = bool(states) and all(
        state.get("g1_p0_is_fully_idle") is True
        and state.get("g1_p0_hicache_pending", {}).get("write_through") == 0
        and state.get("g1_p0_hicache_pending", {}).get("load_back") == 0
        and state.get("g1_p0_hicache_pending", {}).get("prefetch") == 0
        and state.get("g1_p0_hicache_pending", {}).get("backup") == 0
        and state.get("g1_p0_hicache_pending", {}).get("buffer_pipeline_idle") is True
        for state in states
    )
    if idle:
        quiet_since = quiet_since or time.monotonic()
        if time.monotonic() - quiet_since >= 5:
            try:
                detail = server_info()
                marker_states = detail.get("internal_states") or []
                marker_ok = bool(marker_states) and all(
                    s.get("g1_p0_is_fully_idle") is True for s in marker_states
                )
                if not marker_ok:
                    time.sleep(1)
                    continue
                detail_states = detail.get("internal_states") or []
                traces = [
                    event
                    for state in detail_states
                    for event in state.get("g1_p0_hicache_pending", {}).get("lifecycle_trace_events", [])
                ]
            except Exception:
                raise SystemExit("Could not collect scheduler quiescence details")
            out.joinpath("tree-lifecycle-events.json").write_text(
                json.dumps(traces, separators=(",", ":")) + "\n"
            )
            trace_states = [state.get("g1_p0_hicache_pending", {}) for state in detail_states]
            buffered_count = max((s.get("lifecycle_trace_count", 0) for s in trace_states), default=0)
            total_count = sum(s.get("lifecycle_trace_total", 0) for s in trace_states)
            violation = any(s.get("lifecycle_trace_violation", False) for s in trace_states)
            violation_reported = any(
                s.get("lifecycle_trace_first_violation_reported", False)
                for s in trace_states
            )
            sampled = traces if traces else []
            sampled_ops = {e.get("operation") for e in sampled}
            operations = {}
            for state in trace_states:
                for name, count in state.get("lifecycle_trace_operations", {}).items():
                    operations[name] = operations.get(name, 0) + count
            required_ops = {"split_new_prefix", "split_old_child", "backup_commit", "host_leaf_evict"}
            coverage = {name: operations.get(name, 0) > 0 for name in required_ops}
            out.joinpath("hicache_quiescent.json").write_text(json.dumps({
                "observed": True, "basis": "scheduler is_fully_idle",
                "quiet_seconds": 5,
                "tree_trace_buffered_events": buffered_count,
                "tree_trace_total_events": total_count,
                "tree_trace_operations": operations,
                "tree_trace_violation": violation,
                "tree_trace_first_violation_reported": violation_reported,
                "sampled_event_operations": sorted(sampled_ops),
                "required_path_coverage": coverage,
                "observed_at_unix": time.time()}, indent=2) + "\n")
            break
    else:
        quiet_since = None
        blocked_states = []
        for state in states:
            p = state.get("g1_p0_hicache_pending", {})
            blocked_states.append({
                "is_fully_idle": state.get("g1_p0_is_fully_idle"),
                "write_through": p.get("write_through"),
                "load_back": p.get("load_back"),
                "prefetch": p.get("prefetch"),
                "backup": p.get("backup"),
                "buffer_pipeline_idle": p.get("buffer_pipeline_idle"),
                "running": p.get("running"),
                "waiting": p.get("waiting"),
                "result_queue": p.get("result_queue"),
                "ongoing_backup": p.get("ongoing_backup"),
            })
    time.sleep(1)
else:
    out.joinpath("hicache_quiescent.json").write_text(json.dumps({
        "observed": False,
        "reason": "scheduler idle/HiCache drain not continuously confirmed within 180s",
        "blocking_scheduler_hicache_state": blocked_states,
        "observed_at_unix": time.time()}, indent=2) + "\n")
    raise SystemExit("Scheduler/HiCache quiescence not proven within 180s")
PY

echo 'scheduler_quiescence_observed=1' >> "$OUT/lifecycle.status"
# on_idle() writes the result from the real production sanity_check call.
if grep -q 'G1_P0_SANITY_CHECK_RESULT phase=production_on_idle status=PASS' "$OUT/scheduler-lifecycle.markers"; then
  echo 'sanity_check_executed=1 phase=production_on_idle result=PASS' >> "$OUT/lifecycle.status"
elif grep -q 'G1_P0_SANITY_CHECK_RESULT phase=production_on_idle status=FAIL' "$OUT/scheduler-lifecycle.markers"; then
  echo 'sanity_check_executed=1 phase=production_on_idle result=FAIL' >> "$OUT/lifecycle.status"
  exit 10
else
  echo 'sanity_check_executed=0 phase=production_on_idle result=UNKNOWN' >> "$OUT/lifecycle.status"
  echo 'Production on_idle sanity result missing.' >&2
  exit 11
fi

# Summarize the bounded lifecycle buffer captured from the scheduler endpoint.
"$VENV/bin/python" - "$OUT/tree-lifecycle-events.json" "$OUT/tree-lifecycle-summary.json" "$OUT/hicache_quiescent.json" <<'PY'
import collections, json, sys
from pathlib import Path
source, dest, quiescent = map(Path, sys.argv[1:])
events = json.loads(source.read_text()) if source.exists() else []
q = json.loads(quiescent.read_text())
summary = {
    "event_count": q.get("tree_trace_total_events", 0),
    "buffered_events": q.get("tree_trace_buffered_events", 0),
    "operation_counts": q.get("tree_trace_operations", {}),
    "has_split": q.get("tree_trace_operations", {}).get("split_new_prefix", 0) + q.get("tree_trace_operations", {}).get("split_old_child", 0) > 0,
    "has_backup_commit": q.get("tree_trace_operations", {}).get("backup_commit", 0) > 0,
    "has_host_clear": q.get("tree_trace_operations", {}).get("host_leaf_evict", 0) + q.get("tree_trace_operations", {}).get("full_component_evict", 0) > 0,
    "required_path_coverage": q.get("required_path_coverage", {}),
}
dest.write_text(json.dumps(summary, indent=2) + "\n")
print(json.dumps(summary, sort_keys=True))
PY
# Ensure the launcher (which owns its own child and monitoring cleanup) exits.
kill -TERM "$LAUNCHER_PID" 2>/dev/null || true
wait "$LAUNCHER_PID" || true
LAUNCHER_PID=''
echo 'launcher_cleanup_complete=1' >> "$OUT/lifecycle.status"
echo "$OUT"
