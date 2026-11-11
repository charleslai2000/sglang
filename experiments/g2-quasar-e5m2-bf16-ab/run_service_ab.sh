#!/usr/bin/env bash
set -Eeuo pipefail
ROOT=/home/ubuntu/workspaces/3rdparty/sglang-hicache
RUNS=/data/sglang-hicache/g2-quasar-runs
MODEL=/data/models/gemma4-quasar-q4_0/gemma-4-E4B-it-QUASAR-Q4_0.gguf
LOCK=/tmp/f1-r16b-gpu-exclusive.lock
OVERLAY=$RUNS/20261107T-g2-first-logits/head-kernel-shadow
AOT=$RUNS/20261107T-g2-first-logits/aot-sm86-package
TOKENIZER=/data/sglang-hicache/gemma4/model
ARM=${1:?usage: run_service_ab.sh bf16|fp8_e5m2 RUN_DIR PORT [FIXTURE]}
BASE=${2:?RUN_DIR required}
PORT=${3:?PORT required}
FIXTURE=${4:-}
case "$ARM" in
  bf16) KV_DTYPE=bf16 ;;
  fp8_e5m2) KV_DTYPE=fp8_e5m2 ;;
  *) echo "unsupported arm: $ARM" >&2; exit 2 ;;
esac
[[ "$BASE" = "$RUNS"/* ]] || { echo "run directory must be under $RUNS" >&2; exit 2; }
[[ ! -e "$BASE" ]] || { echo "REFUSE_EXISTING_RUN_DIR $BASE" >&2; exit 4; }
[[ -f "$MODEL" && -d "$OVERLAY" && -d "$AOT" ]] || { echo 'required model/overlay/AOT missing' >&2; exit 5; }
mkdir -p "$BASE"
exec 9>"$LOCK"; flock -n 9 || { echo GPU_LOCK_BUSY >&2; exit 90; }
export PYTHONNOUSERSITE=1
export PYTHONPATH="$OVERLAY:$AOT:$ROOT/python:/home/ubuntu/venvs/sglang-3090/lib/python3.12/site-packages:$ROOT/python/sglang/kernels/aot/python"
export SGLANG_ENABLE_JIT_DEEPGEMM=0
OVERLAY_FILE=$OVERLAY/sglang/kernels/ops/attention/extend_attention.py
OVERLAY_SHA=$(sha256sum "$OVERLAY_FILE" | cut -d' ' -f1)
AOT_SHA=$(sha256sum "$AOT/sm86/common_ops.abi3.so" | cut -d' ' -f1)
[[ "$OVERLAY_SHA" = 69a9f59d6817b3947feb38639d47c690e82947ead0e9af50a0200f02a4b34d4e ]]
[[ "$AOT_SHA" = 22c9f5eb84e5e494df31f814aeffe5ba0aafb266fca2b56c99cfb5a3c1dea4c2 ]]
! grep -q BF16_KV_COMPUTE "$OVERLAY_FILE"
python3 - "$OVERLAY_FILE" "$BASE" <<'PY'
import hashlib, subprocess, sys
from pathlib import Path
source, out = map(Path, sys.argv[1:])
blob = subprocess.check_output(['git','hash-object',str(source)],text=True).strip()
head = subprocess.check_output(['git','rev-parse','HEAD:python/sglang/kernels/ops/attention/extend_attention.py'],text=True).strip()
if blob != head:
    raise SystemExit(f'overlay is not current HEAD blob: {blob} != {head}')
(out/'source-identity.txt').write_text(
    f'overlay_path={source}\noverlay_sha256={hashlib.sha256(source.read_bytes()).hexdigest()}\n'
    f'overlay_git_blob={blob}\nhead_git_blob={head}\n'
    f'worktree_sha256={hashlib.sha256(Path("python/sglang/kernels/ops/attention/extend_attention.py").read_bytes()).hexdigest()}\n'
    f'aot_binary_sha256=22c9f5eb84e5e494df31f814aeffe5ba0aafb266fca2b56c99cfb5a3c1dea4c2\n')
PY
cat > "$BASE/manifest.txt" <<EOF
arm=$ARM
model_sha256=7d6269096c9acbce4422fd1aa3a249436b01288868961e48ca9bb2541997f669
kv_cache_dtype=$KV_DTYPE
compute_dtype=bfloat16
context_length=8192
chunked_prefill_size=2048
attention_backend=triton
cuda_graph_prefill=false
cuda_graph_decode=false
radix_cache=false
max_running_requests=16
tp_size=1
mem_fraction_static=0.88
workload=64 random token IDs; 32 forced output tokens; c1/c4/c16; 1 warmup + 3 measured waves each
seed_server=666360643
head_kernel_overlay_sha256=$OVERLAY_SHA
aot_common_ops_abi3_sha256=$AOT_SHA
EOF
sha256sum "$MODEL" > "$BASE/model-sha256.txt"
if [[ -n "$FIXTURE" ]]; then
  [[ -f "$FIXTURE" ]] || { echo "fixture missing: $FIXTURE" >&2; exit 6; }
  mkdir -p "$BASE/perf"
  cp "$FIXTURE" "$BASE/perf/fixture.json"
  FIXTURE_ARG=(--fixture "$BASE/perf/fixture.json")
else
  FIXTURE_ARG=()
fi
SERVER_PID=''
cleanup(){
 set +e
 if [[ -n "$SERVER_PID" ]] && kill -0 "$SERVER_PID" 2>/dev/null; then
  kill -TERM -- "-$SERVER_PID" 2>/dev/null || kill -TERM "$SERVER_PID" 2>/dev/null
  for _ in $(seq 1 90); do kill -0 "$SERVER_PID" 2>/dev/null || break; sleep 1; done
  kill -KILL -- "-$SERVER_PID" 2>/dev/null || true
  wait "$SERVER_PID" 2>/dev/null || true
 fi
 if ss -ltnp | grep -q ":${PORT}\\b"; then echo "PORT_REMAINS $PORT" > "$BASE/cleanup-warning.txt"; fi
 nvidia-smi --query-gpu=timestamp,utilization.gpu,memory.used --format=csv,noheader > "$BASE/gpu-after.csv"
}
trap cleanup EXIT INT TERM
/home/ubuntu/venvs/sglang-3090/bin/python - <<'PY'
from pathlib import Path
import sglang.kernels.ops.attention.extend_attention as e
expected='/data/sglang-hicache/g2-quasar-runs/20261107T-g2-first-logits/head-kernel-shadow/'
assert str(e.__file__).startswith(expected), e.__file__
assert 'BF16_KV_COMPUTE' not in Path(e.__file__).read_text()
print('HEAD_KERNEL_OVERLAY', e.__file__)
PY
(cd /tmp && setsid /home/ubuntu/venvs/sglang-3090/bin/python -m sglang.launch_server \
 --model-path "$MODEL" --tokenizer-path "$TOKENIZER" --load-format gguf --quantization gguf \
 --dtype bfloat16 --kv-cache-dtype "$KV_DTYPE" --context-length 8192 --mem-fraction-static 0.88 \
 --chunked-prefill-size 2048 --attention-backend triton --disable-prefill-cuda-graph \
 --disable-decode-cuda-graph --disable-radix-cache --max-running-requests 16 \
 --host 127.0.0.1 --port "$PORT" --random-seed 666360643 --log-level info) > "$BASE/server.log" 2>&1 &
SERVER_PID=$!; echo "$SERVER_PID" > "$BASE/server.pid"
ready=0
for _ in $(seq 1 900); do
 if curl -fsS "http://127.0.0.1:$PORT/model_info" > "$BASE/model-info.json" 2>/dev/null; then ready=1; break; fi
 if ! kill -0 "$SERVER_PID" 2>/dev/null; then tail -120 "$BASE/server.log"; exit 2; fi
 sleep 1
done
[[ "$ready" == 1 ]] || { echo SERVER_READY_TIMEOUT >&2; tail -120 "$BASE/server.log"; exit 3; }
python3 - "$BASE" <<'PY'
import sys
from pathlib import Path
p=Path(sys.argv[1]); lines=p.joinpath('server.log').read_text(errors='replace').splitlines()
(p/'pool-capacity.txt').write_text('\n'.join(x for x in lines if 'KV Cache is allocated' in x or 'max_total_num_tokens=' in x)+'\n')
PY
if [[ -n "$FIXTURE" ]]; then
  /home/ubuntu/venvs/sglang-3090/bin/python "$ROOT/experiments/g2-quasar-e5m2-bf16-ab/service_ab.py" \
   --url "http://127.0.0.1:$PORT/generate" --arm "$ARM" --out "$BASE/perf" "${FIXTURE_ARG[@]}" | tee "$BASE/driver.log"
else
  /home/ubuntu/venvs/sglang-3090/bin/python "$ROOT/experiments/g2-quasar-e5m2-bf16-ab/service_ab.py" \
   --url "http://127.0.0.1:$PORT/generate" --arm "$ARM" --out "$BASE/perf" | tee "$BASE/driver.log"
fi
sha256sum "$BASE"/{manifest.txt,source-identity.txt,model-sha256.txt,model-info.json,pool-capacity.txt,server.log,perf/fixture.json,perf/raw.jsonl,perf/summary.json} > "$BASE/artifact-sha256.txt"
cat "$BASE/perf/summary.json"
