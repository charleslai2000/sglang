#!/usr/bin/env bash
set -Eeuo pipefail
ROOT=/home/ubuntu/workspaces/3rdparty/sglang-hicache; VENV=/home/ubuntu/venvs/sglang-3090; DATA=/data/sglang-hicache/gemma4; MODEL=$DATA/model; OUT=${G1_PROD_OUT:?set G1_PROD_OUT}; PORT=${G1_PROD_PORT:-31401}; LOCK=/tmp/f1-r16b-gpu-exclusive.lock; AOT=/data/sglang-hicache/g2-quasar-runs/20261110T-g2-postrope-e5m2-quality/aot-sm86-package; OVERLAY=$ROOT/control/gemma4-w4a16-3090-performance-capacity/runs/overlay
[[ $(sha256sum "$MODEL/model.safetensors"|awk '{print $1}') == 19d89d2a4b3e401a3eae75ec08ab112810421a036c91d8c8226b686be7fe0c5d ]]
[[ $(sha256sum "$AOT/sgl_kernel/sm86/common_ops.abi3.so"|awk '{print $1}') == 22c9f5eb84e5e494df31f814aeffe5ba0aafb266fca2b56c99cfb5a3c1dea4c2 ]]
[[ $(sha256sum "$OVERLAY/sglang/kernels/ops/attention/extend_attention.py"|awk '{print $1}') == 69a9f59d6817b3947feb38639d47c690e82947ead0e9af50a0200f02a4b34d4e ]]
if [[ ${G1_GPU_LOCK_HELD:-0} != 1 ]]; then
  exec 9>"$LOCK"
  flock -n 9 || { echo GPU_LOCK_BUSY >&2; exit 90; }
fi
ss -ltn|grep -q ":$PORT\\b" && { echo PORT_BUSY >&2; exit 91; } || true
mkdir -p "$OUT"; export PYTHONNOUSERSITE=1 PYTHONPATH="$ROOT/control/gemma4-w4a16-3090-performance-capacity/runs:$AOT:$ROOT/python:$VENV/lib/python3.12/site-packages:$ROOT/python/sglang/kernels/aot/python:$OVERLAY" LD_LIBRARY_PATH="$VENV/lib/python3.12/site-packages/torch/lib:/usr/local/cuda-12.9/lib64" SGLANG_CACHE_DIR="$DATA/cache" HF_HOME="$DATA/cache/hf-home" HF_DATASETS_CACHE="$DATA/cache/datasets"; cd "$ROOT"
# The venv has a different editable SGLang checkout. Keep it installed for other
# projects, but fail closed unless this process resolves the service and HiCache
# modules from this one authorized worktree. Record imported file hashes before
# starting the scheduler so the run binds to the checked source, not metadata.
"$VENV/bin/python" - "$ROOT" "$OUT/source-identity.json" <<'PY'
import hashlib, importlib, json, os, subprocess, sys
root = os.path.realpath(sys.argv[1])
modules = (
    "sglang",
    "sglang.launch_server",
    "sglang.srt.managers.scheduler",
    "sglang.srt.managers.scheduler_components.hicache_restore",
    "sglang.srt.mem_cache.unified_cache.unified_tree_core",
    "sglang.srt.mem_cache.unified_radix_cache",
)
loaded = {}
for name in modules:
    module = importlib.import_module(name)
    path = os.path.realpath(module.__file__)
    if not (path == root or path.startswith(root + os.sep)):
        raise SystemExit(f"Refusing runtime module outside authorized worktree: {name}={path}")
    loaded[name] = {"path": path, "sha256": hashlib.sha256(open(path, "rb").read()).hexdigest()}
identity = {
    "project_root": root,
    "git_head": subprocess.check_output(["git", "-C", root, "rev-parse", "HEAD"], text=True).strip(),
    "branch": subprocess.check_output(["git", "-C", root, "branch", "--show-current"], text=True).strip(),
    "python": os.path.realpath(sys.executable),
    "pythonpath": os.environ.get("PYTHONPATH", ""),
    "modules": loaded,
}
with open(sys.argv[2], "w") as stream:
    json.dump(identity, stream, indent=2)
    stream.write("\n")
