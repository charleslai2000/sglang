#!/usr/bin/env bash
# Shared-prefix C32 shape on the frozen T007 service configuration.
# 8192-token input (7168 shared prefix + 1024 distinct new tokens), 256 output,
# 32 concurrent requests, write_back + wait_complete, chunk4096, graph b32.
# Reuses T006's recorded launch argv and the g1 shared-prefix request harness;
# no profiler, so the client wall clock is the measured quantity.
set -Eeuo pipefail
ROOT=/home/ubuntu/workspaces/3rdparty/sglang-hicache
VENV=/home/ubuntu/venvs/sglang-3090
DATA=/data/sglang-hicache/gemma4
MODEL=$DATA/model
AOT=/data/sglang-hicache/g2-quasar-runs/20261110T-g2-postrope-e5m2-quality/aot-sm86-package
OVERLAY=$ROOT/control/gemma4-w4a16-3090-performance-capacity/runs/overlay
RUNS=$ROOT/control/gemma4-w4a16-3090-performance-capacity/runs
T006=/data/sglang-hicache/gemma4/runs/20261124T-g5-live-capacity-65536/c8-800-r2
OUT=${T007_OUT:?set T007_OUT to an empty directory}
PORT=${T007_SHARED_PORT:-31405}
LOCK=/tmp/f1-r16b-gpu-exclusive.lock
PREFIX_TOKENS=${T007_SHARED_PREFIX:-7168}
TOTAL_TOKENS=${T007_SHARED_TOTAL:-8192}
OUTPUT_TOKENS=${T007_SHARED_OUTPUT:-256}
COUNT=${T007_SHARED_COUNT:-32}
CHUNK_OVERRIDE=${T007_CHUNK:-4096}

[[ -d "$OUT" && -z "$(ls -A "$OUT")" ]] || { echo "T007_OUT must be an empty directory: $OUT" >&2; exit 2; }
mkdir -p "$OUT"
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
"$VENV/bin/python" - "$ROOT" "$OUT/source-identity.json" <<'PY'
import hashlib, importlib, json, os, subprocess, sys
root=os.path.realpath(sys.argv[1]); mods=("sglang","sglang.launch_server","sglang.srt.managers.scheduler","sglang.srt.mem_cache.unified_radix_cache")
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

