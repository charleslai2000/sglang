#!/usr/bin/env bash
# T007 bounded profiling window inside a full original C-8 run.
# Reuses T006's exact launch argv and the official bench_multiturn workload.
# Collection is limited to one steady-state window via the existing nsys
# launch/start/stop session interface; no new instrumentation is added to SGLang.
set -Eeuo pipefail
ROOT=/home/ubuntu/workspaces/3rdparty/sglang-hicache
VENV=/home/ubuntu/venvs/sglang-3090
DATA=/data/sglang-hicache/gemma4
MODEL=$DATA/model
AOT=/data/sglang-hicache/g2-quasar-runs/20261110T-g2-postrope-e5m2-quality/aot-sm86-package
OVERLAY=$ROOT/control/gemma4-w4a16-3090-performance-capacity/runs/overlay
RUNS=$ROOT/control/gemma4-w4a16-3090-performance-capacity/runs
T006=/data/sglang-hicache/gemma4/runs/20261124T-g5-live-capacity-65536/c8-800-r2
OUT=${T007_OUT:?set T007_OUT}
PORT=31401
LOCK=/tmp/f1-r16b-gpu-exclusive.lock
NSYS=/usr/local/bin/nsys
SESSION=${T007_SESSION:-t007c8-$(date -u +%H%M%S)-$$}
WINDOW_DELAY=${T007_WINDOW_DELAY:-150}
WINDOW_SECONDS=${T007_WINDOW_SECONDS:-120}
CHUNK_OVERRIDE=${T007_CHUNK:-}
HICACHE_MODE=${T007_HICACHE_MODE:-on}
WRITE_POLICY=${T007_WRITE_POLICY:-}
PREFETCH_POLICY=${T007_PREFETCH_POLICY:-}
EXTENT_OUT=${T007_EXTENT_OUT:-$OUT/l3-extent}
[[ $HICACHE_MODE == on || $HICACHE_MODE == l2 || $HICACHE_MODE == off ]] || { echo "invalid T007_HICACHE_MODE=$HICACHE_MODE" >&2; exit 2; }
[[ -z $WRITE_POLICY || $WRITE_POLICY == write_through || $WRITE_POLICY == write_back || $WRITE_POLICY == write_through_selective ]] || { echo "invalid T007_WRITE_POLICY=$WRITE_POLICY" >&2; exit 2; }
[[ -z $PREFETCH_POLICY || $PREFETCH_POLICY == wait_complete || $PREFETCH_POLICY == best_effort || $PREFETCH_POLICY == timeout ]] || { echo "invalid T007_PREFETCH_POLICY=$PREFETCH_POLICY" >&2; exit 2; }

