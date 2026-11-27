#!/usr/bin/env bash
# T011: bounded real-batch extend measurement on the frozen production service.
#
# Starts the production service (Frozen C-8 argv with hierarchical cache removed,
# i.e. L1-only), sends a fixed set of *concurrent* long prompts so each extend
# step is a real multi-request batch through all 42 layers, and reports the
# device extend time per prefill token. No profiling, no bench appending.
set -Eeuo pipefail
ROOT=/home/ubuntu/workspaces/3rdparty/sglang-hicache
VENV=/home/ubuntu/venvs/sglang-3090
DATA=/data/sglang-hicache/gemma4
MODEL=$DATA/model
AOT=/data/sglang-hicache/g2-quasar-runs/20261110T-g2-postrope-e5m2-quality/aot-sm86-package
RUNS=$ROOT/control/gemma4-w4a16-3090-performance-capacity/runs
OVERLAY=$RUNS/overlay
BASELINE_ARGV=${T011_BASELINE_ARGV:-/data/sglang-hicache/gemma4/runs/20261126T-t009-c8-acceptance-r8/launch-argv.txt}
OUT=${T011_OUT:?set T011_OUT}
FLAG=${T011_FLAG:-0}
PORT=${T011_PORT:-31411}
LOCK=/tmp/f1-r16b-gpu-exclusive.lock
CLIENTS=${T011_CLIENTS:-12}
PROMPT_LEN=${T011_PROMPT_LEN:-9216}
ROUNDS=${T011_ROUNDS:-3}
TIMING_PATH=${T011_TIMING_PATH:-}
TIMING_STRIDE=${T011_TIMING_STRIDE:-1}

[[ -d "$OUT" ]] || { echo "T011_OUT must exist: $OUT" >&2; exit 2; }
mapfile -t CONTENTS < <(find "$OUT" -mindepth 1 -maxdepth 1 -printf '%f\n')
[[ ${#CONTENTS[@]} == 1 && ${CONTENTS[0]} == intent.txt ]] || {
  echo "T011_OUT must contain only intent.txt before launch: $OUT" >&2; exit 2; }

exec 9>"$LOCK"
flock -n 9 || { echo GPU_LOCK_BUSY | tee "$OUT/preflight.txt"; exit 90; }
nvidia-smi --query-compute-apps=pid --format=csv,noheader | grep -q '[0-9]' && {
  echo GPU_PROCESS_BUSY | tee "$OUT/preflight.txt"; exit 92; } || true
ss -ltn | grep -q ":$PORT\b" && { echo PORT_BUSY | tee "$OUT/preflight.txt"; exit 91; } || true
printf 'lock=acquired port=%s flag=%s clients=%s prompt_len=%s rounds=%s checked=%s\n' \
  "$PORT" "$FLAG" "$CLIENTS" "$PROMPT_LEN" "$ROUNDS" "$(date -Is)" > "$OUT/preflight.txt"
git -C "$ROOT" rev-parse HEAD > "$OUT/source-head.txt"
git -C "$ROOT" status --porcelain > "$OUT/source-status.txt"

# Frozen production argv minus every hierarchical-cache flag (L1-only), with a
# local port and a per-run metrics directory.
eval "ARGS=($(cat "$BASELINE_ARGV"))"
NEW=(); skip=0
for ((i=0;i<${#ARGS[@]};i++)); do
  if [[ $skip == 1 ]]; then skip=0; continue; fi
  case ${ARGS[i]} in
    --enable-hierarchical-cache) continue ;;
    --hicache-size|--hicache-write-policy|--hicache-io-backend|--hicache-mem-layout|--hicache-host-memory-mode|--hicache-storage-backend|--hicache-storage-backend-extra-config|--hicache-storage-prefetch-policy) skip=1; continue ;;
    --port) NEW+=("${ARGS[i]}" "$PORT"); skip=1; continue ;;
    --export-metrics-to-file-dir) NEW+=("${ARGS[i]}" "$OUT/request-metrics"); skip=1; continue ;;
  esac
  NEW+=("${ARGS[i]}")
done
ARGS=("${NEW[@]}")
mkdir -p "$OUT/request-metrics"
printf '%q ' "${ARGS[@]}" > "$OUT/launch-argv.txt"

export PYTHONNOUSERSITE=1 SGLANG_GEMMA4_SWA_POOL_TOKENS=65536 \
  PYTHONPATH="$RUNS:$AOT:$ROOT/python:$VENV/lib/python3.12/site-packages:$ROOT/python/sglang/kernels/aot/python:$OVERLAY" \
  LD_LIBRARY_PATH="$VENV/lib/python3.12/site-packages/torch/lib:/usr/local/cuda-12.9/lib64" \
  SGLANG_CACHE_DIR="$DATA/cache" HF_HOME="$DATA/cache/hf-home" HF_DATASETS_CACHE="$DATA/cache/datasets" \
  SGLANG_ENABLE_METRICS_DEVICE_TIMER=1
export SGLANG_ENABLE_T011_BF16_RAGGED_FULL_EXTEND="$FLAG"
if [[ -n $TIMING_PATH ]]; then
  export SGLANG_T011_BF16_TIMING_PATH="$TIMING_PATH" SGLANG_T011_BF16_TIMING_STRIDE="$TIMING_STRIDE"
fi

SERVER_PID=
cleanup(){
  local rc=$?
  trap - EXIT TERM INT
  set +e
  curl -fsS --max-time 5 "http://127.0.0.1:$PORT/metrics" > "$OUT/metrics-at-stop.prom" 2>/dev/null
  # Graceful stop first so worker atexit hooks (component timing dump) run.
  [[ -z $SERVER_PID ]] || kill -INT "$SERVER_PID" 2>/dev/null
  for _ in $(seq 1 30); do pgrep -f "sglang.launch_server .*--port $PORT" >/dev/null || break; sleep 1; done
  [[ -z $SERVER_PID ]] || kill -TERM "$SERVER_PID" 2>/dev/null
  for _ in $(seq 1 60); do pgrep -f "sglang.launch_server .*--port $PORT" >/dev/null || break; sleep 1; done
  pkill -KILL -f "sglang.launch_server .*--port $PORT" 2>/dev/null
  nvidia-smi --query-gpu=timestamp,utilization.gpu,memory.used --format=csv > "$OUT/gpu-after.csv" 2>&1
  ss -ltnp | grep ":$PORT\b" > "$OUT/port-after.txt" 2>&1 || true
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
for _ in $(seq 1 900); do
  curl -fsS --max-time 2 "http://127.0.0.1:$PORT/health" >/dev/null 2>&1 && { ready=1; break; }
  kill -0 "$SERVER_PID" 2>/dev/null || { tail -80 "$OUT/server.log"; exit 2; }
  sleep 1
done
[[ $ready == 1 ]] || { echo SERVER_NOT_READY; tail -80 "$OUT/server.log"; exit 3; }
curl -fsS --max-time 20 "http://127.0.0.1:$PORT/metrics" > "$OUT/metrics-at-start.prom"
nvidia-smi --query-gpu=timestamp,utilization.gpu,memory.used --format=csv > "$OUT/gpu-ready.csv"

"$VENV/bin/python" - "$PORT" "$OUT" "$CLIENTS" "$PROMPT_LEN" "$ROUNDS" <<'PY'
import json, os, sys, threading, time, urllib.request

port, out, clients, prompt_len, rounds = (
    sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5]))
