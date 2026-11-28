#!/usr/bin/env bash
# T014 nsys: one bounded steady-state window of the production C-8 three-tier
# HiCache stack per arm (A = Humming+Triton, B = Humming+FA2).
#   usage: run_nsys_tiers.sh <triton|fa2>
# Reuses the validated T007/T010 harness (real service, real benchmark, nsys
# launch with CUDA+NVTX trace, bounded window) and adds an NVML sampler for clocks,
# power and PCIe link state. nsys GPU-metric counters need root on this driver, so
# whole-GPU DRAM/SM-issue percentages are NOT collected here; per-kernel counters
# come from the NCU cells instead. Whole-GPU samples are labelled as such.
set -Eeuo pipefail
ROOT=/home/ubuntu/workspaces/3rdparty/sglang-hicache
WRAP=$ROOT/control/gemma4-rtx3090-throughput-scheduling/runs/t007_c8_profile.sh
TIER_ARGV=/data/sglang-hicache/gemma4/runs/20261126T-t009-c8-acceptance-r6/launch-argv.txt
OUT=/data/sglang-hicache/gemma4/runs/20261128T-t014-nsys
ARM=${1:?arm triton|fa2}
CELL=$OUT/tiers-$ARM
[[ -r "$TIER_ARGV" ]] || { echo "missing tiers argv" >&2; exit 2; }

rm -rf "$CELL"
mkdir -p "$CELL" "$OUT/logs"
cp "$ROOT/control/gemma4-t014-hwprof/runs/nsys-intent.txt" "$CELL/intent.txt"

ENVV=(T007_OUT="$CELL" T007_HICACHE_MODE=on T007_CHUNK=4096
      T007_WINDOW_SECONDS=45 T007_WINDOW_DELAY=150
      T007_BASELINE_ARGV="$TIER_ARGV"
      T007_BENCH_TAG="T014-tiers-$ARM"
      SGLANG_CTWNA16_HUMMING=1
      SGLANG_T011_BF16_TIMING_PATH="$CELL/ragged-coverage.json"
      SGLANG_T011_BF16_PREFIX_BUDGET_MB=128)
if [[ $ARM == fa2 ]]; then
  ENVV+=(SGLANG_FA2_RAGGED_EXTEND=1 SGLANG_T011_BF16_TIMING_STRIDE=8)
elif [[ $ARM != triton ]]; then
  echo "unknown arm: $ARM" >&2
  exit 2
fi

nvidia-smi --query-gpu=timestamp,utilization.gpu,memory.used,clocks.sm,clocks.mem,power.draw,temperature.gpu,pcie.link.gen.current,pcie.link.width.current \
  --format=csv --loop-ms=500 > "$OUT/nvml-$ARM.csv" &
SAMPLER=$!
trap 'kill "$SAMPLER" 2>/dev/null || true' EXIT

echo "CELL_START cell=tiers-$ARM at=$(date -u +%FT%TZ)" | tee -a "$OUT/nsys-status.txt"
if ! env "${ENVV[@]}" bash "$WRAP" > "$OUT/logs/tiers-$ARM-wrapper.log" 2>&1; then
  printf 'cell=tiers-%s wrapper_failed at=%s\n' "$ARM" "$(date -u +%FT%TZ)" >> "$OUT/nsys-status.txt"
  tail -20 "$OUT/logs/tiers-$ARM-wrapper.log" || true
  exit 4
fi
printf 'cell=tiers-%s done=%s summary=%s\n' "$ARM" "$(date -u +%FT%TZ)" \
  "$(cat "$CELL/official-summary.txt" 2>/dev/null || echo MISSING)" >> "$OUT/nsys-status.txt"

kill "$SAMPLER" 2>/dev/null || true
SAMPLER=
bash "$ROOT/control/gemma4-rtx3090-throughput-scheduling/runs/t007_export_and_summarize.sh" "$CELL" \
  > "$OUT/logs/tiers-$ARM-export.log" 2>&1 || true
if [[ -d "$CELL/l3-extent" ]]; then
  du -sh "$CELL/l3-extent" >> "$OUT/nsys-status.txt"
  rm -rf "$CELL/l3-extent"
fi
echo "CELL_DONE cell=tiers-$ARM at=$(date -u +%FT%TZ)" | tee -a "$OUT/nsys-status.txt"
