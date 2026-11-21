#!/usr/bin/env bash
set -Eeuo pipefail
ROOT=/home/ubuntu/workspaces/3rdparty/sglang-hicache
RUNS=$ROOT/control/gemma4-g1-hicache-tier-lifecycle-20261119/runs
PROD_RUNS=$ROOT/control/gemma4-w4a16-3090-performance-capacity/runs
VENV=/home/ubuntu/venvs/sglang-3090
OUT=${G1_TIER_OUT:?set G1_TIER_OUT}
PORT=${G1_TIER_PORT:-31401}
MAX_TOTAL_TOKENS=${G1_TIER_MAX_TOTAL_TOKENS:-139264}
HICACHE_SIZE_GB=${G1_TIER_HICACHE_SIZE_GB:-8}
G1_PROD_CONTEXT=${G1_TIER_CONTEXT:-131072}
PRESSURE_MIN_REQUESTS=${G1_TIER_PRESSURE_MIN_REQUESTS:-12}
FIXTURE_SHA256=${G1_TIER_FIXTURE_SHA256:-ac06790a415e772880dac9cb0415d09cc1bdc04142652733d1314f583f841a8b}
CAPACITY_JSON=${G1_TIER_CAPACITY_JSON:-/data/sglang-hicache/gemma4/runs/20261120T-g1-capacity-139264-hicache8-extent32-20261119T204751Z/capacity.json}
PROBE_CAPACITY=${G1_TIER_PROBE_CAPACITY:-yes}
RUN_CLIENT=${G1_TIER_RUN_CLIENT:-yes}
EXPECTED_GIT_HEAD=${G1_TIER_EXPECTED_GIT_HEAD:?set G1_TIER_EXPECTED_GIT_HEAD to the reviewed immutable commit SHA}
EXTENT_FILE_SIZE=${G1_TIER_EXTENT_FILE_SIZE:-34359738368}
[[ "$EXTENT_FILE_SIZE" == 34359738368 ]] || { echo "EXTENT_SIZE_NOT_AUTHORIZED:$EXTENT_FILE_SIZE" >&2; exit 94; }
STAGES=${G1_TIER_STAGES:-tier_probe,cold_storage_restore}
BRANCH_SEQUENCE=${G1_TIER_BRANCH_SEQUENCE:-}
REQUIRE_SOURCES=${G1_TIER_REQUIRE_SOURCES:-}
REQUIRE_BRANCHES=${G1_TIER_REQUIRE_BRANCH_EXCLUSIVE:-}
LOCK=/tmp/f1-r16b-gpu-exclusive.lock
FIXTURE=${G1_TIER_FIXTURE:?set G1_TIER_FIXTURE}
[[ ! -e "$OUT" ]] || { echo "OUTPUT_DIRECTORY_ALREADY_EXISTS:$OUT" >&2; exit 79; }
# 8 GB is the authorized acceptance configuration; 8.5 GB is authorized only for
# the targeted branch-exclusive capacity differential (does a +0.5 GB Host pool
# clear the restore_host_alloc_wait wall). Anything else is not authorized.
[[ "$MAX_TOTAL_TOKENS" == 139264 ]] || { echo "PRESSURE_CONFIG_NOT_AUTHORIZED" >&2; exit 94; }
case "$HICACHE_SIZE_GB" in 8|8.5) ;; *) echo "PRESSURE_CONFIG_NOT_AUTHORIZED" >&2; exit 94 ;; esac
[[ "$G1_PROD_CONTEXT" == 131072 ]] || { echo "CONTEXT_CONFIG_NOT_AUTHORIZED" >&2; exit 94; }
[[ -f "$FIXTURE" ]] || { echo "FIXTURE_MISSING:$FIXTURE" >&2; exit 80; }
[[ -f "$CAPACITY_JSON" ]] || { echo "CAPACITY_JSON_MISSING:$CAPACITY_JSON" >&2; exit 85; }
python3 - "$CAPACITY_JSON" "$MAX_TOTAL_TOKENS" <<'PY'
import json, sys
from pathlib import Path
path=Path(sys.argv[1]); x=json.loads(path.read_text()); expected=int(sys.argv[2])
gpu=x.get("gpu_pool_capacity_gauges", {})
host=x.get("distinct_host_pool_allocations", {})
full_values=gpu.get("sglang:max_total_num_tokens", {})
swa_values=gpu.get("sglang:max_total_num_tokens_swa", {})
if len(full_values) != 1 or len(swa_values) != 1:
    raise SystemExit("CAPACITY_DEVICE_GAUGES_NOT_UNIQUE")
