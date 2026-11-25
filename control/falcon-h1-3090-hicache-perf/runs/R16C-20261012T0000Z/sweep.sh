#!/usr/bin/env bash
set -euo pipefail
ROOT=/tmp/sglang-f1-r16b-clean; RUN=/home/ubuntu/workspaces/3rdparty/sglang-hicache/control/falcon-h1-3090-hicache-perf/runs/R16C-20261012T0000Z
cfg=$1; conc=$2; trial=$3
case "$cfg" in gpu-only) port=30150; launch="$RUN/launch_gpu_only.sh";; gpu-host) port=30151; launch="$RUN/launch_gpu_host.sh";; *) exit 2;; esac
exec 9>/tmp/f1-r16b-gpu-exclusive.lock; flock -x 9
used=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | tr -d ' '); [[ $used -le 32 ]]
mkdir -p "$RUN/$cfg/c${conc}/t${trial}"; out="$RUN/$cfg/c${conc}/t${trial}"
[[ ! -e $out/result.json ]] || { echo "preserving existing result directory: $out" >&2; exit 4; }
# Deterministic GSP manifest must be generated offline by --prepare-manifests before any GPU run.
manifest="$RUN/manifest-v4-c${conc}-t${trial}.json"
[[ -s $manifest ]] || { echo "missing frozen manifest: $manifest" >&2; exit 3; }
"$launch" > "$out/server.log" 2>&1 & server=$!
cleanup(){ kill -TERM "$server" 2>/dev/null||true;for i in $(seq 1 40);do kill -0 "$server" 2>/dev/null||break;sleep 1;done;kill -KILL "$server" 2>/dev/null||true;wait "$server" 2>/dev/null||true; }
trap cleanup EXIT INT TERM
for i in $(seq 1 180);do grep -q 'The server is fired up and ready to roll!' "$out/server.log"&&break;kill -0 "$server" 2>/dev/null||exit 1;sleep 2;done
grep -q 'The server is fired up and ready to roll!' "$out/server.log"
args=(--base-url "http://127.0.0.1:$port" --output "$out/result.json" --manifest "$manifest" --config "$cfg" --server-log "$out/server.log" --concurrency "$conc" --sessions 72 --rounds 4 --prefix-len 4608 --question-len 256 --output-len 64 --groups 36 --metrics-before "$out/metrics-before.txt" --metrics-after "$out/metrics-after.txt" --fpm-endpoint "ipc:///tmp/r16c-${cfg}-fpm.0" --fpm-output "$out/forward-pass-metrics.json" --fpm-duration 7200)
PYTHONPATH="/tmp/f1-r3-kernel-overlay:$ROOT/python:$ROOT/python/sglang/kernels/aot/python" /home/ubuntu/venvs/sglang-3090/bin/python "$RUN/multiturn_sweep.py" "${args[@]}" > "$out/driver.log" 2>&1
# Independent cache-counter snapshot is collected with the same request protocol.
cleanup;trap - EXIT INT TERM
for i in $(seq 1 25);do ! ss -ltn | grep -q ":$port "&&break;sleep 1;done
! ss -ltn | grep -q ":$port "
nvidia-smi --query-gpu=memory.used --format=csv,noheader | grep -qx '1 MiB'
