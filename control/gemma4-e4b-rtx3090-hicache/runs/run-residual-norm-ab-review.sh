#!/usr/bin/env bash
# Experimental G1 residual/RMSNorm A/B runner. STATUS: NOT VALIDATED.
set -euo pipefail
repo=/home/ubuntu/workspaces/3rdparty/sglang-hicache
venv=/home/ubuntu/venvs/sglang-3090
model=/data/sglang-hicache/gemma4/model
model_sha256=19d89d2a4b3e401a3eae75ec08ab112810421a036c91d8c8226b686be7fe0c5d
hook=$repo/control/gemma4-e4b-rt3090-hicache/runs/runtime-layer-components.py
[[ -f "$hook" ]] || { echo "missing capture hook $hook" >&2; exit 92; }
[[ $(sha256sum "$model/model.safetensors" | awk '{print $1}') == "$model_sha256" ]] || { echo 'model SHA mismatch' >&2; exit 93; }
out=${GEMMA4_AB_OUT:?set GEMMA4_AB_OUT to a fresh run directory}
ids_file=${GEMMA4_AB_IDS_FILE:?set exact token IDs JSON file}
positions_file=${GEMMA4_AB_POSITIONS_FILE:?set exact positions JSON file}
context_length=1024
read -r input_len first_pos last_pos < <("$venv/bin/python" - "$ids_file" "$positions_file" <<'PY'
import json,sys
ids=json.load(open(sys.argv[1]));pos=json.load(open(sys.argv[2]))
if not ids or len(ids)!=len(pos) or pos!=list(range(1,len(ids)+1)):raise SystemExit('expected exact text positions 1..N')
print(len(ids),pos[0],pos[-1])
PY
)
(( input_len <= context_length )) || { echo 'input exceeds runner context' >&2; exit 94; }
[[ ! -e "$out" ]] || { echo "refusing non-fresh output directory: $out" >&2; exit 91; }
mkdir -p "$out"/{A,B,bootstrap}
exec 9>/tmp/f1-r16b-gpu-exclusive.lock
flock -n 9 || { echo 'GPU lock unavailable' >&2; exit 90; }
export PYTHONNOUSERSITE=1
export PYTHONPATH="$out/bootstrap:$repo/control/gemma4-e4b-rt3090-hicache/runs:$repo/python:/data/sglang-hicache/gemma4/aot-sm86-build:$repo/3rdparty/sglang/python/sglang/kernels/aot/python${PYTHONPATH:+:$PYTHONPATH}"
export LD_LIBRARY_PATH="$venv/lib/python3.12/site-packages/torch/lib:/usr/local/cuda-12.9/lib64${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export SGLANG_CACHE_DIR=/data/sglang-hicache/gemma4/cache HF_HOME=/data/sglang-hicache/gemma4/hf-home
export GEMMA4_RUNTIME_HOOK_ENABLE=1 GEMMA4_RUNTIME_HOOK_PATH="$repo/control/gemma4-e4b-rt3090-hicache/runs" GEMMA4_RUNTIME_HOOK_INSTALL="$hook"
export GEMMA4_MODEL_IDENTITY='{"model_revision":"6cd26aaa2357fb2bad8c51699a7558a4d1a965bb","model_sha256":"19d89d2a4b3e401a3eae75ec08ab112810421a036c91d8c8226b686be7fe0c5d"}' GEMMA4_MODEL_SHA256="$model_sha256"
export SGLANG_GEMMA4_CAPTURE_LAYERS=1 SGLANG_GEMMA4_CAPTURE_LOGITS=1
cat > "$out/bootstrap/sitecustomize.py" <<'PY'
import os,runpy
if os.getenv('GEMMA4_RUNTIME_HOOK_ENABLE')=='1':
    runpy.run_path(os.environ['GEMMA4_RUNTIME_HOOK_INSTALL'],run_name='__gemma4_runtime_hooks__')