full=int(next(iter(full_values.values()))); swa=int(next(iter(swa_values.values())))
if full != expected or x.get("request_count") != 0 or not x.get("host_pools_distinct_full_swa"):
    raise SystemExit("CAPACITY_CONFIGURATION_NOT_CONFIRMED")
if int(host.get("full", {}).get("tokens", 0)) <= full:
    raise SystemExit("CAPACITY_FULL_HOST_NOT_ABOVE_DEVICE")
if int(host.get("swa", {}).get("tokens", 0)) <= swa:
    raise SystemExit("CAPACITY_SWA_HOST_NOT_ABOVE_DEVICE")
PY
mkdir -p "$OUT"
[[ $(df -PB1 "$OUT" | awk 'NR==2 {print $4}') -gt 40000000000 ]] || { echo DISK_SPACE_BELOW_40GB >&2; exit 81; }
exec 9>"$LOCK"
flock -n 9 || { echo GPU_LOCK_BUSY >&2; exit 90; }
if nvidia-smi --query-compute-apps=pid --format=csv,noheader | grep -q '[0-9]'; then echo GPU_PROCESS_BUSY >&2; exit 92; fi
if ss -ltn | grep -q ":$PORT\\b"; then echo "PORT_BUSY:$PORT" >&2; exit 91; fi
actual_head=$(git -C "$ROOT" rev-parse HEAD)
[[ "$actual_head" == "$EXPECTED_GIT_HEAD" ]] || { echo "WORKTREE_HEAD_MISMATCH:$actual_head" >&2; exit 93; }
python3 - "$OUT" <<'PY'
import json, sys
from pathlib import Path
out=Path(sys.argv[1])
try:
    mem_kb={}
    for line in Path('/proc/meminfo').read_text().splitlines():
        k, rest=line.split(':',1); mem_kb[k]=int(rest.split()[0])
    if mem_kb.get('MemAvailable',0) < 8*1024*1024:
        raise SystemExit('MEMAVAILABLE_BELOW_8GIB')
except OSError as exc:
    raise SystemExit(f'MEMINFO_UNAVAILABLE:{exc}')
(out/'memory-before.json').write_text(json.dumps({'mem_available_kib':mem_kb['MemAvailable'],'threshold_kib':8*1024*1024},indent=2)+'\n')
PY
if find "$OUT/service" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null | grep -q .; then
  echo SERVICE_OUTPUT_ALREADY_EXISTS >&2
  exit 95
