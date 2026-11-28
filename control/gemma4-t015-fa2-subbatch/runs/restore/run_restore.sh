#!/usr/bin/env bash
# T013 real L3 restore, round trip per combo:
#   server 1 (write_through, fresh extent) primes the tier with a 20k-token prefix;
#   server 2 (same extent directory, empty device+host tiers) must restore it.
# Shell/argv identical to the production three-tier stack apart from the probe's
# smaller pools, which only make the tier transition deterministic.
set -Eeuo pipefail
ROOT=/home/ubuntu/workspaces/3rdparty/sglang-hicache
VENV=/home/ubuntu/venvs/sglang-3090
HERE=$(cd "$(dirname "$0")" && pwd)
OUT=$HERE/restore2
MODEL=/data/sglang-hicache/gemma4/model
AOT=/data/sglang-hicache/g2-quasar-runs/20261110T-g2-postrope-e5m2-quality/aot-sm86-package
OVERLAY=$ROOT/control/gemma4-w4a16-3090-performance-capacity/runs/overlay
TIER_ARGV=/data/sglang-hicache/gemma4/runs/20261126T-t009-c8-acceptance-r6/launch-argv.txt
PORT=31418

exec 9>/tmp/f1-r16b-gpu-exclusive.lock
flock -n 9 || { echo LOCK_BUSY; exit 90; }
if ss -ltn | grep -q ":$PORT\\b"; then echo PORT_BUSY; exit 91; fi

export PYTHONNOUSERSITE=1 SGLANG_GEMMA4_SWA_POOL_TOKENS=65536
export PYTHONPATH="$AOT:$ROOT/python:$VENV/lib/python3.12/site-packages:$ROOT/python/sglang/kernels/aot/python:$OVERLAY"
export LD_LIBRARY_PATH="$VENV/lib/python3.12/site-packages/torch/lib:/usr/local/cuda-12.9/lib64"
export SGLANG_CACHE_DIR=/data/sglang-hicache/gemma4/cache HF_HOME=/data/sglang-hicache/gemma4/cache/hf-home
export SGLANG_HUMMING_USE_F16_ACCUM=0 SGLANG_CTWNA16_HUMMING=1
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True

build_args() {  # $1 = extent dir, $2 = write policy
  "$VENV/bin/python" - "$TIER_ARGV" "$MODEL" "$PORT" "$1" "$2" <<'PY'
import json, shlex, sys
argv = shlex.split(open(sys.argv[1]).read())
model, port, extent, policy = sys.argv[2:6]
drop_v = {"--port", "--model-path", "--export-metrics-to-file-dir",
          "--max-total-tokens", "--hicache-size", "--hicache-write-policy",
          "--hicache-storage-backend-extra-config"}
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
        "--hicache-write-policy", policy,
        "--hicache-storage-backend-extra-config",
        json.dumps({"storage_dir": extent, "extent_size": 67108864,
                    "file_size": 8 * 1024 ** 3, "max_size": 8 * 1024 ** 3,
                    "min_free_space": 1073741824})]
print("\n".join(out))
PY
}

start_server() {  # $1 = dir, $2 = extent dir, $3 = policy
  mapfile -t ARGS < <(build_args "$2" "$3")
  export T013_SERVER_LOG=$1/server.log
  "$VENV/bin/python" -u -m sglang.launch_server "${ARGS[@]}" > "$1/server.log" 2>&1 &
  PID=$!
}

stop_server() {
  kill -TERM "$PID" 2>/dev/null || true
  for _ in $(seq 1 90); do kill -0 "$PID" 2>/dev/null || break; sleep 1; done
  kill -KILL "$PID" 2>/dev/null || true
  pkill -TERM -f "sglang.srt.managers.scheduler .*--port $PORT" 2>/dev/null || true
  sleep 3
}

