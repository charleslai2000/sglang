#!/usr/bin/env bash
# T013 engagement check: prove the restored FA2 path runs in a real service and
# read its own coverage counters (plans, budget skips, prefix bytes, owners).
set -Eeuo pipefail
ROOT=/home/ubuntu/workspaces/3rdparty/sglang-hicache
VENV=/home/ubuntu/venvs/sglang-3090
OUT=$(cd "$(dirname "$0")" && pwd)/engage
MODEL=/data/sglang-hicache/gemma4/model
AOT=/data/sglang-hicache/g2-quasar-runs/20261110T-g2-postrope-e5m2-quality/aot-sm86-package
OVERLAY=$ROOT/control/gemma4-w4a16-3090-performance-capacity/runs/overlay
L1ONLY_ARGV=/data/sglang-hicache/gemma4/runs/20261127T-t011-l1only-off2/launch-argv.txt
PORT=31414

exec 9>/tmp/f1-r16b-gpu-exclusive.lock
flock -n 9 || { echo LOCK_BUSY; exit 90; }
if ss -ltn | grep -q ":$PORT\\b"; then echo PORT_BUSY; exit 91; fi

export PYTHONNOUSERSITE=1 SGLANG_GEMMA4_SWA_POOL_TOKENS=65536
export PYTHONPATH="$AOT:$ROOT/python:$VENV/lib/python3.12/site-packages:$ROOT/python/sglang/kernels/aot/python:$OVERLAY"
export LD_LIBRARY_PATH="$VENV/lib/python3.12/site-packages/torch/lib:/usr/local/cuda-12.9/lib64"
export SGLANG_CACHE_DIR=/data/sglang-hicache/gemma4/cache HF_HOME=/data/sglang-hicache/gemma4/cache/hf-home
export SGLANG_HUMMING_USE_F16_ACCUM=0 SGLANG_CTWNA16_HUMMING=1
export SGLANG_FA2_RAGGED_EXTEND=1 SGLANG_T011_BF16_PREFIX_BUDGET_MB=128
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True

mkdir -p "$OUT"
mapfile -t ARGS < <(
  "$VENV/bin/python" - "$L1ONLY_ARGV" "$MODEL" "$PORT" <<'PY'
import json, shlex, sys
argv = shlex.split(open(sys.argv[1]).read())
model, port = sys.argv[2], sys.argv[3]
drop_with_value = {"--port", "--model-path", "--export-metrics-to-file-dir"}
drop_flag = {"--enable-metrics", "--export-metrics-to-file"}
out, i = [], 0
while i < len(argv):
    if argv[i] in drop_with_value:
        i += 2; continue
    if argv[i] in drop_flag:
        i += 1; continue
    out.append(argv[i]); i += 1
out += ["--model-path", model, "--host", "127.0.0.1", "--port", port]
print("\n".join(out))
PY
)
export SGLANG_T011_BF16_TIMING_PATH="$OUT/ragged-coverage.json"
export SGLANG_T011_BF16_TIMING_STRIDE=8

"$VENV/bin/python" -u -m sglang.launch_server "${ARGS[@]}" > "$OUT/server.log" 2>&1 &
PID=$!
for _ in $(seq 1 30); do
  kill -0 "$PID" 2>/dev/null || break
  if [[ -r /proc/$PID/environ ]]; then
    tr '\0' '\n' < "/proc/$PID/environ" | grep -E "SGLANG_(FA2_RAGGED|CTWNA16|T011)" > "$OUT/launcher-env.txt" || true
    break
  fi
  sleep 1
done
if ! kill -0 "$PID" 2>/dev/null; then
  echo "SERVER_DIED" >&2; tail -5 "$OUT/server.log" >&2; exit 3
fi
"$VENV/bin/python" - "$PORT" "$OUT" <<'PY'
import json, sys, time
import requests

port, out = int(sys.argv[1]), sys.argv[2]
session = requests.Session(); session.trust_env = False
base = f"http://127.0.0.1:{port}"
for _ in range(900):
    try:
        if session.get(base + "/health", timeout=2).status_code == 200:
            break
    except requests.RequestException:
        pass
    time.sleep(2)
else:
    raise SystemExit("server unhealthy")

filler = ("The plan is built once per forward from host lengths, then every Full "
          "layer reuses it without re-planning.\n")
tokens = 0
for index in range(350):
    text = f"{index:03d} " + filler * 60
    for _ in range(2):  # second pass reuses the radix prefix, which the FA2 path needs
        body = {"text": text, "sampling_params": {"temperature": 0.0, "max_new_tokens": 4,
                                                  "ignore_eos": True}}
        response = session.post(base + "/generate", json=body, timeout=300)
        response.raise_for_status()
        tokens += response.json().get("meta_info", {}).get("prompt_tokens") or 0
print(json.dumps({"requests": 700, "prompt_tokens": tokens}, indent=2))
PY
kill -INT "$PID" 2>/dev/null || true
for _ in $(seq 1 120); do kill -0 "$PID" 2>/dev/null || break; sleep 1; done
kill -KILL "$PID" 2>/dev/null || true
pkill -TERM -f "sglang.srt.managers.scheduler .*--port $PORT" 2>/dev/null || true
sleep 2

"$VENV/bin/python" - "$OUT" <<'PY'
import json, os, sys
out = sys.argv[1]
payload = {"launcher_env": open(os.path.join(out, "launcher-env.txt")).read().strip().splitlines()}
path = os.path.join(out, "ragged-coverage.json")
payload["coverage_file"] = os.path.exists(path)
if payload["coverage_file"]:
    payload["coverage"] = json.load(open(path))
payload["verdict"] = "PASS" if payload["coverage_file"] and payload["coverage"]["coverage"]["plans"] > 0 else "FAIL"
json.dump(payload, open(os.path.join(out, "engage-verdict.json"), "w"), indent=2)
print(json.dumps(payload, indent=2))
PY