fi
mkdir -p "$OUT/service/l3-extent"
export G1_PROD_OUT="$OUT/service" G1_PROD_PORT="$PORT" G1_GPU_LOCK_HELD=1
export G1_PROD_KV=fp8_e5m2 G1_PROD_CONTEXT=131072 G1_PROD_MAX_RUNNING=32
export G1_PROD_MAX_TOTAL_TOKENS=$MAX_TOTAL_TOKENS G1_PROD_MEM_FRACTION=${G1_TIER_MEM_FRACTION:-.90}
export G1_PROD_HICACHE_PREFETCH_POLICY=${G1_TIER_PREFETCH_POLICY:-wait_complete}
export G1_PROD_GRAPH_BS=32 G1_PROD_RADIX=on G1_PROD_HICACHE=on G1_PROD_HICACHE_SIZE=$HICACHE_SIZE_GB
# 8.5 GB is expressed as a token ratio: 8 GB measured 186,012 Full host tokens,
# so 8.5/8 of that is 1.4192 x the 139,264-token device pool.
if [[ "$HICACHE_SIZE_GB" == 8.5 ]]; then export G1_PROD_HICACHE_RATIO=${G1_TIER_HICACHE_RATIO:-1.4192}; fi
export G1_PROD_L3_DIR="$OUT/service/l3-extent" G1_PROD_WARMUP=off G1_PROD_EXPORT_REQUEST_METRICS=on
export G1_PROD_EXTENT_SIZE=${G1_TIER_EXTENT_SIZE:-67108864}
export G1_PROD_EXTENT_FILE_SIZE=$EXTENT_FILE_SIZE
export G1_PROD_EXTENT_MAX_SIZE=$EXTENT_FILE_SIZE
export G1_PROD_EXTENT_MIN_FREE_SPACE=${G1_TIER_EXTENT_MIN_FREE_SPACE:-1073741824}
PRESSURE_FIXTURE=${G1_TIER_PRESSURE_FIXTURE:-}
if [[ -n "$PRESSURE_FIXTURE" ]]; then
  PRESSURE_SHA256=${G1_TIER_PRESSURE_FIXTURE_SHA256:-}
  [[ -n "$PRESSURE_SHA256" && -f "$PRESSURE_FIXTURE" ]] || { echo PRESSURE_FIXTURE_OR_HASH_MISSING >&2; exit 84; }
  actual_pressure_sha=$(sha256sum "$PRESSURE_FIXTURE" | awk '{print $1}')
  [[ "$actual_pressure_sha" == "$PRESSURE_SHA256" ]] || { echo PRESSURE_FIXTURE_SHA256_MISMATCH >&2; exit 84; }