[[ -d "$OUT" ]] || { echo "T007_OUT must exist with its run intent: $OUT" >&2; exit 2; }
mapfile -t OUT_CONTENTS < <(find "$OUT" -mindepth 1 -maxdepth 1 -printf '%f\n')
[[ ${#OUT_CONTENTS[@]} == 1 && ${OUT_CONTENTS[0]} == intent.txt ]] || {
  echo "T007_OUT must contain only intent.txt before launch: $OUT" >&2
  exit 2
}
exec 9>"$LOCK"
flock -n 9 || { echo GPU_LOCK_BUSY | tee "$OUT/preflight.txt"; exit 90; }
[[ $(sha256sum "$MODEL/model.safetensors"|awk '{print $1}') == 19d89d2a4b3e401a3eae75ec08ab112810421a036c91d8c8226b686be7fe0c5d ]]
ss -ltn|grep -q ":$PORT\\b" && { echo PORT_BUSY | tee "$OUT/preflight.txt"; exit 91; } || true
nvidia-smi --query-compute-apps=pid --format=csv,noheader | grep -q '[0-9]' && { echo GPU_PROCESS_BUSY | tee "$OUT/preflight.txt"; exit 92; } || true
printf 'lock=acquired port=%s gpu_free checked=%s\n' "$PORT" "$(date -Is)" > "$OUT/preflight.txt"
df -h "$DATA" > "$OUT/disk-before.txt"; free -h > "$OUT/ram-before.txt"
git -C "$ROOT" rev-parse HEAD > "$OUT/source-head.txt"
git -C "$ROOT" status --porcelain > "$OUT/source-status.txt"

export PYTHONNOUSERSITE=1 SGLANG_GEMMA4_SWA_POOL_TOKENS=65536 \
  PYTHONPATH="$RUNS:$AOT:$ROOT/python:$VENV/lib/python3.12/site-packages:$ROOT/python/sglang/kernels/aot/python:$OVERLAY" \
  LD_LIBRARY_PATH="$VENV/lib/python3.12/site-packages/torch/lib:/usr/local/cuda-12.9/lib64" \
  SGLANG_CACHE_DIR="$DATA/cache" HF_HOME="$DATA/cache/hf-home" HF_DATASETS_CACHE="$DATA/cache/datasets" \
  SGLANG_ENABLE_METRICS_DEVICE_TIMER=1 SGLANG_ENABLE_NVTX_SCHEDULER=1
# Bind the run to the actual imported service modules (not just git metadata).
"$VENV/bin/python" - "$ROOT" "$OUT/source-identity.json" <<'PY'
import hashlib, importlib, json, os, subprocess, sys
root=os.path.realpath(sys.argv[1]); mods=("sglang","sglang.launch_server","sglang.srt.managers.scheduler","sglang.srt.managers.schedule_policy","sglang.srt.managers.scheduler_components.metrics_reporter","sglang.srt.utils.device_timer","sglang.srt.mem_cache.unified_radix_cache")
loaded={}
for n in mods:
    m=importlib.import_module(n); p=os.path.realpath(m.__file__)
    if not (p==root or p.startswith(root+os.sep)): raise SystemExit(f"outside worktree: {n}={p}")
    loaded[n]={"path":p,"sha256":hashlib.sha256(open(p,"rb").read()).hexdigest()}
ident={"project_root":root,"git_head":subprocess.check_output(["git","-C",root,"rev-parse","HEAD"],text=True).strip(),
 "branch":subprocess.check_output(["git","-C",root,"branch","--show-current"],text=True).strip(),
 "python":os.path.realpath(sys.executable),"pythonpath":os.environ.get("PYTHONPATH",""),"modules":loaded}
json.dump(ident,open(sys.argv[2],"w"),indent=2); print(json.dumps({k:ident[k] for k in ("git_head","python")},sort_keys=True))
PY

# Reuse T006's exact recorded argv, overriding only metrics/artifact paths and
# (for the L1+L2 diagnostic) removing the L3 storage backend.
eval "ARGS=($(cat "$T006/launch-argv.txt"))"
NEW=(); skip=0
for ((i=0;i<${#ARGS[@]};i++)); do
  if [[ $skip == 1 ]]; then skip=0; continue; fi
  if [[ $HICACHE_MODE == off ]]; then
    case ${ARGS[i]} in
      --enable-hierarchical-cache) continue ;;
      --hicache-size|--hicache-write-policy|--hicache-io-backend|--hicache-mem-layout|--hicache-host-memory-mode|--hicache-storage-backend|--hicache-storage-backend-extra-config|--hicache-storage-prefetch-policy) skip=1; continue ;;
    esac
  elif [[ $HICACHE_MODE == l2 ]]; then
    case ${ARGS[i]} in
      --hicache-storage-backend) skip=1; continue ;;
      --hicache-storage-backend-extra-config|--hicache-storage-prefetch-policy) skip=1; continue ;;
    esac
  fi
  if [[ ${ARGS[i]} == --export-metrics-to-file-dir ]]; then NEW+=("${ARGS[i]}" "$OUT/request-metrics"); skip=1; continue; fi
  if [[ -n $WRITE_POLICY && ${ARGS[i]} == --hicache-write-policy ]]; then
    NEW+=("${ARGS[i]}" "$WRITE_POLICY"); skip=1; continue
  fi
  if [[ -n $PREFETCH_POLICY && ${ARGS[i]} == --hicache-storage-prefetch-policy ]]; then
    NEW+=("${ARGS[i]}" "$PREFETCH_POLICY"); skip=1; continue
  fi
  NEW+=("${ARGS[i]}")
done
ARGS=("${NEW[@]}")
if [[ -n "$CHUNK_OVERRIDE" ]]; then
  NEW2=(); had=0
  for ((i=0;i<${#ARGS[@]};i++)); do
    if [[ $had == 1 ]]; then had=0; continue; fi
    if [[ ${ARGS[i]} == --chunked-prefill-size ]]; then NEW2+=("${ARGS[i]}" "$CHUNK_OVERRIDE"); had=1; continue; fi
    NEW2+=("${ARGS[i]}")
  done
  if [[ $had == 0 && ! " ${ARGS[*]} " =~ \ --chunked-prefill-size\  ]]; then NEW2+=(--chunked-prefill-size "$CHUNK_OVERRIDE"); fi
  ARGS=("${NEW2[@]}")
fi
# Fresh L3 extent dir per run: never replay a previous run's WAL.
NEW3=(); had=0
for ((i=0;i<${#ARGS[@]};i++)); do
  if [[ $had == 1 ]]; then had=0; continue; fi
  if [[ $HICACHE_MODE == l2 && ${ARGS[i]} == --hicache-storage-backend-extra-config ]]; then had=1; continue; fi
  if [[ $HICACHE_MODE == l2 && ${ARGS[i]} == --hicache-storage-prefetch-policy ]]; then had=1; continue; fi
  if [[ ${ARGS[i]} == --hicache-storage-backend-extra-config ]]; then
    NEW3+=("${ARGS[i]}")
    had=2
    continue
  fi
  if [[ $had == 2 ]]; then
    had=0
    NEW3+=("$(python3 -c 'import json,sys; c=json.loads(sys.argv[1]); c["storage_dir"]=sys.argv[2]; print(json.dumps(c))' "${ARGS[i]}" "$EXTENT_OUT")")
    continue
  fi
  NEW3+=("${ARGS[i]}")
done
ARGS=("${NEW3[@]}")
mkdir -p "$OUT/request-metrics"
printf '%q ' "${ARGS[@]}" > "$OUT/launch-argv.txt"; printf '\nchunked_prefill_size_override=%s\nhicache_mode=%s\nwrite_policy_override=%s\nprefetch_policy_override=%s\nwindow_delay_s=%s\nwindow_seconds=%s\n' "${CHUNK_OVERRIDE:-default}" "$HICACHE_MODE" "${WRITE_POLICY:-from-baseline}" "${PREFETCH_POLICY:-from-baseline}" "$WINDOW_DELAY" "$WINDOW_SECONDS" > "$OUT/manifest.txt"
printf 'task_started=%s\nwrapper_pid=%s\nwrapper_command=%q\nextent_dir=%s\n' "$(date -u +%FT%TZ)" "$$" "$0" "$EXTENT_OUT" >> "$OUT/manifest.txt"
printf 'SGLANG_ENABLE_METRICS_DEVICE_TIMER=1\nSGLANG_ENABLE_NVTX_SCHEDULER=1\n' >> "$OUT/manifest.txt"
printf 'git_head=%s\n' "$(git -C "$ROOT" rev-parse HEAD)" >> "$OUT/manifest.txt"

NSYS_PID= SAMPLER= GPU_MON= BENCH_PID= SERVER_TREE=
stop_tree(){ local r=${1:-} s=${2:-TERM} c; [[ -n "$r" ]] || return 0; while read -r c; do stop_tree "$c" "$s"; done < <(pgrep -P "$r" 2>/dev/null || true); kill -s "$s" "$r" 2>/dev/null || true; }
cleanup(){
  local rc=$?
  trap - EXIT TERM INT
  set +e
  [[ -z $BENCH_PID ]] || { kill -TERM "$BENCH_PID" 2>/dev/null; wait "$BENCH_PID" 2>/dev/null; }
  [[ -z $SAMPLER ]] || { kill -TERM "$SAMPLER" 2>/dev/null; wait "$SAMPLER" 2>/dev/null; }
  [[ -z $GPU_MON ]] || { kill -TERM "$GPU_MON" 2>/dev/null; wait "$GPU_MON" 2>/dev/null; }
  curl -fsS --max-time 5 "http://127.0.0.1:$PORT/metrics" > "$OUT/metrics-at-stop.prom" 2>"$OUT/metrics-at-stop.err"
  "$NSYS" stop --session="$SESSION" > "$OUT/nsys-stop-on-cleanup.log" 2>&1
  [[ -z $NSYS_PID ]] || stop_tree "$NSYS_PID" TERM
  # nsys launch may detach, so stop the actual service tree by argv as well.
  pkill -TERM -f "sglang.launch_server .*--port $PORT" 2>/dev/null
  for _ in $(seq 1 60); do pgrep -f "sglang.launch_server .*--port $PORT" >/dev/null || break; sleep 1; done
  pkill -KILL -f "sglang.launch_server .*--port $PORT" 2>/dev/null
  [[ -z $NSYS_PID ]] || kill -KILL "$NSYS_PID" 2>/dev/null
  pkill -KILL -f "start-agent --session-name $SESSION" 2>/dev/null
  "$NSYS" shutdown > "$OUT/nsys-shutdown.log" 2>&1
  nvidia-smi --query-gpu=timestamp,utilization.gpu,memory.used,memory.total --format=csv > "$OUT/gpu-after.csv" 2>&1
  ss -ltnp | grep ":$PORT\\b" > "$OUT/port-after.txt" 2>&1 || true
  free -h > "$OUT/ram-after.txt"
  printf 'wrapper_exit=%s ended=%s\n' "$rc" "$(date -u +%FT%TZ)" > "$OUT/exit.txt"
  exit "$rc"
}
trap cleanup EXIT
trap 'exit 143' TERM
trap 'exit 130' INT

# T007_NSYS_EXTRA carries extra launch-time options (word-split on purpose):
# e.g. "--cudabacktrace=sync:100 --python-backtrace=cuda --python-sampling=true" for sync attribution.
NSYS_EXTRA=${T007_NSYS_EXTRA:-}
NSYS_START_EXTRA=${T007_NSYS_START_EXTRA:-}
# shellcheck disable=SC2086
"$NSYS" launch --session-new="$SESSION" --trace=cuda,nvtx --cuda-graph-trace=node --cuda-event-trace=false --wait=all $NSYS_EXTRA \
  "$VENV/bin/python" -u -m sglang.launch_server "${ARGS[@]}" > "$OUT/server.log" 2>&1 &
NSYS_PID=$!
echo "$NSYS_PID" > "$OUT/nsys-launch.pid"

ready=0
for _ in $(seq 1 1200); do
  if curl -fsS --max-time 2 "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; then ready=1; break; fi
  kill -0 "$NSYS_PID" 2>/dev/null || { tail -100 "$OUT/server.log"; exit 2; }
  sleep 1
done
[[ $ready == 1 ]]
curl -fsS --max-time 20 "http://127.0.0.1:$PORT/metrics" > "$OUT/metrics-at-start.prom"
curl -fsS --max-time 20 "http://127.0.0.1:$PORT/model_info" > "$OUT/model-info.json"
nvidia-smi --query-gpu=timestamp,utilization.gpu,memory.used,memory.total --format=csv > "$OUT/gpu-ready.csv"
# Prove the opt-in reached the scheduler worker, not just the launcher shell.
ps -eo pid,ppid,args > "$OUT/processes.txt"
SCHED_PID=$(pgrep -f "sglang.launch_server .*--port $PORT" | head -1 || true)
[[ -n "$SCHED_PID" ]] && tr '\0' '\n' < "/proc/$SCHED_PID/environ" | grep -E '^SGLANG_ENABLE_(METRICS_DEVICE_TIMER|NVTX_SCHEDULER)=' > "$OUT/worker-env.txt" || true
grep -E '^(sglang:)?forward_execution_seconds_total|sglang:fwd_occupancy' "$OUT/metrics-at-start.prom" > "$OUT/timer-at-start.txt" || true

"$VENV/bin/python" /tmp/g1_metrics_sampler.py --url "http://127.0.0.1:$PORT/metrics" --out "$OUT/pool-series.jsonl" --interval 2 --seconds 3600 & SAMPLER=$!
nvidia-smi --query-gpu=timestamp,utilization.gpu,memory.used,memory.total --format=csv --loop-ms=1000 > "$OUT/gpu-samples.csv" & GPU_MON=$!

BENCH_PP="$RUNS:$AOT:$ROOT/python:$VENV/lib/python3.12/site-packages:$ROOT/python/sglang/kernels/aot/python:$OVERLAY"
BENCH_ARGS=(--num-clients 40 --num-rounds 20 --request-length 1024 --output-length 256 --distribution poisson --request-rate 8 --seed 42 --max-parallel 64 --disable-auto-run --fixed-history-tokens --host 127.0.0.1 --port "$PORT" --model-path "$MODEL" --dataset-path /data/sglang-hicache/datasets/ShareGPT_V3_unfiltered_cleaned_split.json --log-file "$OUT/perf.jsonl" --tag T007-profile --request-hash-log "$OUT/hashes.jsonl")
( cd "$ROOT" && PYTHONPATH="$BENCH_PP" exec timeout -k 60 7200 "$VENV/bin/python" benchmark/hicache/bench_multiturn.py "${BENCH_ARGS[@]}" ) > "$OUT/bench.log" 2>&1 &
BENCH_PID=$!
BENCH_START=$(date +%s)
BENCH_START_UTC=$(date -u +%FT%TZ)

# Bounded, same-run profiling window in the steady-state part of the workload.
# A zero window disables capture (used only for an unprofiled full acceptance).
if [[ $WINDOW_SECONDS != 0 ]]; then
sleep "$WINDOW_DELAY"
# launch already fixed the trace options; start must not repeat them.
# shellcheck disable=SC2086
"$NSYS" start --session="$SESSION" -o "$OUT/t007-c8-window" $NSYS_START_EXTRA > "$OUT/nsys-start.log" 2>&1 || printf 'NSYS_START_FAILED rc=%s\n' "$?" >> "$OUT/nsys-start.log"
echo "window_start=$(date -Is) window_start_epoch=$(date +%s) bench_elapsed_s=$(( $(date +%s) - BENCH_START ))" > "$OUT/window.txt"
sleep "$WINDOW_SECONDS"
"$NSYS" stop --session="$SESSION" > "$OUT/nsys-stop.log" 2>&1 || true
echo "window_end=$(date -Is) window_end_epoch=$(date +%s) bench_elapsed_s=$(( $(date +%s) - BENCH_START ))" >> "$OUT/window.txt"
fi

if wait "$BENCH_PID"; then BENCH_RC=0; else BENCH_RC=$?; fi
BENCH_PID=
BENCH_END=$(date +%s)
printf 'bench_exit=%s finished=%s\n' "$BENCH_RC" "$(date -u +%FT%TZ)" > "$OUT/bench-exit.txt"
printf 'client_wall_seconds=%s start_utc=%s end_utc=%s\n' \
  "$(( BENCH_END - BENCH_START ))" "$BENCH_START_UTC" "$(date -u +%FT%TZ)" > "$OUT/client-wall.txt"
curl -fsS --max-time 5 "http://127.0.0.1:$PORT/metrics" > "$OUT/metrics-at-end.prom" 2>"$OUT/metrics-at-end.err" || true
grep -E 'forward_execution_seconds_total|sglang:fwd_occupancy' "$OUT/metrics-at-end.prom" > "$OUT/timer-at-end.txt" || true
# Official summary: the benchmark's own aggregate plus what this wrapper
# observed. A profiled run is labelled so its TPS is never read as the
# unprofiled acceptance number, and an aborted run is labelled incomplete.
"$VENV/bin/python" - "$OUT" "$BENCH_RC" "$(( BENCH_END - BENCH_START ))" "$WINDOW_SECONDS" <<'SUMPY'
import json, os, sys
out, bench_rc, client_wall, window_seconds = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
summary = {}
try:
    with open(os.path.join(out, "perf.jsonl")) as fh:
        for line in fh:
            line = line.strip()
            if line:
                record = json.loads(line)
                if "summary" in record:
                    summary = record["summary"]
                break
except FileNotFoundError:
    pass


def counters(path, name):
    values = {}
    try:
        with open(path) as fh:
            for line in fh:
                if line.startswith(name):
                    labels = line.split("{", 1)[1].split("}", 1)[0] if "{" in line else ""
                    # The engine exports extra labels (engine_type, model_name);
                    # key the series by category only so lookups below match.
                    category = None
                    for part in labels.split(","):
                        key, _, value = part.partition("=")
                        if key == "category":
                            category = value.strip('"')
                    values[category if category is not None else labels] = float(
                        line.rsplit(" ", 1)[1]
                    )
    except FileNotFoundError:
        pass
    return values


start = counters(os.path.join(out, "metrics-at-start.prom"), "sglang:forward_execution_seconds_total")
end = counters(os.path.join(out, "metrics-at-end.prom"), "sglang:forward_execution_seconds_total")


def delta(category):
    left, right = start.get(category), end.get(category)
    return None if left is None or right is None else right - left


decode_s, extend_s = delta("decode"), delta("extend")
bench_s = summary.get("duration_seconds")
# Two duty bases: the benchmark's own window (acceptance-facing) and the
# wrapper's client wall clock (includes ramp-up and teardown).
duty = (
    100.0 * (decode_s + extend_s) / bench_s
    if None not in (decode_s, extend_s) and bench_s
    else None
)
duty_client_wall = (
    100.0 * (decode_s + extend_s) / client_wall
    if None not in (decode_s, extend_s) and client_wall
    else None
)
window_elapsed = None
try:
    with open(os.path.join(out, "window.txt")) as fh:
        stamps = {}
        for line in fh:
            for token in line.split():
                if "=" in token:
                    key, value = token.split("=", 1)
                    stamps[key] = value
        if stamps.get("window_start_epoch") and stamps.get("window_end_epoch"):
            window_elapsed = float(stamps["window_end_epoch"]) - float(stamps["window_start_epoch"])
except FileNotFoundError:
    pass
completed, total = summary.get("completed_requests"), summary.get("total_requests")
result = {
    "profiled": window_seconds > 0,
    "profile_window_seconds": window_seconds or 0,
    "profile_window_elapsed_s": window_elapsed,
    "official_output_token_throughput": summary.get("output_token_throughput"),
    "official_input_token_throughput": summary.get("input_token_throughput"),
    "official_request_throughput": summary.get("throughput"),
    "bench_duration_seconds": summary.get("duration_seconds"),
    "client_wall_seconds": client_wall,
    "total_requests": total,
    "completed_requests": completed,
    "failed_requests": summary.get("failed_requests"),
    "cache_hit_rate": summary.get("cache_hit_rate"),
    "average_latency_s": summary.get("average_latency"),
    "average_ttft_s": summary.get("average_ttft"),
    "average_itl_s": summary.get("average_itl"),
    "decode_forward_seconds": decode_s,
    "extend_forward_seconds": extend_s,
    "forward_duty_pct_vs_bench_window": duty,
    "forward_duty_pct_vs_client_wall": duty_client_wall,
    "bench_exit": bench_rc,
    "bench_complete": bool(total is not None and completed == total and not summary.get("failed_requests")),
}
try:
    result["git_head"] = open(os.path.join(out, "source-head.txt")).read().strip()
except FileNotFoundError:
    pass
with open(os.path.join(out, "official-summary.json"), "w") as fh:
    json.dump(result, fh, indent=2, sort_keys=True, default=str)
tps = result["official_output_token_throughput"]
line = "official_tps=%s duty_pct=%s duty_clientwall_pct=%s bench_s=%s client_wall_s=%s completed=%s/%s failed=%s profiled=%s head=%s" % (
    None if tps is None else round(tps, 2),
    None if duty is None else round(duty, 2),
    None if duty_client_wall is None else round(duty_client_wall, 2),
    None if bench_s is None else round(bench_s, 2),
    client_wall, completed, total, result["failed_requests"], result["profiled"],
    str(result.get("git_head", ""))[:10])
open(os.path.join(out, "official-summary.txt"), "w").write(line + "\n")
print(line)
if not result["bench_complete"]:
    print("BENCH_INCOMPLETE: official TPS is not an acceptance number")
    sys.exit(3)
SUMPY
[[ $BENCH_RC == 0 ]]