base = f"http://127.0.0.1:{port}"

def http(path, payload=None, timeout=1800):
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(base + path, data=data,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode()
    return json.loads(body) if body.strip().startswith(("{", "[")) else body

def metric(name, text=None, category=None):
    """Sum a sglang:* series, optionally restricted to one category label."""
    text = text if text is not None else http("/metrics")
    total = 0.0
    for line in text.splitlines():
        if not line.startswith(name):
            continue
        labels = line.split("{", 1)[1].split("}", 1)[0] if "{" in line else ""
        if category is not None and f'category="{category}"' not in labels:
            continue
        total += float(line.rsplit(" ", 1)[1])
    return total

# Distinct, non-shareable prompts per round so every extend is a real prefill.
def prompt(seed):
    parts = [f"T011 fwd-bench seed={seed} client={seed % clients}."]
    idx = 0
    while len(" ".join(parts).split()) < prompt_len:
        parts.append(f"record{idx} alpha{idx % 17} beta{idx % 23} gamma{idx % 29}")
        idx += 1
    return " ".join(parts)[: prompt_len * 6]

records = []
for rnd in range(rounds):
    try:
        http("/flush_cache", None)
    except Exception:
        pass
    time.sleep(0.5)
    before = metric("sglang:forward_execution_seconds_total", http("/metrics"))
    ext_before = metric("sglang:forward_execution_seconds_total", http("/metrics"), "extend")
    dec_before = metric("sglang:forward_execution_seconds_total", http("/metrics"), "decode")
    results = []
    errors = []

    def run(i):
        try:
            body = http("/generate", {
                "text": prompt(rnd * 1000 + i),
                "sampling_params": {"max_new_tokens": 1, "temperature": 0.0,
                                    "ignore_eos": True},
            })
            results.append(body)
        except Exception as exc:  # keep the run bounded and honest
            errors.append(repr(exc))

    t0 = time.perf_counter()
    threads = [threading.Thread(target=run, args=(i,)) for i in range(clients)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    wall = time.perf_counter() - t0
    text = http("/metrics")
    ext_after = metric("sglang:forward_execution_seconds_total", text, "extend")
    dec_after = metric("sglang:forward_execution_seconds_total", text, "decode")
    prompt_tokens = sum(int(r.get("meta_info", {}).get("prompt_tokens", 0)) for r in results)
    records.append({
        "round": rnd, "clients": clients, "completed": len(results),
        "errors": errors[:3], "error_count": len(errors),
        "wall_seconds": wall,
        "extend_seconds": ext_after - ext_before,
        "decode_seconds": dec_after - dec_before,
        "forward_seconds_all_categories": metric("sglang:forward_execution_seconds_total", text) - before,
        "prompt_tokens": prompt_tokens,
        "extend_ms_per_1k_prefill_tokens": (
            1000.0 * (ext_after - ext_before) / prompt_tokens if prompt_tokens else None),
    })
    print(json.dumps(records[-1]), flush=True)

tot_ext = sum(r["extend_seconds"] for r in records)
tot_tok = sum(r["prompt_tokens"] for r in records)
summary = {
    "clients": clients, "prompt_len_requested": prompt_len, "rounds": rounds,
    "completed": sum(r["completed"] for r in records),
    "errors": sum(r["error_count"] for r in records),
    "extend_seconds_total": tot_ext,
    "prefill_tokens_total": tot_tok,
    "extend_ms_per_1k_prefill_tokens": 1000.0 * tot_ext / tot_tok if tot_tok else None,
    "rounds_detail": records,
}
with open(os.path.join(out, "fwd-bench.json"), "w") as fh:
    json.dump(summary, fh, indent=2)
print("SUMMARY " + json.dumps({k: summary[k] for k in (
    "completed", "errors", "extend_seconds_total", "prefill_tokens_total",
    "extend_ms_per_1k_prefill_tokens")}), flush=True)
PY

cp "$OUT/fwd-bench.json" "$OUT/fwd-bench-final.json"
echo DONE
