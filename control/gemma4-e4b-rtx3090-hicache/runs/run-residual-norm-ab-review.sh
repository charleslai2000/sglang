#!/usr/bin/env bash
# Experimental G1 residual/RMSNorm A/B runner. STATUS: NOT VALIDATED.
# Do not use as an acceptance runner until its RID/FID completion checks are reviewed.
set -euo pipefail
repo=/home/ubuntu/workspaces/3rdparty/sglang-hicache
venv=/home/ubuntu/venvs/sglang-3090
model=/data/sglang-hicache/gemma4/model
model_sha256=19d89d2a4b3e401a3eae75ec08ab112810421a036c91d8c8226b686be7fe0c5d
actual_model_sha256=$(sha256sum "$model/model.safetensors" | awk '{print $1}')
if [ "$actual_model_sha256" != "$model_sha256" ]; then echo "model SHA mismatch: $actual_model_sha256" >&2; exit 93; fi
hook=$repo/control/gemma4-e4b-rt3090-hicache/runs/runtime-layer-components.py
if [ ! -f "$hook" ]; then echo "missing required capture hook: $hook" >&2; exit 92; fi
out=${GEMMA4_AB_OUT:?set GEMMA4_AB_OUT to a fresh external run directory}
ids_file=${GEMMA4_AB_IDS_FILE:?set JSON array file of exact input token IDs}
positions_file=${GEMMA4_AB_POSITIONS_FILE:?set JSON array file of exact positions}
layer_count=42
hidden_size=2560
vocab_size=262144
context_length=1024
if [ "$("$venv/bin/python" - "$ids_file" <<'PY'
import json,sys
print(len(json.load(open(sys.argv[1]))))
PY
)" -gt "$context_length" ]; then echo 'input exceeds runner context length' >&2; exit 94; fi
if [ -e "$out" ]; then echo "refusing non-fresh output directory: $out" >&2; exit 91; fi
mkdir -p "$out"/{A,B,bootstrap}
exec 9>/tmp/f1-r16b-gpu-exclusive.lock
flock -n 9 || { echo 'GPU lock unavailable' >&2; exit 90; }
export PYTHONNOUSERSITE=1
export PYTHONPATH="$out/bootstrap:$repo/control/gemma4-e4b-rt3090-hicache/runs:$repo/python:/data/sglang-hicache/gemma4/aot-sm86-build:$repo/3rdparty/sglang/python/sglang/kernels/aot/python${PYTHONPATH:+:$PYTHONPATH}"
export LD_LIBRARY_PATH="$venv/lib/python3.12/site-packages/torch/lib:/usr/local/cuda-12.9/lib64${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export SGLANG_CACHE_DIR=/data/sglang-hicache/gemma4/cache HF_HOME=/data/sglang-hicache/gemma4/hf-home
export GEMMA4_RUNTIME_HOOK_ENABLE=1
export GEMMA4_RUNTIME_HOOK_PATH="$repo/control/gemma4-e4b-rt3090-hicache/runs"
export GEMMA4_RUNTIME_HOOK_INSTALL="$hook"
export GEMMA4_COMPONENT_LAYERS=$(seq -s, 0 41) GEMMA4_CAPTURE_ALL_LAYER_OUTPUTS=1
export GEMMA4_MODEL_IDENTITY='{"model_revision":"6cd26aaa2357fb2bad8c51699a7558a4d1a965bb","model_sha256":"19d89d2a4b3e401a3eae75ec08ab112810421a036c91d8c8226b686be7fe0c5d"}'
export GEMMA4_MODEL_SHA256=19d89d2a4b3e401a3eae75ec08ab112810421a036c91d8c8226b686be7fe0c5d
export SGLANG_GEMMA4_CAPTURE_LAYERS=1 SGLANG_GEMMA4_CAPTURE_LOGITS=1
cat > "$out/bootstrap/sitecustomize.py" <<'PY'
import os, runpy
if os.getenv('GEMMA4_RUNTIME_HOOK_ENABLE') == '1':
    runpy.run_path(os.environ['GEMMA4_RUNTIME_HOOK_INSTALL'], run_name='__gemma4_runtime_hooks__')
