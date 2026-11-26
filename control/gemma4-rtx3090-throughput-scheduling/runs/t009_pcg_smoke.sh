#!/usr/bin/env bash
# T009 prefill CUDA graph smoke: numeric parity (graph vs eager), replay evidence,
# capture memory, and H2D-pending eager fallback. One server per invocation.
#
# usage: t009_pcg_smoke.sh <graph|eager> <out_dir>
set -euo pipefail
MODE=${1:?graph|eager}
OUT=${2:?out dir}
ROOT=/home/ubuntu/workspaces/3rdparty/sglang-hicache
MODEL=/data/sglang-hicache/gemma4/model
PORT=31403
VENV=/home/ubuntu/venvs/sglang-3090
LOCK=/tmp/f1-r16b-gpu-exclusive.lock
BUCKETS="${T009_PCG_BUCKETS:-1024 1280 1536 2048 3584 4096}"

mkdir -p "$OUT"
rm -rf "$OUT/l3-extent" "$OUT/request-metrics"
mkdir -p "$OUT/request-metrics"

ARGS=(
  --model-path "$MODEL" --trust-remote-code --host 127.0.0.1 --port "$PORT"
  --context-length 131072 --max-running-requests 32 --mem-fraction-static .94
  --kv-cache-dtype fp8_e5m2 --attention-backend triton
  --cuda-graph-backend-decode full --cuda-graph-max-bs-decode 32
  --log-level info --enable-metrics --decode-log-interval 40
  --skip-server-warmup --enable-hierarchical-cache --hicache-size 8
  --hicache-write-policy write_back --hicache-io-backend kernel
  --hicache-mem-layout page_first --hicache-host-memory-mode cache
  --hicache-storage-backend extent
  --hicache-storage-backend-extra-config "{\"storage_dir\":\"$OUT/l3-extent\",\"extent_size\":67108864,\"file_size\":34359738368,\"max_size\":34359738368,\"min_free_space\":1073741824}"
  --hicache-storage-prefetch-policy wait_complete
  --chunked-prefill-size 4096
)
if [[ $MODE == graph ]]; then
  ARGS+=(--cuda-graph-backend-prefill breakable --cuda-graph-bs-prefill $BUCKETS)
else
  ARGS+=(--cuda-graph-backend-prefill disabled)
fi
printf '%q ' "${ARGS[@]}" > "$OUT/launch-argv.txt"; echo >> "$OUT/launch-argv.txt"

exec 9>"$LOCK"
flock -n 9 || { echo "GPU lock busy" >&2; exit 4; }

VENV_SITE=$VENV/lib/python3.12/site-packages
AOT=/data/sglang-hicache/g2-quasar-runs/20261110T-g2-postrope-e5m2-quality/aot-sm86-package
OVERLAY=$ROOT/control/gemma4-w4a16-3090-performance-capacity/runs/overlay
RUNS=$ROOT/control/gemma4-w4a16-3090-performance-capacity/runs
export PYTHONNOUSERSITE=1 SGLANG_GEMMA4_SWA_POOL_TOKENS=65536
export PYTHONPATH="$RUNS:$AOT:$ROOT/python:$VENV_SITE:$ROOT/python/sglang/kernels/aot/python:$OVERLAY"
export LD_LIBRARY_PATH="$VENV_SITE/torch/lib:/usr/local/cuda-12.9/lib64"
export SGLANG_CACHE_DIR=/data/sglang-hicache/gemma4/cache
export HF_HOME=/data/sglang-hicache/gemma4/cache/hf-home
export HF_DATASETS_CACHE=/data/sglang-hicache/gemma4/cache/datasets
export SGLANG_ENABLE_METRICS_DEVICE_TIMER=1 SGLANG_ENABLE_NVTX_SCHEDULER=1
# Prefill graph capture needs contiguous activation memory on top of a KV pool
# sized at 0.94 mem fraction; expandable segments removes the reserved-but-
# unallocated tail that made the first 4096-token capture OOM. Allocation
# policy only -- no capacity change.
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True