eval "ARGS=($(cat "$T006/launch-argv.txt"))"
NEW=(); skip=0; had=0
for ((i=0;i<${#ARGS[@]};i++)); do
  if [[ $skip == 1 ]]; then skip=0; continue; fi
  if [[ ${ARGS[i]} == --export-metrics-to-file-dir ]]; then NEW+=("${ARGS[i]}" "$OUT/request-metrics"); skip=1; continue; fi
  if [[ ${ARGS[i]} == --port ]]; then NEW+=("${ARGS[i]}" "$PORT"); skip=1; continue; fi
  if [[ ${ARGS[i]} == --hicache-write-policy ]]; then NEW+=("${ARGS[i]}" write_back); skip=1; continue; fi
  if [[ ${ARGS[i]} == --hicache-storage-prefetch-policy ]]; then NEW+=("${ARGS[i]}" wait_complete); skip=1; continue; fi
  if [[ ${ARGS[i]} == --chunked-prefill-size ]]; then NEW+=("${ARGS[i]}" "$CHUNK_OVERRIDE"); skip=1; continue; fi
  if [[ ${ARGS[i]} == --hicache-storage-backend-extra-config ]]; then
    NEW+=("${ARGS[i]}")
    skip=2
    continue
  fi
  if [[ $skip == 2 ]]; then
    skip=0
    NEW+=("$(python3 -c 'import json,sys; c=json.loads(sys.argv[1]); c["storage_dir"]=sys.argv[2]; print(json.dumps(c))' "${ARGS[i]}" "$OUT/l3-extent")")
    continue
  fi
  NEW+=("${ARGS[i]}")
done
ARGS=("${NEW[@]}")
mkdir -p "$OUT/request-metrics" "$OUT/l3-extent"
printf '%q ' "${ARGS[@]}" > "$OUT/launch-argv.txt"; printf '\nshape=shared-prefix prefix_tokens=%s total_tokens=%s output_tokens=%s count=%s chunked_prefill_size=%s write_policy=write_back prefetch_policy=wait_complete\n' \
  "$PREFIX_TOKENS" "$TOTAL_TOKENS" "$OUTPUT_TOKENS" "$COUNT" "$CHUNK_OVERRIDE" > "$OUT/manifest.txt"
printf 'task_started=%s\nwrapper_pid=%s\n' "$(date -u +%FT%TZ)" "$$" >> "$OUT/manifest.txt"

SAMPLER= GPU_MON= SERVER_PID=
stop_tree(){ local r=${1:-} s=${2:-TERM} c; [[ -n "$r" ]] || return 0; while read -r c; do stop_tree "$c" "$s"; done < <(pgrep -P "$r" 2>/dev/null || true); kill -s "$s" "$r" 2>/dev/null || true; }
cleanup(){
  local rc=$?
  trap - EXIT TERM INT
  set +e
  curl -fsS --max-time 5 "http://127.0.0.1:$PORT/metrics" > "$OUT/metrics-at-stop.prom" 2>"$OUT/metrics-at-stop.err"
  [[ -z $SAMPLER ]] || { kill -TERM "$SAMPLER" 2>/dev/null; wait "$SAMPLER" 2>/dev/null; }
  [[ -z $GPU_MON ]] || { kill -TERM "$GPU_MON" 2>/dev/null; wait "$GPU_MON" 2>/dev/null; }
  if [[ -n $SERVER_PID ]]; then stop_tree "$SERVER_PID" TERM; for _ in $(seq 1 60); do kill -0 "$SERVER_PID" 2>/dev/null || break; sleep 1; done; stop_tree "$SERVER_PID" KILL; wait "$SERVER_PID" 2>/dev/null; fi
  pkill -TERM -f "sglang.launch_server .*--port $PORT" 2>/dev/null
  for _ in $(seq 1 30); do pgrep -f "sglang.launch_server .*--port $PORT" >/dev/null || break; sleep 1; done
  pkill -KILL -f "sglang.launch_server .*--port $PORT" 2>/dev/null
  nvidia-smi --query-gpu=timestamp,utilization.gpu,memory.used,memory.total --format=csv > "$OUT/gpu-after.csv" 2>&1
  ss -ltnp | grep ":$PORT\\b" > "$OUT/port-after.txt" 2>&1 || true
  free -h > "$OUT/ram-after.txt"
  printf 'wrapper_exit=%s ended=%s\n' "$rc" "$(date -u +%FT%TZ)" > "$OUT/exit.txt"
  exit "$rc"
}
trap cleanup EXIT
trap 'exit 143' TERM
trap 'exit 130' INT

"$VENV/bin/python" -u -m sglang.launch_server "${ARGS[@]}" > "$OUT/server.log" 2>&1 &
SERVER_PID=$!
echo "$SERVER_PID" > "$OUT/server.pid"
ready=0
for _ in $(seq 1 1200); do
  if curl -fsS --max-time 2 "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; then ready=1; break; fi
  kill -0 "$SERVER_PID" 2>/dev/null || { tail -100 "$OUT/server.log"; exit 2; }
  sleep 1
done
[[ $ready == 1 ]]
curl -fsS --max-time 20 "http://127.0.0.1:$PORT/metrics" > "$OUT/metrics-at-start.prom"
curl -fsS --max-time 20 "http://127.0.0.1:$PORT/model_info" > "$OUT/model-info.json"
nvidia-smi --query-gpu=timestamp,utilization.gpu,memory.used,memory.total --format=csv > "$OUT/gpu-ready.csv"
"$VENV/bin/python" /tmp/g1_metrics_sampler.py --url "http://127.0.0.1:$PORT/metrics" --out "$OUT/pool-series.jsonl" --interval 0.5 --seconds 1800 & SAMPLER=$!
nvidia-smi --query-gpu=timestamp,utilization.gpu,memory.used,memory.total --format=csv --loop-ms=1000 > "$OUT/gpu-samples.csv" & GPU_MON=$!

HARNESS=$RUNS/g1_shared_prefix_hicache.py
FIXTURE=$OUT/fixture-${TOTAL_TOKENS}.json
SHAPE=(--url "http://127.0.0.1:$PORT" --fixture "$FIXTURE" --out "$OUT/client" --count "$COUNT" --prefix-tokens "$PREFIX_TOKENS" --total-tokens "$TOTAL_TOKENS" --new-tokens "$OUTPUT_TOKENS")
run_step(){ printf '%s start=%s\n' "$1" "$(date -u +%FT%TZ)" >> "$OUT/steps.txt"; }
run_step fixture
"$VENV/bin/python" "$HARNESS" --action fixture "${SHAPE[@]}" > "$OUT/fixture.stdout" 2> "$OUT/fixture.stderr"
run_step warm
WARM_START=$(date +%s)
"$VENV/bin/python" "$HARNESS" --action warm "${SHAPE[@]}" > "$OUT/warm.stdout" 2> "$OUT/warm.stderr"
printf 'warm_wall_seconds=%s\n' "$(( $(date +%s) - WARM_START ))" >> "$OUT/steps.txt"
run_step batch
BATCH_START=$(date +%s); BATCH_START_UTC=$(date -u +%FT%TZ)
"$VENV/bin/python" "$HARNESS" --action batch "${SHAPE[@]}" --max-parallel "$COUNT" > "$OUT/batch.stdout" 2> "$OUT/batch.stderr"
BATCH_RC=$?
BATCH_END=$(date +%s)
printf 'batch_wall_seconds=%s start_utc=%s end_utc=%s rc=%s\n' "$(( BATCH_END - BATCH_START ))" "$BATCH_START_UTC" "$(date -u +%FT%TZ)" "$BATCH_RC" >> "$OUT/steps.txt"
curl -fsS --max-time 5 "http://127.0.0.1:$PORT/metrics" > "$OUT/metrics-at-end.prom" 2>"$OUT/metrics-at-end.err" || true

"$VENV/bin/python" - "$OUT" "$(( BATCH_END - BATCH_START ))" <<'PY'
import json, os, sys
out, client_wall = sys.argv[1], int(sys.argv[2])
def counters(path, name):
    values = {}
    try:
        for line in open(path):
            if line.startswith(name):
                label = line.split("{", 1)[1].split("}", 1)[0] if "{" in line else ""
                values[label] = float(line.rsplit(" ", 1)[1])
    except FileNotFoundError:
        pass
    return values
start = counters(os.path.join(out, "metrics-at-start.prom"), "sglang:forward_execution_seconds_total")
end = counters(os.path.join(out, "metrics-at-end.prom"), "sglang:forward_execution_seconds_total")
def delta(c):
    l, r = start.get('category="%s"' % c), end.get('category="%s"' % c)
    return None if l is None or r is None else r - l
extend_s, decode_s = delta("extend"), delta("decode")
batch = {}
try:
    batch = json.load(open(os.path.join(out, "client", "batch.json")))
except FileNotFoundError:
    pass
result = {
    "shape": "shared_prefix_c32",
    "client_wall_seconds": client_wall,
    "requests": batch.get("count"),
    "success": batch.get("success"),
    "errors": batch.get("errors"),
    "aggregate_output_tps": batch.get("aggregate_output_tps"),
    "harness_wall_s": batch.get("wall_s"),
    "ttft_p50_s": batch.get("ttft_p50_s"),
    "ttft_p95_s": batch.get("ttft_p95_s"),
    "tpot_p50_s": batch.get("tpot_p50_s"),
    "latency_p50_s": batch.get("latency_p50_s"),
    "latency_p95_s": batch.get("latency_p95_s"),
    "extend_forward_seconds": extend_s,
    "decode_forward_seconds": decode_s,
    "forward_seconds_total": None if None in (extend_s, decode_s) else extend_s + decode_s,
    "forward_duty_pct_vs_client_wall": None if None in (extend_s, decode_s) or not client_wall else 100.0 * (extend_s + decode_s) / client_wall,
}
try:
    result["git_head"] = open(os.path.join(out, "source-head.txt")).read().strip()
except FileNotFoundError:
    pass
json.dump(result, open(os.path.join(out, "official-summary.json"), "w"), indent=2, sort_keys=True, default=str)
line = "shared_prefix_c32 output_tps=%s wall_s=%s success=%s/%s ttft_p50=%s tpot_p50=%s duty_pct=%s head=%s" % (
    None if result["aggregate_output_tps"] is None else round(result["aggregate_output_tps"], 2),
    client_wall, result["success"], result["requests"],
    None if result["ttft_p50_s"] is None else round(result["ttft_p50_s"], 3),
    None if result["tpot_p50_s"] is None else round(result["tpot_p50_s"], 4),
    None if result["forward_duty_pct_vs_client_wall"] is None else round(result["forward_duty_pct_vs_client_wall"], 2),
    str(result.get("git_head", ""))[:10])
open(os.path.join(out, "official-summary.txt"), "w").write(line + "\n")
print(line)
if not result["requests"] or result["success"] != result["requests"]:
    print("SHARED_PREFIX_INCOMPLETE: not an acceptance number")
    sys.exit(3)
PY