fi
export SGLANG_TREE_LIFECYCLE_TRACE=1 G1_P0_EXPORT_TREE_EVENTS=1
export G1_P0_SANITY_RESULT_MARKER="$OUT/scheduler-lifecycle.markers"
export G1_P0_SANITY_PHASE=startup
printf 'worktree_head=%s\nexpected_worktree_head=%s\n' "$actual_head" "$EXPECTED_GIT_HEAD" > "$OUT/run.identity.txt"
fixture_sha=$(sha256sum "$FIXTURE" | awk '{print $1}')
[[ "$fixture_sha" == "$FIXTURE_SHA256" ]] || { echo "FIXTURE_SHA256_MISMATCH:$fixture_sha" >&2; exit 83; }
python3 "$RUNS/verify_radix_tree_fixture.py" "$FIXTURE" --expected-sha256 "$FIXTURE_SHA256" > "$OUT/fixture-verification.json"
printf 'start_epoch=%s\n' "$(date +%s)" >> "$OUT/run.identity.txt"
df -PB1 "$OUT" > "$OUT/disk-before.txt"
printf 'fixture=%s\nfixture_sha256=%s\nport=%s\nextent_gib=%s\n' "$FIXTURE" "$fixture_sha" "$PORT" "$((EXTENT_FILE_SIZE / 1073741824))" >> "$OUT/run.identity.txt"
printf 'target=max_total_tokens:%s,hicache_size_decimal_gb:%s,context:131072,output_tokens:256\n' "$MAX_TOTAL_TOKENS" "$HICACHE_SIZE_GB" >> "$OUT/run.identity.txt"
printf 'timeout_s=10800\ncompletion=12_tree_seed_plus_12_reverse_restore_decode_plus_production_idle_sanity\n' >> "$OUT/run.identity.txt"
printf 'probe_capacity_before_generation=%s\nstages=%s\n' "$PROBE_CAPACITY" "$STAGES" >> "$OUT/run.identity.txt"
if [[ -n "$PRESSURE_FIXTURE" ]]; then printf 'pressure_fixture=%s\npressure_fixture_sha256=%s\npressure_requests=%s\npressure_prompt_tokens=%s\n' "$PRESSURE_FIXTURE" "$PRESSURE_SHA256" "${G1_TIER_PRESSURE_REQUESTS:-4}" "${G1_TIER_PRESSURE_PROMPT_TOKENS:-130000}" >> "$OUT/run.identity.txt"; fi
"$PROD_RUNS/run_g1_prod_e5m2.sh" 9>&- > "$OUT/launcher.log" 2>&1 &
LAUNCHER=$!
SERVER_PID=''
MONITOR_PID=''
stop_tree() {
  local root=${1:-} sig=${2:-TERM} child
  [[ -n "$root" ]] || return 0
  while read -r child; do stop_tree "$child" "$sig"; done < <(pgrep -P "$root" 2>/dev/null || true)
  kill -s "$sig" "$root" 2>/dev/null || true
}
process_live() {
  local state
  state=$(ps -o stat= -p "$1" 2>/dev/null | awk 'NR==1 {print $1}')
  [[ -n "$state" && "$state" != Z* && "$state" != X* ]]
}
cleanup() {
  local rc=$?
  trap - EXIT TERM INT
  set +e
  if [[ -n "$SERVER_PID" ]] && process_live "$SERVER_PID"; then
    stop_tree "$SERVER_PID" TERM
    for _ in $(seq 1 60); do process_live "$SERVER_PID" || break; sleep 1; done
    process_live "$SERVER_PID" && stop_tree "$SERVER_PID" KILL
  fi
  if [[ -n "$MONITOR_PID" ]]; then kill -TERM "$MONITOR_PID" 2>/dev/null || true; wait "$MONITOR_PID" 2>/dev/null || true; fi
  if process_live "$LAUNCHER"; then
    stop_tree "$LAUNCHER" TERM
    for _ in $(seq 1 90); do process_live "$LAUNCHER" || break; sleep 1; done
    process_live "$LAUNCHER" && stop_tree "$LAUNCHER" KILL
  fi
  wait "$LAUNCHER" 2>/dev/null || true
  nvidia-smi --query-gpu=timestamp,utilization.gpu,memory.used --format=csv,noheader > "$OUT/gpu-after-wrapper.csv" 2>&1 || true
  nvidia-smi --query-compute-apps=pid,process_name --format=csv,noheader > "$OUT/gpu-processes-after.txt" 2>&1 || true
  ss -ltnp | grep ":$PORT\\b" > "$OUT/port-after-wrapper.txt" 2>&1 || true
  if [[ -s "$OUT/port-after-wrapper.txt" || -s "$OUT/gpu-processes-after.txt" ]]; then
    printf 'cleanup_leak=port_or_gpu_process\n' >> "$OUT/run.identity.txt"
    [[ $rc != 0 ]] || rc=12
  fi
  printf 'cleanup_epoch=%s\ncleanup_exit=%s\n' "$(date +%s)" "$rc" >> "$OUT/run.identity.txt"
  exit "$rc"
}
trap cleanup EXIT
trap 'exit 143' TERM
trap 'exit 130' INT
READY=0
for _ in $(seq 1 1200); do
  if curl -fsS "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; then READY=1; break; fi
  if ! kill -0 "$LAUNCHER" 2>/dev/null; then tail -100 "$OUT/launcher.log" >&2; exit 2; fi
  sleep 1
done
[[ $READY == 1 ]] || { echo SERVICE_READINESS_TIMEOUT >&2; exit 3; }
printf 'service_ready_epoch=%s\n' "$(date +%s)" >> "$OUT/run.identity.txt"
for _ in $(seq 1 30); do
  if [[ -s "$OUT/service/server.pid" ]]; then SERVER_PID=$(<"$OUT/service/server.pid"); break; fi
  server_pid=$(pgrep -f "python -m sglang.launch_server .*--port $PORT( |$)" | head -1 || true)
  if [[ -n "$server_pid" ]]; then SERVER_PID=$server_pid; break; fi
  process_live "$LAUNCHER" || { echo LAUNCHER_EXITED_BEFORE_SERVER_PID >&2; exit 4; }
  sleep 1
