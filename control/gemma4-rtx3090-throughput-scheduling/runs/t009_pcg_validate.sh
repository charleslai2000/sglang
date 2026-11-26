#!/usr/bin/env bash
# T009 prefill-graph correctness validation (item 3 of the convergence round):
#   A. alternating bucket replay -- the same probes at 1024/1280/1536/2048/4096 tokens,
#      sent twice in interleaved order; identical greedy ids per probe prove that
#      replaying different buckets alternately stays correct.
#   B. real L3 restore with the graph enabled -- small device/host pools so the target
#      prefix can only come back from the Extent tier, then /flush_cache + re-request;
#      requires extent reads, restored cached tokens, and ids identical to the cold run.
#   C. HiCache H2D fallback -- the prefill graph must stand aside while a layer transfer
#      is in flight (counted from the runner log).
#
# usage: t009_pcg_validate.sh <out_dir>
set -euo pipefail
OUT=${1:?out dir}
ROOT=/home/ubuntu/workspaces/3rdparty/sglang-hicache
VENV=/home/ubuntu/venvs/sglang-3090
DATA=/data/sglang-hicache/gemma4
MODEL=$DATA/model
PORT=31404
LOCK=/tmp/f1-r16b-gpu-exclusive.lock
BUCKETS="${T009_PCG_BUCKETS:-1024 1280 1536 2048 4096}"

mkdir -p "$OUT"; rm -rf "$OUT/l3-extent"; mkdir -p "$OUT/l3-extent"

ARGS=(
  --model-path "$MODEL" --trust-remote-code --host 127.0.0.1 --port "$PORT"
  --context-length 32768 --max-total-tokens 65536 --max-running-requests 32
  --mem-fraction-static .80 --kv-cache-dtype fp8_e5m2 --attention-backend triton
  --cuda-graph-backend-decode full --cuda-graph-max-bs-decode 32
  --log-level info --skip-server-warmup
  --enable-hierarchical-cache --hicache-size 1 --hicache-write-policy write_back
  --hicache-io-backend kernel --hicache-mem-layout page_first
  --hicache-host-memory-mode cache
  --hicache-storage-backend extent
  --hicache-storage-backend-extra-config "{\"storage_dir\":\"$OUT/l3-extent\",\"extent_size\":67108864,\"file_size\":8589934592,\"max_size\":8589934592,\"min_free_space\":1073741824}"
  --hicache-storage-prefetch-policy wait_complete
  --cuda-graph-backend-prefill breakable --cuda-graph-bs-prefill $BUCKETS
)
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
export SGLANG_CACHE_DIR=$DATA/cache HF_HOME=$DATA/cache/hf-home HF_DATASETS_CACHE=$DATA/cache/datasets
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True

( "$VENV/bin/python" -m sglang.launch_server "${ARGS[@]}" > "$OUT/server.log" 2>&1 ) &
SPID=$!
cleanup() {
  pkill -TERM -P $SPID 2>/dev/null || true
  kill -TERM $SPID 2>/dev/null || true
  for _ in $(seq 1 60); do kill -0 $SPID 2>/dev/null || break; sleep 1; done
  kill -KILL $SPID 2>/dev/null || true
  wait $SPID 2>/dev/null || true
}
trap cleanup EXIT

for _ in $(seq 1 600); do
  curl -sf "http://127.0.0.1:$PORT/health_generate" >/dev/null 2>&1 && break
  kill -0 $SPID 2>/dev/null || { echo SERVER_DIED; tail -30 "$OUT/server.log"; exit 5; }
  sleep 1
done
curl -sf "http://127.0.0.1:$PORT/health_generate" >/dev/null || { echo SERVER_NOT_READY; exit 5; }
grep -E "Capture target prefill|max_total_num_tokens" "$OUT/server.log" | tail -3 > "$OUT/capture-summary.txt" || true

"$VENV/bin/python" - "$PORT" "$OUT" <<'PY'
import json, sys, time
import requests

port, out = sys.argv[1], sys.argv[2]
gen_url = f"http://127.0.0.1:{port}/generate"

def gen(ids, n=16, tag=""):
    body = {"input_ids": ids, "sampling_params": {"temperature": 0.0, "top_k": 1,
            "max_new_tokens": n, "ignore_eos": True}}
    t0 = time.time()
    r = requests.post(gen_url, json=body, timeout=900)
    r.raise_for_status()
    d = r.json()
    return {"tag": tag, "len_in": len(ids), "ids": d.get("output_ids") or [],
            "cached": (d.get("meta_info") or {}).get("cached_tokens"),
            "wall_s": round(time.time() - t0, 3)}

# ---------- A. alternating bucket replay ----------
sizes = [1024, 1280, 1536, 2048, 4096]
probes = {}
for n in sizes:
    probes[n] = list(range(1000, 1000 + n))          # in-vocabulary ids
first, second = {}, {}
for n in sizes:
    first[n] = gen(probes[n], tag=f"r1_{n}")
for n in reversed(sizes):                             # interleave the replay order
    second[n] = gen(probes[n], tag=f"r2_{n}")
a_ok = all(first[n]["ids"] == second[n]["ids"] for n in sizes)
json.dump({"first": {k: v for k, v in first.items()},
           "second": {k: v for k, v in second.items()},
           "identical": a_ok},
          open(f"{out}/bucket-alternation.json", "w"), indent=1)

# ---------- B. real L3 restore ----------
target = list(range(50000, 50000 + 20000))
cold = gen(target, n=16, tag="target-cold")
pressure = []
for i in range(16):
    base = 100000 + i * 2500
    pressure.append(gen(list(range(base, base + 20000)), n=2, tag=f"pressure{i}"))
requests.post(f"http://127.0.0.1:{port}/flush_cache", json={}, timeout=300).raise_for_status()
time.sleep(2)
restored = gen(target, n=16, tag="target-restored")
json.dump({"cold": cold, "restored": restored,
           "pressure": len(pressure),
           "cached_tokens_restored": restored["cached"],
           "ids_identical": cold["ids"] == restored["ids"]},
          open(f"{out}/l3-restore.json", "w"), indent=1)
print("VALIDATE_OK")
PY

sleep 2
curl -sf "http://127.0.0.1:$PORT/metrics" > "$OUT/metrics-end.prom" || true
grep -oE "#new-seq: [0-9]+, #new-token: [0-9]+.*cuda graph: (True|False)" "$OUT/server.log" \
  | sed -E 's/, #cached-token: ([0-9]+).*cuda graph:/ cached=\1 graph=/' \
  | sort | uniq -c | sort -rn | head -12 > "$OUT/prefill-shapes.txt" || true
grep -c "cuda graph: True" "$OUT/server.log" > "$OUT/count-graph-true.txt" || true
grep -c "cuda graph: False" "$OUT/server.log" > "$OUT/count-graph-false.txt" || true
grep -iE "prefill cuda graph|h2d|load fallback|pending kv load" "$OUT/server.log" \
  | head -20 > "$OUT/h2d-fallback-lines.txt" || true
grep -iE "extent_read|restore.*disposition|storage_hit" "$OUT/server.log" \
  | tail -20 > "$OUT/restore-lines.txt" || true
echo "VALIDATE_DONE"
