#!/usr/bin/env bash
set -Eeuo pipefail
ROOT=/home/ubuntu/workspaces/3rdparty/sglang-hicache
BASE=/data/sglang-hicache/g2-quasar-runs/20261111T-g2-quasar-radix8k-prefix-e5m2-run3
OVERLAY=/data/sglang-hicache/g2-quasar-runs/20261107T-g2-first-logits/head-kernel-shadow
AOT=/data/sglang-hicache/g2-quasar-runs/20261107T-g2-first-logits/aot-sm86-package
VENV=/home/ubuntu/venvs/sglang-3090
PORT=31381
exec 9>/tmp/f1-r16b-gpu-exclusive.lock; flock -n 9 || { echo GPU_LOCK_BUSY >&2; exit 90; }
[[ ! -e "$BASE/run.lock" ]] || { exec 8>"$BASE/run.lock"; flock -n 8 || { echo RUN_LOCK_BUSY >&2; exit 91; }; }
SERVER_PID=$(ss -ltnp | grep ":${PORT}\\b" | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2)
[[ -n "$SERVER_PID" ]] || { echo SERVER_NOT_RUNNING >&2; exit 3; }
kill -0 "$SERVER_PID"
cleanup(){ set +e
 pkill -P "$BASHPID" -f 'nvidia-smi --query-gpu=.*-lms' 2>/dev/null || true
 kill -TERM "$SERVER_PID" 2>/dev/null || true
 for _ in $(seq 1 45); do kill -0 "$SERVER_PID" 2>/dev/null || break; sleep 1; done
 kill -KILL "$SERVER_PID" 2>/dev/null || true
 if ss -ltnp | grep -q ":${PORT}\\b"; then echo PORT_REMAINS > "$BASE/cleanup-warning.txt"; fi
 nvidia-smi --query-gpu=timestamp,memory.used,utilization.gpu --format=csv,noheader > "$BASE/gpu-after.csv"
 sha256sum "$BASE"/{manifest.txt,source-identity.txt,fixture.json,fixture.json.sha256,server.log,records-c1.json,raw-c1.jsonl,records-c2-c32.json,raw-c2-c32.jsonl,records-c4-c32-resume.json,raw-c4-c32-resume.jsonl,event-analysis.txt,gpu-samples.csv,gpu-after.csv} > "$BASE/artifact-sha256.txt" 2>/dev/null || true
}
trap cleanup EXIT INT TERM
export PYTHONNOUSERSITE=1 SGLANG_ENABLE_JIT_DEEPGEMM=0 SGLANG_ENABLE_METRICS_DEVICE_TIMER=1 SGLANG_FORCE_STREAM_INTERVAL=1
export PYTHONPATH="$OVERLAY:$AOT:$ROOT/python:$VENV/lib/python3.12/site-packages:$ROOT/python/sglang/kernels/aot/python"
export RADIX8K_OUT="$BASE" RADIX8K_URL="http://127.0.0.1:$PORT/generate"
"$VENV/bin/python" "$ROOT/experiments/g2-quasar-radix8k-prefix-benchmark/radix8k_benchmark.py" --run --accepted-validation --concurrency 4 8 16 24 32 | tee -a "$BASE/driver-c4-c32-resume.log"
mv "$BASE/records.json" "$BASE/records-c4-c32-resume.json"; mv "$BASE/raw.jsonl" "$BASE/raw-c4-c32-resume.jsonl"
python3 "$ROOT/experiments/g2-quasar-radix8k-prefix-benchmark/analyze_radix8k_events.py" "$BASE/server.log" --measured-only | tee "$BASE/event-analysis.txt"
python3 "$ROOT/experiments/g2-quasar-radix8k-prefix-benchmark/analyze_run.py" "$BASE" --records "$BASE/records-c1.json" "$BASE/records-c2-c32.json" "$BASE/records-c4-c32-resume.json"