PY
pid=''
cleanup(){ if [ -n "$pid" ]; then kill -TERM "$pid" 2>/dev/null || true; for _ in $(seq 1 30); do kill -0 "$pid" 2>/dev/null || break; sleep 1; done; pkill -TERM -P "$pid" 2>/dev/null || true; wait "$pid" 2>/dev/null || true; pid=''; fi; }
trap cleanup EXIT INT TERM
for arm in A B; do
    arm_pid_file="$out/$arm/server.pid"
    port=31251
    if [ "$arm" = B ]; then
        port=31252
        export SGLANG_GEMMA4_BF16_RESIDUAL_NORM_AB=1
    else
        unset SGLANG_GEMMA4_BF16_RESIDUAL_NORM_AB || true
    fi
    export GEMMA4_COMPONENT_STATE_FILE="$out/$arm/components"
    export SGLANG_GEMMA4_LAYERS_FILE="$out/$arm/layers"
    export GEMMA4_CAPTURE_MANIFEST="$out/$arm/expected-model.json"
    printf '%s\n' '{"model_revision":"6cd26aaa2357fb2bad8c51699a7558a4d1a965bb","model_sha256":"19d89d2a4b3e401a3eae75ec08ab112810421a036c91d8c8226b686be7fe0c5d"}' > "$GEMMA4_CAPTURE_MANIFEST"
    export SGLANG_GEMMA4_LOGITS_FILE="$out/$arm/layers"
    "$venv/bin/python" -m sglang.launch_server --model-path "$model" --trust-remote-code --host 127.0.0.1 --port "$port" --context-length "$context_length" --max-running-requests 1 --mem-fraction-static .82 --disable-radix-cache --kv-cache-dtype bf16 --attention-backend triton --cuda-graph-max-bs-decode 1 --skip-server-warmup --log-level info > "$out/$arm/server.log" 2>&1 &
    pid=$!
    printf '%s\n' "$pid" > "$arm_pid_file"
    ready=0
    for _ in $(seq 1 240); do
        kill -0 "$pid" 2>/dev/null || { echo "$arm server exited" >&2; exit 2; }
        if curl -fsS "http://127.0.0.1:$port/health" >/dev/null 2>&1; then ready=1; break; fi
        sleep 2
    done
    if [ "$ready" != 1 ]; then echo "$arm health timeout" >&2; exit 3; fi
    curl -fsS "http://127.0.0.1:$port/health" >/dev/null
    "$venv/bin/python" - "$ids_file" "$positions_file" "$out/$arm/request.json" <<'PY'
import json,sys
ids=json.load(open(sys.argv[1]));positions=json.load(open(sys.argv[2]))
if not ids or len(ids)!=len(positions) or positions!=list(range(1,len(ids)+1)):
    raise SystemExit('Gemma4 service runner requires exact text positions 1..N')
json.dump({"input_ids":ids,"sampling_params":{"temperature":0,"max_new_tokens":1}},open(sys.argv[3],"w"))
PY
    if ! curl -fsS --retry 3 --retry-delay 2 -H 'Content-Type: application/json' -d @"$out/$arm/request.json" "http://127.0.0.1:$port/generate" > "$out/$arm/response.json"; then echo "$arm generate failed; preserving server and artifacts" >&2; exit 6; fi
    rid=$("$venv/bin/python" -c 'import json,sys; x=json.load(open(sys.argv[1])); print(x["meta_info"]["id"])' "$out/$arm/response.json")
    if [ -z "$rid" ]; then echo "$arm request RID missing" >&2; exit 4; fi
    printf '%s\n' "$rid" > "$out/$arm/request-rid.txt"
    selected=$("$venv/bin/python" "$repo/control/gemma4-e4b-rtx3090-hicache/runs/select-bound-forward.py" "$out/$arm/layers" "$rid" --ids "$(cat "$ids_file")" --positions "$(cat "$positions_file")")
    if [ "$(wc -l <<< "$selected")" -ne 1 ]; then echo "$arm Forward selection malformed" >&2; exit 5; fi
    read -r fid offset <<< "$selected"
    if [ -z "$fid" ] || [ -z "$offset" ]; then echo "$arm Forward selection incomplete" >&2; exit 5; fi
    printf '%s\n' "$fid" > "$out/$arm/forward-id.txt"
    printf '%s\n' "$offset" > "$out/$arm/input-token-offset.txt"
    "$venv/bin/python" "$repo/control/gemma4-e4b-rtx3090-hicache/runs/verify-forward-capture.py" \
        --base "$out/$arm/layers" --forward-id "$fid" \
        --expected-ids "$(cat "$ids_file")" \
        --expected-positions "$(cat "$positions_file")" --expected-rid "$rid" \
        --model-revision 6cd26aaa2357fb2bad8c51699a7558a4d1a965bb \
        --model-sha256 "$model_sha256" \
        --expected-offset "$offset" --expected-layer-count "$layer_count" \
        --expected-hidden-size "$hidden_size" --expected-vocab-size "$vocab_size" \
        --manifest "$out/$arm/verified-capture.json"
    if [ "$arm" = B ]; then printf '1\n' > "$out/$arm/residual-ab-enabled.txt"; else printf '0\n' > "$out/$arm/residual-ab-enabled.txt"; fi
    cleanup
done
nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv > "$out/gpu-after.csv"
for port in 31251 31252; do
    if fuser -n tcp "$port" >/dev/null 2>&1; then echo "port $port remains occupied after cleanup" >&2; exit 7; fi
done
if [ "$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | head -1 | tr -d ' ')" -gt 100 ]; then echo 'GPU memory remains allocated after cleanup' >&2; exit 8; fi