done
printf 'launcher_pid=%s\n' "$LAUNCHER" >> "$OUT/run.identity.txt"
[[ -n "$SERVER_PID" ]] || { echo SERVER_PID_MISSING_AFTER_HEALTH >&2; exit 4; }
kill -0 "$SERVER_PID" 2>/dev/null || { echo SERVER_PID_NOT_ALIVE >&2; exit 4; }
printf 'server_pid=%s\n' "$SERVER_PID" > "$OUT/owned-service.pid"
if [[ "$PROBE_CAPACITY" == yes ]]; then
  curl -fsS "http://127.0.0.1:$PORT/metrics" > "$OUT/capacity.metrics.txt"
  python3 - "$OUT/capacity.metrics.txt" "$OUT/service/server.log" "$MAX_TOTAL_TOKENS" "$OUT/capacity.json" <<'PY'
import json, re, sys
from pathlib import Path
metrics = Path(sys.argv[1]).read_text(errors="replace")
log = Path(sys.argv[2]).read_text(errors="replace")
expected, out = int(sys.argv[3]), Path(sys.argv[4])
def values(name):
    result = {}
    for line in metrics.splitlines():
        if line.startswith(name + "{"):
            label, _, value = line.partition(" ")
            try: result[label] = int(float(value))
            except ValueError: pass
    return result
full = values("sglang:max_total_num_tokens")
swa = values("sglang:max_total_num_tokens_swa")
pools = {}
for match in re.finditer(r"Allocating (full|swa) hierarchical KV host pool: (\d+) tokens, ([0-9.]+) GB host memory", log, re.I):
    pools[match.group(1).lower()] = {"tokens": int(match.group(2)), "host_memory_decimal_gb": float(match.group(3))}
warnings = [line for line in log.splitlines() if "host pool" in line.lower() and "smaller than" in line.lower()]
if len(full) != 1 or len(swa) != 1 or next(iter(full.values())) != expected:
    raise SystemExit("CAPACITY_DEVICE_GAUGE_MISMATCH")
if set(pools) != {"full", "swa"}:
    raise SystemExit("CAPACITY_DISTINCT_HOST_LOG_ALLOCATIONS_MISSING")
device_full, device_swa = next(iter(full.values())), next(iter(swa.values()))
if pools["full"]["tokens"] <= device_full or pools["swa"]["tokens"] <= device_swa:
    raise SystemExit("CAPACITY_HOST_NOT_ABOVE_DEVICE")
obj = {
    "schema": "gemma4.hicache.startup_capacity_probe.v1",
    "gpu_pool_capacity_gauges": {
        "sglang:max_total_num_tokens": full,
        "sglang:max_total_num_tokens_swa": swa,
    },
    "distinct_host_pool_allocations": pools,
    "host_pools_distinct_full_swa": True,
    "hicache_warnings": warnings,
    "request_count": 0,
    "claim_scope": "startup allocation only; no cache movement/restore or acceptance claims",
}
out.write_text(json.dumps(obj, indent=2) + "\\n")
print(json.dumps(obj, indent=2))
PY
  grep -i -E 'Allocating .*hierarchical KV host pool|host pool.*smaller than' "$OUT/service/server.log" > "$OUT/capacity.allocations.txt" || true
fi
if [[ "$RUN_CLIENT" != yes ]]; then
  printf 'client_skipped=1\n' >> "$OUT/run.identity.txt"
  exit 0
fi
nvidia-smi --query-gpu=timestamp,utilization.gpu,memory.used --format=csv --loop-ms=1000 > "$OUT/gpu-during.csv" 2>&1 9>&- &
MONITOR_PID=$!
CLIENT_ARGS=(
  --url "http://127.0.0.1:$PORT"
  --fixture "$FIXTURE" --out "$OUT/client" --extent-dir "$OUT/service/l3-extent"
  --server-log "$OUT/service/server.log" --timeout 1800
  --warm-output-tokens 1 --decode-output-tokens 256 --parallel "${G1_TIER_PARALLEL:-8}"
  --min-requests "$PRESSURE_MIN_REQUESTS"
  --capacity-json "$CAPACITY_JSON"
  --context "$G1_PROD_CONTEXT" --require-capacity --frontier-count "${G1_TIER_FRONTIER_COUNT:-0}" --stages "$STAGES"
)
if [[ -n "${G1_PROD_ADMIN_API_KEY:-}" ]]; then CLIENT_ARGS+=(--admin-api-key "$G1_PROD_ADMIN_API_KEY"); fi
if [[ -n "$PRESSURE_FIXTURE" ]]; then
  CLIENT_ARGS+=(--pressure-fixture "$PRESSURE_FIXTURE" --pressure-requests "${G1_TIER_PRESSURE_REQUESTS:-4}" --pressure-prompt-tokens "${G1_TIER_PRESSURE_PROMPT_TOKENS:-130000}" --pressure-preserve-prefix --pressure-watermark-timeout "${G1_TIER_PRESSURE_WATERMARK_TIMEOUT:-180}" --pressure-max-prompt-tokens "${G1_TIER_PRESSURE_MAX_PROMPT_TOKENS:-130000}" --pressure-min-device-evictions "${G1_TIER_PRESSURE_MIN_DEVICE_EVICTIONS:-1}" --pressure-min-storage-bytes "${G1_TIER_PRESSURE_MIN_STORAGE_BYTES:-1}")
