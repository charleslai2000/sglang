#!/usr/bin/env bash
# T015 cell: one production workload with the FA2 coverage diagnostics enabled.
#   usage: run_cell.sh <c8|tiers|long> <triton|fa2> <tag> [extra env...]
set -Eeuo pipefail
ROOT=/home/ubuntu/workspaces/3rdparty/sglang-hicache
OUT=$(cd "$(dirname "$0")" && pwd)
WRAP=$ROOT/control/gemma4-rtx3090-throughput-scheduling/runs/t007_c8_profile.sh
TIER_ARGV=/data/sglang-hicache/gemma4/runs/20261126T-t009-c8-acceptance-r6/launch-argv.txt
FAILED_OUT=/data/sglang-hicache/gemma4/runs/20261128T-t015-fa2-subbatch-partial
L1ONLY_ARGV=/data/sglang-hicache/gemma4/runs/20261127T-t011-l1only-off2/launch-argv.txt

WORKLOAD=${1:?c8|tiers|long}
ARM=${2:?triton|fa2}
TAG=${3:?tag}
DIR=$OUT/cells/$WORKLOAD-$ARM-$TAG
rm -rf "$DIR"; mkdir -p "$DIR" "$OUT/logs"
printf 'workload=%s arm=%s tag=%s\n' "$WORKLOAD" "$ARM" "$TAG" > "$DIR/intent.txt"

ENVV=(T007_OUT="$DIR" T007_WINDOW_SECONDS=0 T007_CHUNK=4096 T007_BENCH_TAG="T015-$WORKLOAD-$ARM-$TAG"
      SGLANG_CTWNA16_HUMMING=1
      SGLANG_T011_BF16_PREFIX_BUDGET_MB=128
      SGLANG_T011_BF16_TIMING_PATH="$DIR/ragged-coverage.json"
      SGLANG_T011_BF16_TIMING_STRIDE=8)
case "$WORKLOAD" in
  c8)    ENVV+=(T007_BASELINE_ARGV="$L1ONLY_ARGV" T007_HICACHE_MODE=off) ;;
  tiers) ENVV+=(T007_BASELINE_ARGV="$TIER_ARGV" T007_HICACHE_MODE=on) ;;
  long)  ENVV+=(T007_BASELINE_ARGV="$TIER_ARGV" T007_HICACHE_MODE=on
                T007_BENCH_CLIENTS=96 T007_BENCH_ROUNDS=6 T007_BENCH_REQ_LEN=5000
                T007_BENCH_OUT_LEN=256 T007_BENCH_MAXPAR=64) ;;
  *) echo "unknown workload $WORKLOAD" >&2; exit 2 ;;
esac
[[ $ARM == fa2 ]] && ENVV+=(SGLANG_FA2_RAGGED_EXTEND=1)
shift 3
ENVV+=("$@")

set +e
env "${ENVV[@]}" bash "$WRAP" > "$OUT/logs/$WORKLOAD-$ARM-$TAG.log" 2>&1
rc=$?
set -e
printf 'cell=%s rc=%s summary=%s\n' "$DIR" "$rc" "$(cat "$DIR/official-summary.txt" 2>/dev/null || echo MISSING)" >> "$OUT/status.txt"
rm -rf "$DIR/l3-extent"
exit $rc
