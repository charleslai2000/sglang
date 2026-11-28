#!/usr/bin/env bash
# T014 NCU matrix: 6 production Forward shapes x 2 arms, CUPTI ApplicationReplay.
set -uo pipefail
ROOT=/home/ubuntu/workspaces/3rdparty/sglang-hicache
OUT=/data/sglang-hicache/gemma4/runs/20261128T-t014-ncu
LOG=$OUT/logs
mkdir -p "$OUT" "$LOG"
: > "$OUT/matrix-start.txt"
date -u +%FT%TZ | tee -a "$OUT/matrix-start.txt"

run() {
  local name=$1; shift
  local t0 t1
  t0=$(date +%s)
  echo "== $name $(date -u +%FT%TZ)" | tee -a "$OUT/matrix-progress.txt"
  bash "$ROOT/control/gemma4-t014-hwprof/runs/run_ncu.sh" \
    "$OUT/$name" "$@" --out "$OUT/$name.json" > "$LOG/$name.log" 2>&1
  local rc=$?
  t1=$(date +%s)
  if [[ -f "$OUT/$name.json" ]]; then
    python3 -c '
import json, sys
d = json.load(open(sys.argv[1]))
print("   pool_full={} pool_swa={} clamped={}".format(
    d.get("max_total_num_tokens"),
    (d.get("kv_pool_geometry") or {}).get("alloc.size_swa"),
    d.get("max_total_tokens_clamped")))
' "$OUT/$name.json" >> "$OUT/matrix-progress.txt"
  fi
  echo "$name rc=$rc secs=$((t1 - t0))" | tee -a "$OUT/matrix-progress.txt"
  echo "$rc" > "$OUT/$name.rc"
}

for arm in marlin humming; do
  if [ "$arm" = marlin ]; then attn=triton; tag=A; else attn=fa2; tag=B; fi
  run "$tag-prefill1024" --stage prefill --input-len 1024 --arm "$arm" --attn "$attn"
  run "$tag-prefill4096" --stage prefill --input-len 4096 --arm "$arm" --attn "$attn"
  run "$tag-prefix16k" --stage prefix --prefix-len 16384 --new-len 1024 --arm "$arm" --attn "$attn"
  run "$tag-decode8" --stage decode --batch 8 --decode-context 8192 --arm "$arm" --attn "$attn"
  run "$tag-decode16" --stage decode --batch 16 --decode-context 8192 --arm "$arm" --attn "$attn"
  run "$tag-decode32" --stage decode --batch 32 --decode-context 8192 --arm "$arm" --attn "$attn"
done

date -u +%FT%TZ | tee -a "$OUT/matrix-done.txt"