PY
pid=''
cleanup(){
  [[ -n "$pid" ]] || return 0
  kill -TERM "$pid" 2>/dev/null || true
  for _ in $(seq 1 30); do kill -0 "$pid" 2>/dev/null || break; sleep 1; done
  if kill -0 "$pid" 2>/dev/null; then
    pkill -TERM -P "$pid" 2>/dev/null || true
    kill -KILL "$pid" 2>/dev/null || true
  fi
  wait "$pid" 2>/dev/null || true
  pid=''
}
on_error(){ local rc=$?; printf 'RUNNER_FAILURE line=%s exit=%s command=%q\n' "${BASH_LINENO[0]:-unknown}" "$rc" "$BASH_COMMAND" | tee -a "$out/runner-failure.log" >&2; cleanup; exit "$rc"; }
trap on_error ERR
trap cleanup EXIT INT TERM
for arm in A B; do
  port=31251; enabled=0
  if [[ $arm == B ]]; then port=31252; enabled=1; export SGLANG_GEMMA4_BF16_RESIDUAL_NORM_AB=1; else unset SGLANG_GEMMA4_BF16_RESIDUAL_NORM_AB || true; fi
  export GEMMA4_COMPONENT_STATE_FILE="$out/$arm/components" GEMMA4_COMPONENT_LAYERS=17 GEMMA4_CAPTURE_ALL_LAYER_OUTPUTS=0
  export SGLANG_GEMMA4_LAYERS_FILE="$out/$arm/layers" SGLANG_GEMMA4_LOGITS_FILE="$out/$arm/layers"
  "$venv/bin/python" -m sglang.launch_server --model-path "$model" --trust-remote-code --host 127.0.0.1 --port "$port" --context-length "$context_length" --max-running-requests 1 --mem-fraction-static .82 --disable-radix-cache --disable-cuda-graph --disable-overlap-schedule --watchdog-timeout 1800 --kv-cache-dtype bf16 --attention-backend triton --skip-server-warmup --log-level info > "$out/$arm/server.log" 2>&1 &
  pid=$!; printf '%s\n' "$pid" > "$out/$arm/server.pid"; ready=0
  for _ in $(seq 1 240); do kill -0 "$pid" 2>/dev/null || { echo "$arm server exited" >&2; exit 2; }; if curl -fsS "http://127.0.0.1:$port/health" >/dev/null 2>&1; then ready=1; break; fi; sleep 2; done
  [[ $ready == 1 ]] || { echo "$arm health timeout" >&2; exit 3; }
  "$venv/bin/python" - "$ids_file" "$out/$arm/request.json" <<'PY'
import json,sys
json.dump({'input_ids':json.load(open(sys.argv[1])),'sampling_params':{'temperature':0,'max_new_tokens':1}},open(sys.argv[2],'w'))
PY
  curl -fsS --max-time 1800 -H 'Content-Type: application/json' -d @"$out/$arm/request.json" "http://127.0.0.1:$port/generate" > "$out/$arm/response.json" || { echo "$arm generate failed" >&2; exit 6; }
  rid=$("$venv/bin/python" -c 'import json,sys;print(json.load(open(sys.argv[1]))["meta_info"]["id"])' "$out/$arm/response.json"); [[ -n $rid ]] || exit 4
  printf '%s\n' "$rid" > "$out/$arm/request-rid.txt"
  selected=$("$venv/bin/python" "$repo/control/gemma4-e4b-rtx3090-hicache/runs/select-bound-forward.py" "$out/$arm/layers" "$rid" --ids "$(cat "$ids_file")" --positions "$(cat "$positions_file")")
  read -r fid offset <<< "$selected"; [[ -n $fid && -n $offset ]] || { echo "$arm Forward selection failed" >&2; exit 5; }
  printf '%s\n' "$fid" > "$out/$arm/forward-id.txt"; printf '%s\n' "$offset" > "$out/$arm/input-token-offset.txt"
  "$venv/bin/python" "$repo/control/gemma4-e4b-rtx3090-hicache/runs/verify-forward-capture.py" --base "$out/$arm/layers" --forward-id "$fid" --expected-ids "$(cat "$ids_file")" --expected-positions "$(cat "$positions_file")" --expected-rid "$rid" --model-revision 6cd26aaa2357fb2bad8c51699a7558a4d1a965bb --model-sha256 "$model_sha256" --expected-offset "$offset" --allow-ple --manifest "$out/$arm/verified-capture.json"
  printf '%s\n' "$enabled" > "$out/$arm/residual-ab-enabled.txt"
  cleanup
  if kill -0 "$pid" 2>/dev/null; then echo "$arm service survived cleanup" >&2; exit 10; fi
  pid=''
  child_pids=$(pgrep -P "$(cat "$out/$arm/server.pid")" || true)
  [[ -z "$child_pids" ]] || { echo "$arm server children remain: $child_pids" >&2; exit 11; }
done
nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv > "$out/gpu-after.csv"
for port in 31251 31252; do fuser -n tcp "$port" >/dev/null 2>&1 && { echo "port $port remains occupied" >&2; exit 7; }; done
(( $(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | head -1 | tr -d ' ') <= 100 )) || { echo 'GPU memory remains allocated' >&2; exit 8; }