fi
if [[ -n "$BRANCH_SEQUENCE" ]]; then CLIENT_ARGS+=(--branch-sequence "$BRANCH_SEQUENCE"); fi
if [[ -n "${G1_TIER_BRANCH_IDLE_TIMEOUT:-}" ]]; then CLIENT_ARGS+=(--branch-idle-timeout "$G1_TIER_BRANCH_IDLE_TIMEOUT"); fi
if [[ -n "${G1_TIER_BRANCH_CHURN_PASSES:-}" ]]; then CLIENT_ARGS+=(--branch-churn-passes "$G1_TIER_BRANCH_CHURN_PASSES"); fi
if [[ -n "$REQUIRE_SOURCES" ]]; then CLIENT_ARGS+=(--require-sources "$REQUIRE_SOURCES"); fi
if [[ -n "$REQUIRE_BRANCHES" ]]; then CLIENT_ARGS+=(--require-branch-exclusive "$REQUIRE_BRANCHES"); fi
if [[ -n "${G1_TIER_REQUIRE_SOURCE:-}" ]]; then CLIENT_ARGS+=(--require-source "$G1_TIER_REQUIRE_SOURCE"); fi
if [[ "${G1_TIER_REQUIRE_FRONTIER_RECOVERY:-}" == yes ]]; then CLIENT_ARGS+=(--require-frontier-recovery); fi
if [[ "${G1_TIER_FRONTIER_FROM_PRESSURE:-}" == yes ]]; then CLIENT_ARGS+=(--frontier-from-pressure); fi
# NOTE: the radix-split/quiescent artifacts (tree-lifecycle-events.json and
# hicache_quiescent.json) are exported by THIS wrapper after the client returns,
# so the client cannot require them on a fresh output directory. The same
# validation runs below in the post-client gate, which is the authoritative
# check; asking the client for them only produced a harness-ordering failure
# (RADIX_TRACE_ARTIFACT_MISSING) after every phase had already succeeded.
if [[ "${G1_TIER_L2_ONLY_PROBE:-}" == yes ]]; then
  CLIENT_ARGS+=(
    --l2-only-storage-backend extent
    --l2-only-idle-timeout "${G1_TIER_L2_ONLY_IDLE_TIMEOUT:-600}"
    --l2-only-churn-passes "${G1_TIER_L2_ONLY_CHURN_PASSES:-1}"
  )
  if [[ -n "${G1_TIER_L2_ONLY_STORAGE_PREFETCH_POLICY:-}" ]]; then
    CLIENT_ARGS+=(--l2-only-storage-prefetch-policy "$G1_TIER_L2_ONLY_STORAGE_PREFETCH_POLICY")
  fi
  if [[ -n "${G1_TIER_L2_ONLY_STORAGE_WRITE_POLICY:-}" ]]; then
    CLIENT_ARGS+=(--l2-only-storage-write-policy "$G1_TIER_L2_ONLY_STORAGE_WRITE_POLICY")
  fi
  if [[ -n "${G1_TIER_L2_ONLY_STORAGE_EXTRA_CONFIG:-}" ]]; then
    CLIENT_ARGS+=(--l2-only-storage-extra-config "$G1_TIER_L2_ONLY_STORAGE_EXTRA_CONFIG")
  fi
