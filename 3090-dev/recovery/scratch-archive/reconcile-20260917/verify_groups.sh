#!/bin/bash
set -e

REPO="/home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt"
FROZEN="/opt/sglang/local-prod-v1.1.2-candidate/src"
OUT="/tmp/opencode/reconcile-20260917"

# All 25 files relative to src/ prefix in frozen, or relative to repo root
# Group A: 14 files already in worktree (modified or untracked)
# Group B: 9 files only in frozen (absent from HEAD and worktree)
# Group C: 2 files with divergent worktree version

# We need to handle the src/ prefix: frozen files are under FROZEN/src/... 
# but repo files are under $REPO/... (no src/ prefix)

cd "$REPO"

echo "=== Computing SHA256 hashes ==="
echo ""

# Group A files
GROUP_A=(
  ".dockerignore"
  ".memory/phase2-hicache-design/work/ARTIFACT-CAPABILITY-INVENTORY-20260916.md"
  ".memory/phase2-hicache-design/work/OPEN4-SHIM-NECESSITY-VERDICT-20260916.md"
  ".memory/phase2-hicache-design/work/TOKENIZER-PROVENANCE-RESOLUTION-20260916.md"
  "python/sglang/_version.py"
  "python/sglang/srt/environ.py"
  "python/sglang/srt/managers/scheduler_components/output_streamer.py"
  "python/sglang/srt/managers/tokenizer_manager.py"
  "python/sglang/srt/mem_cache/cpp_radix_tree/.clang-format"
  "python/sglang/srt/mem_cache/unified_radix_cache.py"
  "python/sglang/srt/observability/hicache_telemetry.py"
  "sgl-model-gateway/LICENSE"
  "test/registered/unit/observability/test_hicache_request_telemetry.py"
  "test/registered/unit/observability/test_output_streamer_hicache_telemetry_wiring.py"
)

# Group B files (absent from HEAD and worktree, only in frozen)
GROUP_B=(
  "python/sglang/srt/configs/qwen3_5.py"
  "python/sglang/srt/layers/quantization/gguf.py"
  "python/sglang/srt/mem_cache/storage/extent/extent_allocator.py"
  "python/sglang/srt/model_loader/gguf_name_maps.py"
  "python/sglang/srt/model_loader/loader.py"
  "python/sglang/srt/model_loader/weight_utils.py"
  "python/sglang/srt/models/qwen3_5.py"
  "python/sglang/srt/models/qwen3_5_text.py"
  "python/sglang/srt/utils/hf_transformers/gguf_native.py"
)

# Group C files (divergent worktree)
GROUP_C=(
  "python/sglang/srt/mem_cache/storage/extent/extent_file_backend.py"
  "test/registered/unit/mem_cache/test_extent_file_backend_unit.py"
)

echo "--- Group A (worktree modified/untracked) ---"
for f in "${GROUP_A[@]}"; do
  HEAD_HASH="N/A (untracked or modified)"
  if git ls-files --error-unmatch "$f" 2>/dev/null; then
    HEAD_HASH=$(git hash-object "$f" 2>/dev/null || echo "HEAD_ERROR")
  fi
  # Worktree hash
  WT_HASH=$(sha256sum "$f" 2>/dev/null | awk '{print $1}')
  # Frozen hash (frozen has src/ prefix)
  FROZEN_HASH=$(sha256sum "$FROZEN/$f" 2>/dev/null | awk '{print $1}')
  # Frozen v1.1 hash (v1.1 is at /opt/sglang/local-prod-v1.1.2-candidate/src but we need v1.1 specifically)
  # The task says frozen v1.1.2 is at /opt/sglang/local-prod-v1.1.2-candidate/src
  # and v1.1 is a different path. Let me check what's available.
  echo "FILE: $f | HEAD: $HEAD_HASH | WORKTREE: $WT_HASH | FROZEN_v1.1.2: $FROZEN_HASH"
done

echo ""
echo "--- Group B (frozen-only) ---"
for f in "${GROUP_B[@]}"; do
  HEAD_HASH="ABSENT"
  WT_HASH="ABSENT"
  FROZEN_HASH=$(sha256sum "$FROZEN/$f" 2>/dev/null | awk '{print $1}')
  echo "FILE: $f | HEAD: $HEAD_HASH | WORKTREE: $WT_HASH | FROZEN_v1.1.2: $FROZEN_HASH"
done

echo ""
echo "--- Group C (divergent) ---"
for f in "${GROUP_C[@]}"; do
  HEAD_HASH=$(git hash-object "$f" 2>/dev/null || echo "HEAD_ERROR")
  WT_HASH=$(sha256sum "$f" 2>/dev/null | awk '{print $1}')
  FROZEN_HASH=$(sha256sum "$FROZEN/$f" 2>/dev/null | awk '{print $1}')
  echo "FILE: $f | HEAD: $HEAD_HASH | WORKTREE: $WT_HASH | FROZEN_v1.1.2: $FROZEN_HASH"
done

# Also check: does frozen v1.1 exist?
echo ""
echo "=== Checking for v1.1 path ==="
ls -la /opt/sglang/ 2>/dev/null
ls /opt/sglang/local-prod-v1.1.2-candidate/ 2>/dev/null

# Check if there's a v1.1 tree
find /opt/sglang/ -maxdepth 2 -name "*.py" -path "*qwen3_5*" 2>/dev/null | head -5
