#!/usr/bin/env bash
# T014 supplements: instruction-pipe (INT/LSU/SFU) and L2 sector counters that the
# main section set does not expose. Same driver, same shapes, fewer launches.
set -uo pipefail
ROOT=/home/ubuntu/workspaces/3rdparty/sglang-hicache
OUT=/data/sglang-hicache/gemma4/runs/20261128T-t014-ncu
LOG=$OUT/logs
mkdir -p "$OUT" "$LOG"

run() {
  local name=$1; shift
  local t0 t1
  t0=$(date +%s)
  echo "== $name $(date -u +%FT%TZ)" | tee -a "$OUT/supplement-progress.txt"
  env T014_SECTIONS="SpeedOfLight InstructionStats MemoryWorkloadAnalysis_Tables" \
      T014_LAUNCH_COUNT=60 \
    bash "$ROOT/control/gemma4-t014-hwprof/runs/run_ncu.sh" \
    "$OUT/$name" "$@" --out "$OUT/$name.json" > "$LOG/$name.log" 2>&1
  local rc=$?
  t1=$(date +%s)
  echo "$name rc=$rc secs=$((t1 - t0))" | tee -a "$OUT/supplement-progress.txt"
}

run A-prefill4096-instr --stage prefill --input-len 4096 --arm marlin --attn triton
run B-prefill4096-instr --stage prefill --input-len 4096 --arm humming --attn fa2
run A-decode32-instr --stage decode --batch 32 --decode-context 8192 --arm marlin --attn triton
run B-decode32-instr --stage decode --batch 32 --decode-context 8192 --arm humming --attn fa2
echo "SUPPLEMENT_DONE $(date -u +%FT%TZ)" | tee -a "$OUT/supplement-progress.txt"
