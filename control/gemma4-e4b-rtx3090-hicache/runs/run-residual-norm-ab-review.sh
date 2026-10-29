#!/usr/bin/env bash
# Experimental G1 residual/RMSNorm A/B runner. STATUS: NOT VALIDATED.
# Do not use as an acceptance runner until its RID/FID completion checks are reviewed.
set -euo pipefail
repo=/home/ubuntu/workspaces/3rdparty/sglang-hicache
venv=/home/ubuntu/venvs/sglang-3090
model=/data/sglang-hicache/gemma4/model
out=${GEMMA4_AB_OUT:?set GEMMA4_AB_OUT to a fresh external run directory}
ids_file=${GEMMA4_AB_IDS_FILE:?set JSON array file of exact input token IDs}
positions_file=${GEMMA4_AB_POSITIONS_FILE:?set JSON array file of exact positions}
layer_count=${GEMMA4_AB_LAYER_COUNT:-42}
hidden_size=${GEMMA4_AB_HIDDEN_SIZE:-2560}
vocab_size=${GEMMA4_AB_VOCAB_SIZE:-262144}
if [ -e "$out" ]; then echo "refusing non-fresh output directory: $out" >&2; exit 91; fi
mkdir -p "$out"/{A,B,bootstrap}
exec 9>/tmp/f1-r16b-gpu-exclusive.lock
flock -n 9 || { echo 'GPU lock unavailable' >&2; exit 90; }
export PYTHONNOUSERSITE=1
export PYTHONPATH="$out/bootstrap:$repo/control/gemma4-e4b-rt3090-hicache/runs:$repo/python:/data/sglang-hicache/gemma4/aot-sm86-build:$repo/3rdparty/sglang/python/sglang/kernels/aot/python"
export LD_LIBRARY_PATH="$venv/lib/python3.12/site-packages/torch/lib:/usr/local/cuda-12.9/lib64"
export GEMMA4_RUNTIME_HOOK_ENABLE=1
export GEMMA4_RUNTIME_HOOK_PATH="$repo/control/gemma4-e4b-rt3090-hicache/runs"
export GEMMA4_RUNTIME_HOOK_INSTALL="$repo/control/gemma4-e4b-rt3090-hicache/runs/runtime-layer-components.py"
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
cleanup(){ if [ -n "$pid" ]; then kill -TERM "$pid" 2>/dev/null || true; wait "$pid" 2>/dev/null || true; pid=''; fi; }
trap cleanup EXIT INT TERM
for arm in A B; do
    port=31251
    if [ "$arm" = B ]; then
        port=31252
        export SGLANG_GEMMA4_BF16_RESIDUAL_NORM_AB=1
    else
        unset SGLANG_GEMMA4_BF16_RESIDUAL_NORM_AB || true
    fi
    export GEMMA4_COMPONENT_STATE_FILE="$out/$arm/components"
    export SGLANG_GEMMA4_LAYERS_FILE="$out/$arm/layers"
    export SGLANG_GEMMA4_LOGITS_FILE="$out/$arm/layers"
    "$venv/bin/python" -m sglang.launch_server --model-path "$model" --trust-remote-code --host 127.0.0.1 --port "$port" --context-length 1024 --max-running-requests 1 --mem-fraction-static .82 --disable-radix-cache --kv-cache-dtype bf16 --attention-backend triton --cuda-graph-max-bs-decode 1 --skip-server-warmup --log-level info > "$out/$arm/server.log" 2>&1 &
    pid=$!
    for _ in $(seq 1 240); do
        kill -0 "$pid" 2>/dev/null || { echo "$arm server exited" >&2; exit 2; }
        curl -fsS "http://127.0.0.1:$port/health" >/dev/null 2>&1 && break
        sleep 2
    done
    curl -fsS "http://127.0.0.1:$port/health" >/dev/null
    "$venv/bin/python" - "$ids_file" "$out/$arm/request.json" <<'PY'
import json,sys
ids=json.load(open(sys.argv[1]))
json.dump({"input_ids":ids,"sampling_params":{"temperature":0,"max_new_tokens":1,"temperature":0.0,"seed":666360643}},open(sys.argv[2],"w"))
PY
    curl -fsS -H 'Content-Type: application/json' -d @"$out/$arm/request.json" "http://127.0.0.1:$port/generate" > "$out/$arm/response.json"
    rid=$("$venv/bin/python" -c 'import json,sys; print(json.load(open(sys.argv[1]))["meta_info"]["id"])' "$out/$arm/response.json")
    printf '%s\n' "$rid" > "$out/$arm/request-rid.txt"
    selected=$("$venv/bin/python" "$repo/control/gemma4-e4b-rtx3090-hicache/runs/select-bound-forward.py" "$out/$arm/layers" "$rid" --ids "$(cat "$ids_file")" --positions "$(cat "$positions_file")")
    read -r fid offset <<< "$selected"
    printf '%s\n' "$fid" > "$out/$arm/forward-id.txt"
    printf '%s\n' "$offset" > "$out/$arm/input-token-offset.txt"
    "$venv/bin/python" "$repo/control/gemma4-e4b-rtx3090-hicache/runs/verify-forward-capture.py" \
        --base "$out/$arm/layers" --forward-id "$fid" \
        --expected-ids "$(cat "$ids_file")" \
        --expected-positions "$(cat "$positions_file")" --expected-rid "$rid" \
        --model-revision 6cd26aaa2357fb2bad8c51699a7558a4d1a965bb \
        --model-sha256 19d89d2a4b3e401a3eae75ec08ab112810421a036c91d8c8226b686be7fe0c5d \
        --expected-offset "$offset" --expected-layer-count "$layer_count" \
        --expected-hidden-size "$hidden_size" --expected-vocab-size "$vocab_size" \
        --manifest "$out/$arm/verified-capture.json"
    cleanup
done
nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv > "$out/gpu-after.csv"
