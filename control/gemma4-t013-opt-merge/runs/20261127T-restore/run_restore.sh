#!/usr/bin/env bash
# T013 real L3 restore check for both combinations (Humming+Triton / Humming+FA2).
# Same frozen C-8 acceptance argv; only max-total-tokens, hicache-size, extent dir,
# port and the FA2 flag differ, so the restore contract is exercised identically.
set -Eeuo pipefail
ROOT=/home/ubuntu/workspaces/3rdparty/sglang-hicache
VENV=/home/ubuntu/venvs/sglang-3090
OUT=$(cd "$(dirname "$0")" && pwd)/restore
MODEL=/data/sglang-hicache/gemma4/model
AOT=/data/sglang-hicache/g2-quasar-runs/20261110T-g2-postrope-e5m2-quality/aot-sm86-package
OVERLAY=$ROOT/control/gemma4-w4a16-3090-performance-capacity/runs/overlay
TIER_ARGV=/data/sglang-hicache/gemma4/runs/20261126T-t009-c8-acceptance-r6/launch-argv.txt
PORT=31413

exec 9>/tmp/f1-r16b-gpu-exclusive.lock
flock -n 9 || { echo LOCK_BUSY; exit 90; }
if ss -ltn | grep -q ":$PORT\\b"; then echo PORT_BUSY; exit 91; fi

export PYTHONNOUSERSITE=1 SGLANG_GEMMA4_SWA_POOL_TOKENS=65536
export PYTHONPATH="$AOT:$ROOT/python:$VENV/lib/python3.12/site-packages:$ROOT/python/sglang/kernels/aot/python:$OVERLAY"
export LD_LIBRARY_PATH="$VENV/lib/python3.12/site-packages/torch/lib:/usr/local/cuda-12.9/lib64"
export SGLANG_CACHE_DIR=/data/sglang-hicache/gemma4/cache
export HF_HOME=/data/sglang-hicache/gemma4/cache/hf-home
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
export SGLANG_HUMMING_USE_F16_ACCUM=0
export SGLANG_CTWNA16_HUMMING=1

mkdir -p "$OUT"
for ARM in triton fa2; do
  DIR=$OUT/$ARM
  rm -rf "$DIR"; mkdir -p "$DIR"
  EXTENT=$DIR/l3-extent
  mapfile -t ARGS < <(
    "$VENV/bin/python" - "$TIER_ARGV" "$MODEL" "$PORT" "$EXTENT" <<'PY'
import json, shlex, sys
argv = shlex.split(open(sys.argv[1]).read())
model, port, extent = sys.argv[2], sys.argv[3], sys.argv[4]
drop_with_value = {"--port", "--max-total-tokens", "--hicache-size",
                   "--hicache-storage-backend-extra-config", "--model-path",
                   "--export-metrics-to-file-dir"}
drop_flag = {"--enable-metrics", "--export-metrics-to-file"}
out, i = [], 0
while i < len(argv):
    if argv[i] in drop_with_value:
        i += 2
        continue
    if argv[i] in drop_flag:
        i += 1
        continue
    out.append(argv[i])
    i += 1
out += ["--model-path", model, "--host", "127.0.0.1", "--port", port,
        "--max-total-tokens", "65536", "--hicache-size", "1",
        "--hicache-storage-backend-extra-config",
        json.dumps({"storage_dir": extent, "extent_size": 67108864,
                    "file_size": 8 * 1024 ** 3, "max_size": 8 * 1024 ** 3,
                    "min_free_space": 1073741824})]
print("\n".join(out))
PY
  )
  export T013_SERVER_LOG=$DIR/server.log
  if [[ $ARM == fa2 ]]; then
    export SGLANG_FA2_RAGGED_EXTEND=1 SGLANG_T011_BF16_PREFIX_BUDGET_MB=128
  else
    unset SGLANG_FA2_RAGGED_EXTEND SGLANG_T011_BF16_PREFIX_BUDGET_MB || true
  fi
  "$VENV/bin/python" -u -m sglang.launch_server "${ARGS[@]}" > "$DIR/server.log" 2>&1 &
  PID=$!
  "$VENV/bin/python" "$OUT/../../t013_restore_probe.py" "$PORT" "$DIR" "$ARM" > "$DIR/probe.log" 2>&1 || {
    echo "$ARM PROBE_FAILED" >&2; tail -20 "$DIR/probe.log" >&2; }
  kill -TERM "$PID" 2>/dev/null || true
  for _ in $(seq 1 90); do kill -0 "$PID" 2>/dev/null || break; sleep 1; done
  kill -KILL "$PID" 2>/dev/null || true
  wait "$PID" 2>/dev/null || true
  pkill -TERM -f "sglang.srt.managers.scheduler .*--port $PORT" 2>/dev/null || true
  sleep 3
done

"$VENV/bin/python" - "$OUT" <<'PY'
import json, os, sys
root = sys.argv[1]
rows = {}
for arm in ("triton", "fa2"):
    path = os.path.join(root, arm, f"{arm}.json")
    rows[arm] = json.load(open(path)) if os.path.exists(path) else None
summary = {
    "arms": {
        arm: None if row is None else {
            "restored_tokens": row["restored_tokens"],
            "warm_cached_tokens": row["warm_cached_tokens"],
            "ids_match_cold": row["ids_match_cold"],
            "cold_ids": row["cold"].get("output_ids"),
            "restored_ids": row["restored"].get("output_ids"),
            "extent": row["extent"],
        }
        for arm, row in rows.items()
    },
}
both = rows["triton"] and rows["fa2"]
summary["arms_agree"] = bool(
    both and rows["triton"]["cold"].get("output_ids") == rows["fa2"]["cold"].get("output_ids")
)
if both:
    short_t, short_f = rows["triton"].get("short_greedy", {}), rows["fa2"].get("short_greedy", {})
    summary["short_greedy_equal"] = {
        key: short_t.get(key) == short_f.get(key) for key in sorted(short_t)
    }
    summary["short_greedy_all_equal"] = all(summary["short_greedy_equal"].values())
summary["verdict"] = "PASS" if (
    both
    and rows["triton"]["ids_match_cold"]
    and rows["fa2"]["ids_match_cold"]
    and rows["triton"]["restored_tokens"] > 0
    and rows["fa2"]["restored_tokens"] > 0
    and summary["arms_agree"]
    and summary.get("short_greedy_all_equal")
) else "FAIL"
json.dump(summary, open(os.path.join(root, "restore-verdict.json"), "w"), indent=2)
print(json.dumps(summary, indent=2))
PY
