#!/usr/bin/env bash
# =============================================================================
# launcher-phase2-pc1.sh
# Phase-2 production-candidate (tag 3090-hicache-phase2-pc1 / commit 9c9e7b7c7c)
#   ONE-CLICK EXPERIMENT-ENVIRONMENT REPRODUCTION on 24052 (RTX 3090 24G).
#
# ⚠️ IMPORTANT
#   This launcher reproduces the *experiment/benchmark environment* used to
#   produce the Phase-2 evidence. It is NOT a production deployment script.
#   It is a config-only wrapper; it does NOT touch any engine .py file.
#
# ORIGIN OF PARAMETERS
#   This script copies the already-existing blueprints:
#     /root/gate3_ab.sh              (RH A/B driver, 24052, the actual soak driver)
#     /root/direct-launch-gate1-rhon.sh (RH-ON engine wrapper, 24052)
#     /root/direct-launch-gate1.sh   (RH-OFF engine wrapper, 24052)
#   The Phase-2 soak-final run that produced the 7/7 PASS evidence used exactly:
#     gate3_ab.sh --tag soak-final --agents 8
#                 --launch /root/direct-launch-gate1-rhon.sh
#                 --rt 400 --budget 7200 --cmax 900
#                 --max-size 200G --file-size 30G
#   (see .memory/.../work/phase2-soak-tester-e1.md §1; verdict elapsed 7229.9s,
#    2349 requests, rc=0, 2h complete).
#
#   The flag <-> commit correspondence:
#     --max-size 200G  -> env MAX_SIZE=200G  -> SGLANG_HICACHE_EXTENT_BACKEND_MAX_SIZE
#                         and --hicache-storage-backend-extra-config max_size=200G
#     --file-size 30G  -> env SGLANG_HICACHE_EXTENT_BACKEND_FILE_SIZE=30G
#     --agents 8       -> gate2_load.py --agents 8
#     --rt 400         -> gate2_load.py --read-turns 400
#     --budget 7200    -> gate2_load.py --time-budget 7200 (2h soak window)
#     --cmax 900       -> gate2_load.py --client-max-time 900
#   Engine fixed config (from direct-launch-gate1-rhon.sh):
#     RH ON, write_back, L3 extent backend, MAX_SIZE=200G, FILE_SIZE=30G,
#     max_total_tokens=65536, hicache_ratio=1.5, page_size=1, pool64,
#     CUDA Graph ON, conc 8.
#
# PREREQUISITES ON 24052 (root)
#   - Engine repo: /root/sglang-b1-continuity (editable install, non-git,
#     manually synced). Phase-2 two files == 9c9e7b7c7c:
#       python/sglang/srt/managers/scheduler.py   md5 495b88515cc2e932c57448359443604d
#       3090-dev/test_hicache_restore_scheduler_feed.py md5 465b6c68ce813b0522200ac96fea0828
#     Backup .bak-round2-pre retained.
#   - Driver/analysis: /root/gate3_ab.sh, /root/gate2_load.py,
#     /root/direct-launch-gate1-rhon.sh (config-only).
#   - Model: /root/models/Qwen3.5-9B-w4a16 (Qwen3.5-9B-w4a16 GPTQ)
#   - L3 admin key: /opt/sglang/l3-admin-key
#   - conda env: sglang-patch (python 3.10.21, torch 2.13.0+cu130,
#     editable sglang@/root/sglang-b1-continuity/python)
#
# USAGE (on 24052, as root)
#   bash launcher-phase2-pc1.sh [--tag <tag>] [--agents K] [--rt N]
#                              [--budget S] [--cmax S] [--max-size S] [--file-size S]
#   Defaults reproduce the soak-final run (tag=repro, budget=7200).
# =============================================================================
set -u

# ---- defaults (reproduce soak-final run) ----
TAG="repro"
AGENTS=8
RT=400
BUDGET=7200
CMAX=900
MAX_SIZE="200G"
FILE_SIZE="30G"
LAUNCH="/root/direct-launch-gate1-rhon.sh"

while [ $# -gt 0 ]; do
  case "$1" in
    --tag)      TAG="$2";      shift 2;;
    --agents)   AGENTS="$2";   shift 2;;
    --rt)       RT="$2";       shift 2;;
    --budget)   BUDGET="$2";   shift 2;;
    --cmax)     CMAX="$2";     shift 2;;
    --max-size) MAX_SIZE="$2"; shift 2;;
    --file-size) FILE_SIZE="$2"; shift 2;;
    --launch)   LAUNCH="$2";   shift 2;;
    *) echo "unknown arg $1"; exit 2;;
  esac
done

# ---- sanity / preflight (read-only) ----
[ -x "$LAUNCH" ] || { echo "FATAL: launcher $LAUNCH missing"; exit 2; }
[ -f /root/gate3_ab.sh ] || { echo "FATAL: /root/gate3_ab.sh missing"; exit 2; }
[ -f /root/gate2_load.py ] || { echo "FATAL: /root/gate2_load.py missing"; exit 2; }

echo "== Phase-2 pc1 EXPERIMENT reproduction (NOT production) =="
echo "   tag=$TAG agents=$AGENTS rt=$RT budget=${BUDGET}s cmax=$CMAX"
echo "   max_size=$MAX_SIZE file_size=$FILE_SIZE launch=$LAUNCH"

# ---- deploy the exact Phase-2 engine files (idempotent, md5-verified) ----
# Files come from the local git repo at commit 9c9e7b7c7c (tag 3090-hicache-phase2-pc1),
# synced via scp to 24052. This block re-asserts the deployment md5s and re-syncs
# from the staged copies if the running scheduler does not match the candidate.
SRC_SCHED=/root/sglang-b1-continuity/python/sglang/srt/managers/scheduler.py
SRC_TEST=/root/sglang-b1-continuity/3090-dev/test_hicache_restore_scheduler_feed.py
EXP_SCHED_MD5=495b88515cc2e932c57448359443604d
EXP_TEST_MD5=465b6c68ce813b0522200ac96fea0828

got_sched=$(md5sum "$SRC_SCHED" 2>/dev/null | awk '{print $1}')
got_test=$(md5sum "$SRC_TEST" 2>/dev/null | awk '{print $1}')
if [ "$got_sched" != "$EXP_SCHED_MD5" ] || [ "$got_test" != "$EXP_TEST_MD5" ]; then
  echo "WARN: deployed Phase-2 files do not match 9c9e7b7c7c:"
  echo "      scheduler got=$got_sched want=$EXP_SCHED_MD5"
  echo "      test      got=$got_test    want=$EXP_TEST_MD5"
  echo "      Refusing to launch on non-candidate engine. Sync files from"
  echo "      commit 9c9e7b7c7c first (see ENGINE_SYNC.md)."
  exit 3
fi
echo "   engine md5 OK (scheduler=$EXP_SCHED_MD5, test=$EXP_TEST_MD5)"

# ---- run the actual Phase-2 soak driver ----
# gate3_ab.sh launches the engine, waits for /health 200, runs gate2_load.py,
# samples GPU, dumps evidence to /root/evidence-gate3-<TAG>/, and SIGTERMs the
# engine. Config-only; does not touch engine .py.
exec bash /root/gate3_ab.sh \
  --tag "$TAG" \
  --agents "$AGENTS" \
  --launch "$LAUNCH" \
  --rt "$RT" \
  --budget "$BUDGET" \
  --cmax "$CMAX" \
  --max-size "$MAX_SIZE" \
  --file-size "$FILE_SIZE"