fi
timeout --signal=TERM --kill-after=60 9000 \
  "$VENV/bin/python" "$RUNS/run_radix_tree_lifecycle.py" "${CLIENT_ARGS[@]}" \
  > "$OUT/client.stdout" 2> "$OUT/client.stderr" || CLIENT_RC=$?
CLIENT_RC=${CLIENT_RC:-0}
export G1_P0_SANITY_PHASE=production_on_idle
printf 'client_complete_epoch=%s\nclient_exit=%s\n' "$(date +%s)" "$CLIENT_RC" >> "$OUT/run.identity.txt"
if [[ "$CLIENT_RC" != 0 ]]; then
  tail -100 "$OUT/client.stderr" >&2 || true
  tail -80 "$OUT/client.stdout" >&2 || true
  exit "$CLIENT_RC"
fi
# Confirm 5 seconds of full scheduler+HiCache idle; sanity_check remains active.
"$VENV/bin/python" - "$PORT" "$OUT" <<'PY'
import json, sys, time, urllib.request
from pathlib import Path
port, out = int(sys.argv[1]), Path(sys.argv[2])
url = f"http://127.0.0.1:{port}"
end = time.monotonic() + 240
quiet_since = None
last = None
while time.monotonic() < end:
    with urllib.request.urlopen(url + "/server_info", timeout=10) as r:
        info = json.load(r)
    states = info.get("internal_states", [])
    last = [s.get("g1_p0_hicache_pending", {}) for s in states]
    idle = bool(states) and all(
        s.get("g1_p0_is_fully_idle") is True
        and all(p.get(k, 0) == 0 for k in ("running", "waiting", "result_queue", "write_through", "load_back", "prefetch", "backup", "ongoing_backup"))
        and p.get("buffer_pipeline_idle") is True
        for s, p in zip(states, last)
    )
    if idle:
        quiet_since = quiet_since or time.monotonic()
        if time.monotonic() - quiet_since >= 5:
            events = [
                event
                for state in states
                for event in state.get("g1_p0_hicache_pending", {}).get("lifecycle_trace_events", [])
            ]
            trace_state = [state.get("g1_p0_hicache_pending", {}) for state in states]
            operations = {}
            for item in trace_state:
                for name, count in item.get("lifecycle_trace_operations", {}).items():
                    operations[name] = operations.get(name, 0) + count
            (out / "tree-lifecycle-events.json").write_text(json.dumps(events, indent=2) + "\n")
            (out / "hicache_quiescent.json").write_text(json.dumps({
                "observed": True,
                "quiet_seconds": 5,
                "tree_trace_total_events": sum(item.get("lifecycle_trace_total", 0) for item in trace_state),
                "tree_trace_operations": operations,
                "tree_trace_violation": any(item.get("lifecycle_trace_violation", False) for item in trace_state),
                "state": trace_state,
                "epoch_s": time.time(),
            }, indent=2) + "\n")
            (out / "idle.json").write_text(json.dumps({"observed": True, "quiet_seconds": 5, "state": last, "epoch_s": time.time()}, indent=2) + "\n")
            break
    else:
        quiet_since = None
    time.sleep(1)
else:
    (out / "idle.json").write_text(json.dumps({"observed": False, "blocking_state": last, "epoch_s": time.time()}, indent=2) + "\n")
    raise SystemExit("FULL_IDLE_TIMEOUT")
PY
if [[ "$CLIENT_RC" == 0 ]] && grep -q 'G1_P0_SANITY_CHECK_RESULT phase=production_on_idle status=PASS' "$OUT/scheduler-lifecycle.markers"; then
  grep -E 'Decode batch|Prefill batch' "$OUT/service/server.log" > "$OUT/observed-gpu-batches.log" || true
  "$VENV/bin/python" - "$OUT/observed-gpu-batches.log" "$OUT/gpu-batch-summary.json" "$OUT/client/lifecycle.json" <<'PY'