( "$VENV/bin/python" -m sglang.launch_server "${ARGS[@]}" > "$OUT/server.log" 2>&1 ) &
SPID=$!
cleanup() {
  pkill -TERM -P $SPID 2>/dev/null || true
  kill -TERM $SPID 2>/dev/null || true
  for _ in $(seq 1 60); do kill -0 $SPID 2>/dev/null || break; sleep 1; done
  kill -KILL $SPID 2>/dev/null || true
  wait $SPID 2>/dev/null || true
  pkill -f "port $PORT" 2>/dev/null || true
}
trap cleanup EXIT

ready=0
for _ in $(seq 1 600); do
  if curl -sf "http://127.0.0.1:$PORT/health_generate" >/dev/null 2>&1; then ready=1; break; fi
  kill -0 $SPID 2>/dev/null || break
  sleep 1
done
[[ $ready == 1 ]] || { echo "SERVER_NOT_READY"; tail -40 "$OUT/server.log"; exit 5; }

nvidia-smi --query-gpu=memory.used --format=csv,noheader > "$OUT/gpu-used-after-capture.txt"

"$VENV/bin/python" - "$PORT" "$OUT" <<'PY'
import json, sys, time
import requests

port, out = sys.argv[1], sys.argv[2]
url = f"http://127.0.0.1:{port}/generate"

def gen(ids, n=32, tag=""):
    body = {"input_ids": ids, "sampling_params": {"temperature": 0.0, "top_k": 1,
            "max_new_tokens": n, "ignore_eos": True}}
    t0 = time.time()
    r = requests.post(url, json=body, timeout=600)
    r.raise_for_status()
    d = r.json()
    meta = d.get("meta_info", {})
    return {"tag": tag, "len_in": len(ids), "ids": d.get("output_ids") or [],
            "cached": meta.get("cached_tokens"), "wall_s": round(time.time() - t0, 3)}

# Bucket-exact shapes only: replay requires an exact hit on a captured
# num_tokens bucket, so probes must not rely on padding.
cases = []
for n in (1024, 1280, 3584, 4096):
    ids = list(range(1000, 1000 + n))   # ids stay inside the tokenizer vocab
    cases.append(gen(ids, tag=f"cold{n}"))
json.dump(cases, open(f"{out}/responses.json", "w"), indent=1)

# prefix-hit (radix match, prefix_lens > 0, extend 1 token)
cases2 = [gen(list(range(1000, 2024)), tag="warm1024")]
json.dump(cases2, open(f"{out}/responses-warm.json", "w"), indent=1)

# 4 concurrent x 1024 = exact 4096 aggregate, no chunk split
import concurrent.futures as cf
def one(i):
    # 4 x 256 = exact 1024 aggregate -> exercises a multi-request replay at a
    # captured bucket, with in-vocabulary ids.
    base = 20000 + i * 2000
    ids = list(range(base, base + 256))
    return gen(ids, tag=f"conc{i}")
with cf.ThreadPoolExecutor(max_workers=4) as ex:
    conc = list(ex.map(one, range(4)))
json.dump(conc, open(f"{out}/responses-concurrent.json", "w"), indent=1)
print("responses_ok")
PY

sleep 2
curl -sf "http://127.0.0.1:$PORT/metrics" > "$OUT/metrics-smoke.prom" || true
nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader > "$OUT/gpu-used-end.txt"

grep -c "cuda graph: True" "$OUT/server.log" > "$OUT/count-prefill-graph-true.txt" || true
grep -c "cuda graph: False" "$OUT/server.log" > "$OUT/count-prefill-graph-false.txt" || true
grep -iE "prefill CUDA graph|Capture.*prefill|prefill graph" "$OUT/server.log" | head -20 > "$OUT/capture-lines.txt" || true
grep -E "Prefill batch" "$OUT/server.log" | sed -E 's/.*(#new-seq: [0-9]+, #new-token: [0-9]+, #cached-token: [0-9]+).*cuda graph: (True|False).*/\1 cuda_graph=\2/' | head -30 > "$OUT/prefill-batches.txt" || true
echo "SMOKE_DONE mode=$MODE"