mkdir -p "$OUT"
for ARM in triton fa2; do
  DIR=$OUT/$ARM
  rm -rf "$DIR"; mkdir -p "$DIR"
  EXTENT=$DIR/extent
  if [[ $ARM == fa2 ]]; then
    export SGLANG_FA2_RAGGED_EXTEND=1 SGLANG_T011_BF16_PREFIX_BUDGET_MB=128
    export SGLANG_T011_BF16_TIMING_PATH="$DIR/restore-coverage.json"
    export SGLANG_T011_BF16_TIMING_STRIDE=1
  else
    unset SGLANG_FA2_RAGGED_EXTEND SGLANG_T011_BF16_PREFIX_BUDGET_MB \
          SGLANG_T011_BF16_TIMING_PATH SGLANG_T011_BF16_TIMING_STRIDE || true
  fi
  # Phase 1: prime the extent tier.
  start_server "$DIR" "$EXTENT" write_through
  "$VENV/bin/python" "/home/ubuntu/workspaces/3rdparty/sglang-hicache/control/gemma4-t013-opt-merge/runs/t013_restore_roundtrip.py" "$PORT" "$ARM" prime "$DIR" \
    > "$DIR/prime.log" 2>&1 || echo "$ARM PRIME_FAILED" >&2
  stop_server
  du -sh "$EXTENT" >> "$DIR/sizes.txt" 2>/dev/null || true
  # Phase 2: a fresh process with empty device/host tiers must restore from it.
  start_server "$DIR" "$EXTENT" write_back
  "$VENV/bin/python" "/home/ubuntu/workspaces/3rdparty/sglang-hicache/control/gemma4-t013-opt-merge/runs/t013_restore_roundtrip.py" "$PORT" "$ARM" restore "$DIR" \
    > "$DIR/restore.log" 2>&1 || echo "$ARM RESTORE_FAILED" >&2
  stop_server
  du -sh "$EXTENT" >> "$DIR/sizes.txt" 2>/dev/null || true
  # Phase 3: same primed extent, fresh process, record greedy completions.
  start_server "$DIR" "$EXTENT" write_back
  "$VENV/bin/python" "/home/ubuntu/workspaces/3rdparty/sglang-hicache/control/gemma4-t013-opt-merge/runs/t013_restore_text.py" "$PORT" "$ARM" "$DIR" \
    > "$DIR/text.log" 2>&1 || echo "$ARM TEXT_FAILED" >&2
  stop_server
done

"$VENV/bin/python" - "$OUT" <<'PY'
import json, os, sys
root = sys.argv[1]
arms = {}
for arm in ("triton", "fa2"):
    path = os.path.join(root, arm, f"{arm}-text.json")
    arms[arm] = json.load(open(path)) if os.path.exists(path) else None
out = {"arms": arms}
if all(arms.values()):
    out["target_text_equal"] = arms["triton"]["target"]["text"] == arms["fa2"]["target"]["text"]
    out["short_text_equal"] = all(
        arms["triton"]["short"][k]["text"] == arms["fa2"]["short"][k]["text"]
        for k in arms["triton"]["short"]
    )
    out["restored_tokens"] = {arm: arms[arm]["target"]["cached_tokens"] for arm in arms}
    out["restore_full"] = {arm: arms[arm]["log"]["restore_full"] for arm in arms}
json.dump(out, open(os.path.join(root, "restore3-verdict.json"), "w"), indent=2)
print(json.dumps(out, indent=2)[:1500])
PY

"$VENV/bin/python" - "$OUT" <<'PY'
import json, os, sys
root = sys.argv[1]
data = {}
for arm in ("triton", "fa2"):
    data[arm] = {}
    for phase in ("prime", "restore"):
        path = os.path.join(root, arm, f"{phase}.json")
        data[arm][phase] = json.load(open(path)) if os.path.exists(path) else None
summary = {"arms": {}}
for arm, phases in data.items():
    prime, restore = phases["prime"], phases["restore"]
    if not prime or not restore:
        summary["arms"][arm] = None
        continue
    summary["arms"][arm] = {
        "primed_ids": prime["main"]["output_ids"],
        "primed_cached_second_pass": prime["main"].get("second_pass_cached"),
        "restored_ids": restore["main"]["output_ids"],
        "restored_cached_tokens": restore["main"]["cached_tokens"],
        "restore_storage_hit": restore["log"]["storage_hit_1"],
        "restore_disposition": restore["log"]["restore_disposition"],
        "restore_recompute": restore["log"]["restore_recompute"],
        "ids_match_prime": prime["main"]["output_ids"] == restore["main"]["output_ids"],
        "short_greedy": restore["short_greedy"],
    }
both = summary["arms"].get("triton") and summary["arms"].get("fa2")
summary["short_greedy_equal"] = bool(
    both
    and summary["arms"]["triton"]["short_greedy"] == summary["arms"]["fa2"]["short_greedy"]
)
summary["verdict"] = "PASS" if (
    both
    and summary["arms"]["triton"]["ids_match_prime"]
    and summary["arms"]["fa2"]["ids_match_prime"]
    and summary["arms"]["triton"]["restored_cached_tokens"] > 0
    and summary["arms"]["fa2"]["restored_cached_tokens"] > 0
    and summary["arms"]["fa2"]["restore_storage_hit"] > 0
    and summary["short_greedy_equal"]
) else "FAIL"
json.dump(summary, open(os.path.join(root, "restore2-verdict.json"), "w"), indent=2)
print(json.dumps(summary, indent=2))
PY