import json, re, sys
from pathlib import Path
lines=Path(sys.argv[1]).read_text(errors="replace").splitlines()
decode=[]
# This branch logs "Decode batch, #running-req: N, #full token: M"; some
# revisions log "#new-seq/#new-token" instead. Accept either, and record which
# field was used so the batch-size claim stays traceable.
for line in lines:
    match=re.search(r"Decode batch, #new-seq: (\d+), #new-token: (\d+)", line)
    if match:
        decode.append({"new_sequences":int(match.group(1)),"new_tokens":int(match.group(2)),
                       "field":"#new-seq","line":line})
        continue
    match=re.search(r"Decode batch, #running-req: (\d+), #full token: (\d+)", line)
    if match:
        decode.append({"new_sequences":int(match.group(1)),"new_tokens":int(match.group(2)),
                       "field":"#running-req","line":line})
records={}
summary=Path(sys.argv[3])
if summary.exists():
    result=json.loads(summary.read_text())
    for phase in ("tier_probe", "cold_storage_restore", "frontier_recovery"):
        for rid in result.get(phase, {}).get("request_ids", []):
            records[rid]=phase
Path(sys.argv[2]).write_text(json.dumps({"decode_batches":decode,"observed_sizes":sorted({x["new_sequences"] for x in decode}),"batch_field":sorted({x["field"] for x in decode}),"basis":"scheduler Decode batch log lines","rid_phase_map":records},indent=2)+"\n")
if not decode:
    raise SystemExit("SCHEDULER_DECODE_BATCH_EVIDENCE_MISSING")
PY
  if [[ -s "$OUT/client/lifecycle.json" ]]; then
    "$VENV/bin/python" - "$OUT/client/lifecycle.json" <<'PY'
import json, sys
from pathlib import Path
result=json.loads(Path(sys.argv[1]).read_text())
for phase in ("seed", "tier_probe", "cold_storage_restore"):
    item=result.get(phase, {})
    if item.get("count", 0) == 0 or item.get("success") != item.get("count"):
        raise SystemExit(f"PHASE_DECODE_INCOMPLETE:{phase}:{item}")
PY
  fi
  "$VENV/bin/python" - "$RUNS/run_radix_tree_lifecycle.py" "$OUT/tree-lifecycle-events.json" "$OUT/hicache_quiescent.json" <<'PY'
import importlib.util, json, sys
from pathlib import Path
module_path, events_path, quiet_path = map(Path, sys.argv[1:])
spec = importlib.util.spec_from_file_location("g1_lifecycle", module_path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
events = json.loads(events_path.read_text())
quiet = json.loads(quiet_path.read_text())
ops = quiet.get("tree_trace_operations", {})
if not quiet.get("observed") or quiet.get("tree_trace_violation"):
    raise SystemExit("RADIX_QUIESCENT_TRACE_INVALID")
# /server_info only attaches the raw event list when a violation was recorded
# (`lifecycle_trace_events` is [] on a clean run), so the event dump cannot be
# required here: a clean run is exactly the outcome we want. Validate the dump
# when it exists, and in every case require the operation counters to show the
# split actually happened.
if events:
    module.validate_radix_events(events)
elif int(quiet.get("tree_trace_total_events", 0)) < 1:
    raise SystemExit("RADIX_QUIESCENT_TRACE_EMPTY")
if ops.get("split_new_prefix", 0) < 1 or ops.get("split_old_child", 0) < 1:
    raise SystemExit("RADIX_QUIESCENT_SPLIT_NOT_CONFIRMED")
print("RADIX_GATE=PASS events=%d total=%s ops=%s" % (len(events), quiet.get("tree_trace_total_events"), {k: ops.get(k) for k in ("split_new_prefix", "split_old_child", "split_old_parent", "backup_commit")}))
PY
  printf 'production_idle_sanity=PASS\n' >> "$OUT/run.identity.txt"
else
  printf 'production_idle_sanity=UNKNOWN_OR_FAIL\n' >> "$OUT/run.identity.txt"
  exit 11
fi
printf 'acceptance_phase_complete=1\n' >> "$OUT/run.identity.txt"
exit "$CLIENT_RC"
