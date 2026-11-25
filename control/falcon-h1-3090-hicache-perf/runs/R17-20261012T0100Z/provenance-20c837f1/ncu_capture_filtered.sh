#!/usr/bin/env bash
set -euo pipefail
RUN=/tmp/sglang-r17/control/falcon-h1-3090-hicache-perf/runs/R17-20261012T0100Z
STAGE=${1:?stage}; C=${2:?c8 or c16}; T=${3:-1}; OUT="ncu-${STAGE}-c${C}-t${T}-$(date +%s%N)"
case "$STAGE" in
 prefill) PAT='regex:.*(Marlin<__nv_bfloat16,.*|ampere_bf16_s16816gemm_bf16_128x128.*)'; GRID='stage trace: Marlin MLP and BF16 CUTLASS GEMM'; COUNT=8;;
 decode) PAT='regex:.*(Marlin<__nv_bfloat16,.*|causal_conv1d_update_kernel.*|_selective_scan_update_kernel|ampere_bf16_s16816gemm_bf16_64x64.*)'; GRID='stage trace: Marlin M=1, Mamba conv/scan and BF16 GEMM'; COUNT=8;;
 *) echo bad stage >&2; exit 2;;
esac
[[ "$C" == 8 || "$C" == 16 ]] || exit 2
D="$RUN/$OUT"; mkdir -p "$D"; test -z "$(find "$D" -mindepth 1 -maxdepth 1 -print -quit)"
exec 9>/tmp/f1-r16b-gpu-exclusive.lock; flock -n 9 || { echo 'GPU lock unavailable' >&2; exit 3; }
if ss -ltn | grep -qE ':(30160|30127)\b'; then echo 'Falcon port active' >&2; exit 4; fi
if nvidia-smi --query-compute-apps=pid --format=csv,noheader | grep -q '[0-9]'; then echo 'GPU compute process active' >&2; exit 5; fi
PY=/home/ubuntu/venvs/sglang-3090/bin/python
date -u +%FT%TZ >"$D/ncu-start.utc"; nvidia-smi -q -d CLOCK,POWER,TEMPERATURE,PERFORMANCE >"$D/nvidia-smi-before.txt"
# Launch-and-attach is the validated NCU path on this host. Kernel-name regex
# excludes unrelated launches; scheduler batch identity is source-trace joined.
sudo -n /usr/local/cuda-12.9/bin/ncu --set full --kernel-name-base demangled --kernel-name "$PAT" --launch-count "$COUNT" --target-processes all --csv --page raw --print-metric-attribution --force-overwrite -o "$D/falcon-filtered" "$PY" "$RUN/ncu_filtered_driver.py" --stage "$STAGE" --concurrency "$C" --trial "$T" --outdir "$OUT" >"$D/ncu.stdout" 2>"$D/ncu.stderr"
date -u +%FT%TZ >"$D/ncu-end.utc"; nvidia-smi -q -d CLOCK,POWER,TEMPERATURE,PERFORMANCE >"$D/nvidia-smi-after.txt"
printf '{"stage":"%s","concurrency":%s,"trial":%s,"kernel_regex":"%s","launch_count":%s,"source_trace_mapping":"%s"}\n' "$STAGE" "$C" "$T" "$PAT" "$COUNT" "$GRID" >"$D/manifest.json"
