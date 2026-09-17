#!/usr/bin/env bash
# Consolidated, reproducible PoC run. No GPU, no lock, no ports.
# Stage 0 is the source-identity preflight gate (charter AMENDMENT 1-A); every
# later stage is only meaningful if it passes.
set -u
ROOT=/tmp/opencode/l3-native-poc-20260916
RUN=(env -i
  PATH=/usr/bin:/bin:/home/ubuntu/.cargo/bin
  HOME=/home/ubuntu
  CUDA_VISIBLE_DEVICES=
  PYTHONDONTWRITEBYTECODE=1
  PYTHONPATH=/opt/sglang/local-prod-v1.1-candidate/src/python
  CARGO_NET_OFFLINE=true
  SGLANG_CACHE_DIR="$ROOT/cache")

# --- Stage 0: source-identity preflight gate (fail fast, exit 1) ---
echo "===== preflight_identity ====="
if "${RUN[@]}" /opt/sglang/local-prod-v1/env/bin/python \
    "$ROOT/src/preflight_identity.py" \
    --tree /opt/sglang/local-prod-v1.1-candidate --pid self \
    > "$ROOT/logs/preflight_identity.log" 2>&1; then
  tail -n 1 "$ROOT/logs/preflight_identity.log"
else
  echo "preflight_identity FAILED (see logs/preflight_identity.log)"
  exit 1
fi

fail=0
for stage in stage1_smoke stage1_gil stage1_worker stage2_frames stage3_page \
             stage4_lease stage4_iov stage_preflight; do
  echo "===== $stage ====="
  if "${RUN[@]}" /opt/sglang/local-prod-v1/env/bin/python "$ROOT/src/py/$stage.py" \
      > "$ROOT/logs/$stage.log" 2>&1; then
    tail -n 1 "$ROOT/logs/$stage.log"
  else
    echo "$stage FAILED (see logs/$stage.log)"
    fail=1
  fi
done
exit "$fail"
