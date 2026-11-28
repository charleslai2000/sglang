#!/usr/bin/env bash
# T014 NCU application-replay collection for one Forward shape.
#   usage: run_ncu.sh <out.json> <driver args...>
# Uses CUPTI ApplicationReplay (``--replay-mode application``) on the standalone
# driver, never kernel replay, and only inside the cudaProfilerStart/Stop region.
set -Eeuo pipefail
ROOT=/home/ubuntu/workspaces/3rdparty/sglang-hicache
VENV=/home/ubuntu/venvs/sglang-3090
AOT=/data/sglang-hicache/g2-quasar-runs/20261110T-g2-postrope-e5m2-quality/aot-sm86-package
NCU=/usr/local/cuda-12.9/bin/ncu
LOCK=/tmp/f1-r16b-gpu-exclusive.lock
OUT_JSON=$1
shift

KERNELS=${T014_KERNEL_FILTER:-regex:Marlin|humming|_fwd_kernel|_fwd_grouped_kernel_stage1|merge_state|RMSNormKernel|FusedAddRMSNorm|act_and_mul_kernel|fused_rope_kernel|BatchPrefill|batchprefill|SinglePrefill|singleprefill}
# Total matching launches profiled per pass (NCU counts globally, not per name).
LAUNCH_COUNT=${T014_LAUNCH_COUNT:-120}
SECTIONS=${T014_SECTIONS:-SpeedOfLight ComputeWorkloadAnalysis MemoryWorkloadAnalysis Occupancy LaunchStats WarpStateStats SchedulerStats}

export PYTHONNOUSERSITE=1 SGLANG_GEMMA4_SWA_POOL_TOKENS=65536
export PYTHONPATH="$AOT:$ROOT/python:$VENV/lib/python3.12/site-packages:$ROOT/python/sglang/kernels/aot/python"
export LD_LIBRARY_PATH="$VENV/lib/python3.12/site-packages/torch/lib:/usr/local/cuda-12.9/lib64"
export SGLANG_CACHE_DIR=/data/sglang-hicache/gemma4/cache HF_HOME=/data/sglang-hicache/gemma4/cache/hf-home
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
export SGLANG_HUMMING_USE_F16_ACCUM=0 SGLANG_T011_BF16_PREFIX_BUDGET_MB=128

exec 9>"$LOCK"
flock -n 9 || { echo GPU_LOCK_BUSY >&2; exit 90; }

SECTION_ARGS=()
for section in $SECTIONS; do SECTION_ARGS+=(--section "$section"); done

exec sudo -n "$NCU" \
  --replay-mode application \
  --profile-from-start off \
  --target-processes application-only \
  --kernel-name "$KERNELS" \
  --launch-count "$LAUNCH_COUNT" \
  "${SECTION_ARGS[@]}" \
  --print-summary per-kernel \
  --csv \
  --force-overwrite \
  --export "$OUT_JSON" \
  "$VENV/bin/python" "$ROOT/control/gemma4-t014-hwprof/runs/t014_forward_driver.py" \
  --profile-region "$@"