print(json.dumps(identity, sort_keys=True))
PY
: "${G1_PROD_KV:=fp8_e5m2}"; : "${G1_PROD_CONTEXT:=8192}"; : "${G1_PROD_MAX_RUNNING:=32}"; : "${G1_PROD_MEM_FRACTION:=.94}"; : "${G1_PROD_GRAPH_BS:=32}"; : "${G1_PROD_RADIX:=on}"; : "${G1_PROD_HICACHE:=off}"; : "${G1_PROD_HICACHE_SIZE:=1}"; : "${G1_PROD_L3_DIR:=$OUT/l3-extent}"
ARGS=(--model-path "$MODEL" --trust-remote-code --host 127.0.0.1 --port "$PORT" --context-length "$G1_PROD_CONTEXT" --max-running-requests "$G1_PROD_MAX_RUNNING" --max-total-tokens 262144 --mem-fraction-static "$G1_PROD_MEM_FRACTION" --kv-cache-dtype "$G1_PROD_KV" --attention-backend triton --cuda-graph-backend-decode full --cuda-graph-max-bs-decode "$G1_PROD_GRAPH_BS" --log-level info --enable-metrics)
[[ $G1_PROD_RADIX == on ]] || ARGS+=(--disable-radix-cache)
if [[ ${G1_PROD_WARMUP:-on} == off ]]; then ARGS+=(--skip-server-warmup); fi
if [[ $G1_PROD_HICACHE == on ]]; then
  mkdir -p "$G1_PROD_L3_DIR"
  EXTENT_CONFIG=$(printf '{"storage_dir":"%s","extent_size":67108864,"file_size":4294967296,"max_size":4294967296,"min_free_space":10737418240}' "$G1_PROD_L3_DIR")
  ARGS+=(--enable-hierarchical-cache --hicache-size "$G1_PROD_HICACHE_SIZE" --hicache-storage-backend extent --hicache-storage-backend-extra-config "$EXTENT_CONFIG" --hicache-write-policy write_through --hicache-io-backend kernel --hicache-mem-layout page_first --hicache-host-memory-mode cache --hicache-storage-prefetch-policy wait_complete)
fi
printf '%q ' "${ARGS[@]}" > "$OUT/launch-argv.txt"; printf '\nkv=%s\ncontext=%s\nmax_running=%s\nmem_fraction=%s\ngraph_bs=%s\nradix=%s\nhicache=%s\nhicache_size=%s\nwarmup=%s\nl3_dir=%s\nsource_head=%s\n' "$G1_PROD_KV" "$G1_PROD_CONTEXT" "$G1_PROD_MAX_RUNNING" "$G1_PROD_MEM_FRACTION" "$G1_PROD_GRAPH_BS" "$G1_PROD_RADIX" "$G1_PROD_HICACHE" "$G1_PROD_HICACHE_SIZE" "${G1_PROD_WARMUP:-on}" "$G1_PROD_L3_DIR" "$(git rev-parse HEAD)" > "$OUT/manifest.txt"
export G1_LOGITS_CAPTURE=; "$VENV/bin/python" -m sglang.launch_server "${ARGS[@]}" > "$OUT/server.log" 2>&1 & PID=$!; MON=; GPU_MON=; cleanup(){ set +e; [[ -z ${MON:-} ]] || { kill -TERM "$MON" 2>/dev/null; wait "$MON" 2>/dev/null; }; [[ -z ${GPU_MON:-} ]] || { kill -TERM "$GPU_MON" 2>/dev/null; wait "$GPU_MON" 2>/dev/null; }; [[ -z ${PID:-} ]] || { kill -TERM "$PID" 2>/dev/null; for _ in $(seq 1 60); do kill -0 "$PID" 2>/dev/null || break; sleep 1; done; pkill -TERM -P "$PID" 2>/dev/null; kill -TERM "$PID" 2>/dev/null; wait "$PID" 2>/dev/null; }; nvidia-smi --query-gpu=timestamp,utilization.gpu,memory.used --format=csv,noheader > "$OUT/gpu-after.csv"; ss -ltnp|grep ":$PORT\\b" > "$OUT/port-after.txt" 2>&1 || true; }; trap cleanup EXIT
trap 'exit 0' TERM
trap 'exit 130' INT
watchdog(){ sleep 4200; kill -TERM "$$" 2>/dev/null; }; watchdog & MON=$!; echo "$MON" > "$OUT/watchdog.pid"
ready=0; for _ in $(seq 1 1200); do if curl -fsS "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; then ready=1;break;fi;kill -0 "$PID" 2>/dev/null || { tail -100 "$OUT/server.log"; exit 2; };sleep 1;done;[[ $ready == 1 ]];curl -fsS "http://127.0.0.1:$PORT/model_info" > "$OUT/model-info.json"; echo "$PID" > "$OUT/server.pid"; echo "$MON" > "$OUT/watchdog.pid"; nvidia-smi --query-gpu=timestamp,utilization.gpu,memory.used --format=csv --loop-ms=1000 > "$OUT/gpu-samples.csv" & GPU_MON=$!; echo "$GPU_MON" > "$OUT/gpu-monitor.pid"; wait "$PID"
