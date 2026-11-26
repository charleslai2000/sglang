#!/usr/bin/env bash
# Steady-state C32 short-context load on the frozen T007 service configuration.
# 1024-token prompts (768 shared prefix + 256 distinct), 256 output tokens, 32
# continuously replenished clients, write_back + wait_complete, chunk4096, b32.
# Reuses T006's recorded launch argv, the g1 shared-prefix fixture/warm harness and
# t007_steady_c32.py for the window; no profiler.
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
PORT=${T007_STEADY_PORT:-31406}
LOCK=/tmp/f1-r16b-gpu-exclusive.lock
PREFIX_TOKENS=${T007_STEADY_PREFIX:-768}
TOTAL_TOKENS=${T007_STEADY_TOTAL:-1024}
OUTPUT_TOKENS=${T007_STEADY_OUTPUT:-256}
COUNT=${T007_STEADY_COUNT:-32}
CHUNK_OVERRIDE=${T007_CHUNK:-4096}

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
DRIVER=$ROOT/control/gemma4-rtx3090-throughput-scheduling/runs/t007_steady_c32.py
FIXTURE=$OUT/fixture-${TOTAL_TOKENS}.json
SHAPE=(--url "http://127.0.0.1:$PORT" --fixture "$FIXTURE" --out "$OUT/client" --count "$COUNT" --prefix-tokens "$PREFIX_TOKENS" --total-tokens "$TOTAL_TOKENS" --new-tokens "$OUTPUT_TOKENS")
run_step(){ printf '%s start=%s\n' "$1" "$(date -u +%FT%TZ)" >> "$OUT/steps.txt"; }

run_step fixture
"$VENV/bin/python" "$HARNESS" --action fixture "${SHAPE[@]}" > "$OUT/fixture.stdout" 2> "$OUT/fixture.stderr"
run_step warm
WARM_START=$(date +%s)
"$VENV/bin/python" "$HARNESS" --action warm "${SHAPE[@]}" > "$OUT/warm.stdout" 2> "$OUT/warm.stderr"
printf 'warm_wall_seconds=%s\n' "$(( $(date +%s) - WARM_START ))" >> "$OUT/steps.txt"

curl -fsS --max-time 20 "http://127.0.0.1:$PORT/metrics" > "$OUT/metrics-before-steady.prom" 2>/dev/null || true
STEADY_START=$(date +%s); STEADY_START_UTC=$(date -u +%FT%TZ)
run_step steady-rotate
"$VENV/bin/python" "$DRIVER" --url "http://127.0.0.1:$PORT" --fixture "$FIXTURE" --out "$OUT/steady-rotate.json" \
  --clients "$COUNT" --seconds "${T007_STEADY_SECONDS:-90}" --new-tokens "$OUTPUT_TOKENS" --variant rotate \
  > "$OUT/steady-rotate.stdout" 2> "$OUT/steady-rotate.stderr"
ROTATE_RC=$?
run_step steady-cached
"$VENV/bin/python" "$DRIVER" --url "http://127.0.0.1:$PORT" --fixture "$FIXTURE" --out "$OUT/steady-cached.json" \
  --clients "$COUNT" --seconds "${T007_STEADY_CACHED_SECONDS:-60}" --new-tokens "$OUTPUT_TOKENS" --variant cached \
  > "$OUT/steady-cached.stdout" 2> "$OUT/steady-cached.stderr"
CACHED_RC=$?
STEADY_END=$(date +%s)
printf 'steady_start_utc=%s steady_end_utc=%s rotate_rc=%s cached_rc=%s\n' "$STEADY_START_UTC" "$(date -u +%FT%TZ)" "$ROTATE_RC" "$CACHED_RC" >> "$OUT/steps.txt"
curl -fsS --max-time 5 "http://127.0.0.1:$PORT/metrics" > "$OUT/metrics-at-end.prom" 2>"$OUT/metrics-at-end.err" || true

"$VENV/bin/python" - "$OUT" "$(( STEADY_END - STEADY_START ))" <<'PY'
import json, os, sys
out, client_wall = sys.argv[1], int(sys.argv[2])


def counters(path, name):
    values = {}
    try:
        for line in open(path):
            if line.startswith(name):
                labels = line.split("{", 1)[1].split("}", 1)[0] if "{" in line else ""
                category = None
                for part in labels.split(","):
                    key, _, value = part.partition("=")
                    if key == "category":
                        category = value.strip('"')
                values[category if category is not None else labels] = float(line.rsplit(" ", 1)[1])
    except FileNotFoundError:
        pass
    return values


start = counters(os.path.join(out, "metrics-before-steady.prom"), "sglang:forward_execution_seconds_total")
end = counters(os.path.join(out, "metrics-at-end.prom"), "sglang:forward_execution_seconds_total")


def delta(category):
    left, right = start.get(category), end.get(category)
    return None if left is None or right is None else right - left


extend_s, decode_s = delta("extend"), delta("decode")
result = {"shape": "steady_c32", "client_wall_seconds": client_wall,
          "extend_forward_seconds": extend_s, "decode_forward_seconds": decode_s,
          "forward_duty_pct_vs_client_wall": None if None in (extend_s, decode_s) or not client_wall else 100.0 * (extend_s + decode_s) / client_wall}
for variant in ("rotate", "cached"):
    path = os.path.join(out, "steady-%s.json" % variant)
    try:
        result[variant] = json.load(open(path))
    except FileNotFoundError:
        result[variant] = None
try:
    result["git_head"] = open(os.path.join(out, "source-head.txt")).read().strip()
except FileNotFoundError:
    pass
json.dump(result, open(os.path.join(out, "official-summary.json"), "w"), indent=2, sort_keys=True, default=str)
lines = ["steady_c32 clients=%s input=%s output=%s" % (
    (result["rotate"] or {}).get("clients"), 1024, 256)]
for variant in ("rotate", "cached"):
    entry = result[variant] or {}
    lines.append("  %-6s out_tps=%s req_s=%s lat_p50=%s inflight=%s errors=%s" % (
        variant, entry.get("output_tps"), entry.get("requests_per_second"),
        entry.get("latency_p50_s"), entry.get("mean_inflight_requests"), entry.get("errors")))
lines.append("  extend_s=%s decode_s=%s duty_pct=%s head=%s" % (
    None if extend_s is None else round(extend_s, 2), None if decode_s is None else round(decode_s, 2),
    None if result["forward_duty_pct_vs_client_wall"] is None else round(result["forward_duty_pct_vs_client_wall"], 2),
    str(result.get("git_head", ""))[:10]))
text = "\n".join(lines) + "\n"
open(os.path.join(out, "official-summary.txt"), "w").write(text)
print(text, end="")
PY

[[ $ROTATE_RC == 0 && $CACHED_RC == 0 ]]
