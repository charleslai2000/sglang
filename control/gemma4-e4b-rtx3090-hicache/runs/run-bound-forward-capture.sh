#!/usr/bin/env bash
set -euo pipefail
repo=/home/ubuntu/workspaces/3rdparty/sglang-hicache
venv=/home/ubuntu/venvs/sglang-3090
model=/data/sglang-hicache/gemma4/model
root=/data/sglang-hicache/gemma4/runs
run_id="$(date -u +%Y%m%dT%H%M%SZ)-forward-binding-v20"
out="$root/$run_id"
exec 9>/tmp/f1-r16b-gpu-exclusive.lock
flock -n 9 || { echo 'GPU lock unavailable' >&2; exit 90; }
mkdir -p "$out"
export PYTHONPATH="$repo/python:/data/sglang-hicache/gemma4/aot-sm86-build:$repo/3rdparty/sglang/python/sglang/kernels/aot/python${PYTHONPATH:+:$PYTHONPATH}"
export LD_LIBRARY_PATH="$venv/lib/python3.12/site-packages/torch/lib:/usr/local/cuda-12.9/lib64${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export SGLANG_GEMMA4_CAPTURE_LAYERS=1
export GEMMA4_MODEL_IDENTITY='{"model_revision":"6cd26aaa2357fb2bad8c51699a7558a4d1a965bb","model_sha256":"19d89d2a4b3e401a3eae75ec08ab112810421a036c91d8c8226b686be7fe0c5d"}'
export GEMMA4_MODEL_SHA256=19d89d2a4b3e401a3eae75ec08ab112810421a036c91d8c8226b686be7fe0c5d
export SGLANG_GEMMA4_LAYERS_FILE="$out/forward"
export SGLANG_GEMMA4_CAPTURE_LOGITS=1
export SGLANG_GEMMA4_LOGITS_FILE="$out/forward"
export SGLANG_CACHE_DIR=/data/sglang-hicache/gemma4/cache
export HF_HOME=/data/sglang-hicache/gemma4/hf-home
export GEMMA4_CAPTURE_RUN_OUT="$out"
printf '%s\n' "$run_id" > "$out/run-id"
git -C "$repo" diff --binary -- python/sglang/srt/models/gemma4_causal.py python/sglang/srt/layers/logits_processor.py python/sglang/srt/model_executor/forward_batch_info.py python/sglang/srt/utils/gemma4_capture.py | sha256sum > "$out/scoped-diff.sha256"
sha256sum "$model/model.safetensors" > "$out/model.sha256"
"$venv/bin/python" "$repo/control/gemma4-e4b-rtx3090-hicache/runs/audit-oracle.py" "$out/oracle-audit.json" > "$out/oracle-audit.stdout"
git -C "$repo" rev-parse HEAD > "$out/source-head"
(
 cd "$repo"
 "$venv/bin/python" -m sglang.launch_server --model-path "$model" --trust-remote-code --host 127.0.0.1 --port 31037 --context-length 1024 --max-running-requests 1 --max-total-tokens 1024 --mem-fraction-static .82 --kv-cache-dtype bf16 --attention-backend triton --cuda-graph-max-bs-decode 1 --log-level info
) > "$out/server.log" 2>&1 &
server_pid=$!; echo "$server_pid" > "$out/server.pid"
cleanup(){ kill -TERM "$server_pid" 2>/dev/null || true; wait "$server_pid" 2>/dev/null || true; }
trap cleanup EXIT
for _ in $(seq 1 240); do curl -fsS http://127.0.0.1:31037/health >/dev/null 2>&1 && break; kill -0 "$server_pid" 2>/dev/null || { echo 'server exited'; exit 2; }; sleep 5; done
curl -fsS http://127.0.0.1:31037/health >/dev/null
printf '{"input_ids":[6974,886,2822,13315,1003,506,7217,236761],"sampling_params":{"temperature":0,"max_new_tokens":1}}' > "$out/request.json"
curl -fsS -H 'Content-Type: application/json' -d @"$out/request.json" http://127.0.0.1:31037/generate > "$out/response.json"
"$venv/bin/python" - "$out/response.json" > "$out/request-rid.txt" <<'PY'
import json,sys
print(json.load(open(sys.argv[1]))['meta_info']['id'])
PY
"$venv/bin/python" "$repo/control/gemma4-e4b-rtx3090-hicache/runs/select-bound-forward.py" "$out/forward" "$(cat "$out/request-rid.txt")" > "$out/forward-id.txt"
read -r forward_id input_offset < "$out/forward-id.txt"
printf '%s\n' "$input_offset" > "$out/input-token-offset.txt"
"$venv/bin/python" "$repo/control/gemma4-e4b-rtx3090-hicache/runs/verify-forward-capture.py" --base "$out/forward" --forward-id "$forward_id" --expected-ids '[6974,886,2822,13315,1003,506,7217,236761]' --expected-positions '[1,2,3,4,5,6,7,8]' --expected-rid "$(cat "$out/request-rid.txt")" --expected-offset "$input_offset" --model-revision 6cd26aaa2357fb2bad8c51699a7558a4d1a965bb --model-sha256 19d89d2a4b3e401a3eae75ec08ab112810421a036c91d8c8226b686be7fe0c5d --manifest "$out/verified-capture.json" > "$out/capture-verification.json"
"$venv/bin/python" "$repo/control/gemma4-e4b-rtx3090-hicache/runs/analyze-bound-forward.py" "$out/forward" "$forward_id" "$(cat "$out/request-rid.txt")" "$input_offset" /data/sglang-hicache/gemma4/runs/targeted-bf16-logits-fixed-same-run/oracle-positions-1-8-all-layers.pt "$out/numerical-analysis.json" > "$out/numerical-summary.json"
printf '{"status":"COMPLETE","exit_code":0}\n' > "$out/run-status.json"
"$venv/bin/python" - "$out" <<'PY'
import hashlib,json,sys
from pathlib import Path
p=Path(sys.argv[1]); r={'run_id':p.name}
for name in ['oracle-audit.json','oracle-audit.stdout','model.sha256','source-head','scoped-diff.sha256','server.log','request.json','response.json','request-rid.txt','forward-id.txt','input-token-offset.txt','capture-verification.json','verified-capture.json','numerical-analysis.json','numerical-summary.json','run-status.json']:
 r[name]=hashlib.sha256((p/name).read_bytes()).hexdigest()
(p/'run-manifest.json').write_text(json.dumps(r,indent=2)+'\n')
PY
