#!/usr/bin/env bash
# T013 final restore evidence: one fresh process per combo against the already
# primed extent tier, with per-phase log names so the RESTORE line survives.
set -Eeuo pipefail
ROOT=/home/ubuntu/workspaces/3rdparty/sglang-hicache
VENV=/home/ubuntu/venvs/sglang-3090
HERE=$(cd "$(dirname "$0")" && pwd)
SRC=$HERE/restore2
OUT=$HERE/restore4
MODEL=/data/sglang-hicache/gemma4/model
AOT=/data/sglang-hicache/g2-quasar-runs/20261110T-g2-postrope-e5m2-quality/aot-sm86-package
OVERLAY=$ROOT/control/gemma4-w4a16-3090-performance-capacity/runs/overlay
TIER_ARGV=/data/sglang-hicache/gemma4/runs/20261126T-t009-c8-acceptance-r6/launch-argv.txt
PORT=31417

exec 9>/tmp/f1-r16b-gpu-exclusive.lock
flock -n 9 || { echo LOCK_BUSY; exit 90; }
ss -ltn | grep -q ":$PORT\\b" && { echo PORT_BUSY; exit 91; }

export PYTHONNOUSERSITE=1 SGLANG_GEMMA4_SWA_POOL_TOKENS=65536
export PYTHONPATH="$AOT:$ROOT/python:$VENV/lib/python3.12/site-packages:$ROOT/python/sglang/kernels/aot/python:$OVERLAY"
export LD_LIBRARY_PATH="$VENV/lib/python3.12/site-packages/torch/lib:/usr/local/cuda-12.9/lib64"
export SGLANG_CACHE_DIR=/data/sglang-hicache/gemma4/cache HF_HOME=/data/sglang-hicache/gemma4/cache/hf-home
export SGLANG_HUMMING_USE_F16_ACCUM=0 SGLANG_CTWNA16_HUMMING=1
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True

mkdir -p "$OUT"
for ARM in triton fa2; do
  DIR=$OUT/$ARM
  rm -rf "$DIR"; mkdir -p "$DIR"
  EXTENT=$SRC/$ARM/extent
  [[ -d "$EXTENT" ]] || { echo "missing primed extent for $ARM" >&2; exit 3; }
  mapfile -t ARGS < <(
    "$VENV/bin/python" - "$TIER_ARGV" "$MODEL" "$PORT" "$EXTENT" <<'PY'
import json, shlex, sys
argv = shlex.split(open(sys.argv[1]).read())
model, port, extent = sys.argv[2:5]
drop_v = {"--port", "--model-path", "--export-metrics-to-file-dir",
          "--max-total-tokens", "--hicache-size", "--hicache-storage-backend-extra-config"}
drop_f = {"--enable-metrics", "--export-metrics-to-file"}
out, i = [], 0
while i < len(argv):
    if argv[i] in drop_v:
        i += 2; continue
    if argv[i] in drop_f:
        i += 1; continue
    out.append(argv[i]); i += 1
out += ["--model-path", model, "--host", "127.0.0.1", "--port", port,
        "--max-total-tokens", "65536", "--hicache-size", "1",
        "--hicache-storage-backend-extra-config",
        json.dumps({"storage_dir": extent, "extent_size": 67108864,
                    "file_size": 8 * 1024 ** 3, "max_size": 8 * 1024 ** 3,
                    "min_free_space": 1073741824})]
print("\n".join(out))
PY
  )
  export T013_SERVER_LOG=$DIR/server-restore.log
  if [[ $ARM == fa2 ]]; then
    export SGLANG_FA2_RAGGED_EXTEND=1 SGLANG_T011_BF16_PREFIX_BUDGET_MB=128
    export SGLANG_T011_BF16_TIMING_PATH="$DIR/coverage.json" SGLANG_T011_BF16_TIMING_STRIDE=1
  else
    unset SGLANG_FA2_RAGGED_EXTEND SGLANG_T011_BF16_PREFIX_BUDGET_MB \
          SGLANG_T011_BF16_TIMING_PATH SGLANG_T011_BF16_TIMING_STRIDE || true
  fi
  "$VENV/bin/python" -u -m sglang.launch_server "${ARGS[@]}" > "$DIR/server-restore.log" 2>&1 &
  PID=$!
  "$VENV/bin/python" "$HERE/../t013_restore_roundtrip.py" "$PORT" "$ARM" restore "$DIR" \
    > "$DIR/restore.log" 2>&1 || echo "$ARM RESTORE_FAILED" >&2
  kill -TERM "$PID" 2>/dev/null || true
  for _ in $(seq 1 90); do kill -0 "$PID" 2>/dev/null || break; sleep 1; done
  kill -KILL "$PID" 2>/dev/null || true
  pkill -TERM -f "sglang.srt.managers.scheduler .*--port $PORT" 2>/dev/null || true
  sleep 3
  grep "disposition=RESTORE" "$DIR/server-restore.log" | tail -2 > "$DIR/restore-line.txt" || true
done

"$VENV/bin/python" - "$OUT" <<'PY'
import json, os, sys
root = sys.argv[1]
summary = {}
for arm in ("triton", "fa2"):
    path = os.path.join(root, arm, "restore.json")
    row = json.load(open(path)) if os.path.exists(path) else None
    line = ""
    line_path = os.path.join(root, arm, "restore-line.txt")
    if os.path.exists(line_path):
        line = open(line_path).read().strip()
    summary[arm] = None if row is None else {
        "prompt_tokens": row["main"]["prompt_tokens"],
        "restored_cached_tokens": row["main"]["cached_tokens"],
        "extent_read": row["log"]["extent_read"],
        "restore_disposition": row["log"]["restore_disposition"],
        "restore_line": line,
        "second_pass_short": row["short_greedy"],
    }
full = all(
    summary[arm]
    and summary[arm]["restored_cached_tokens"] >= summary[arm]["prompt_tokens"] - 2
    and summary[arm]["restore_disposition"] >= 1
    and "disposition=RESTORE" in summary[arm]["restore_line"]
    for arm in ("triton", "fa2")
)
summary["full_restore_both_arms"] = full
summary["verdict"] = "PASS" if full else "FAIL"
json.dump(summary, open(os.path.join(root, "restore4-verdict.json"), "w"), indent=2)
print(json.dumps(summary, indent=2))
PY
