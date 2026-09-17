import subprocess
import os
import json

REPO = "/home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt"
FROZEN = "/opt/sglang/local-prod-v1.1.2-candidate/src"
FROZEN_V11 = "/opt/sglang/local-prod-v1.1-candidate/src"
OPTIONC = "/tmp/opencode/v1.1.2-optionC-20260917/src"
OUT = "/tmp/opencode/reconcile-20260917"

# ============================================================
# 1. Verify groups and produce file-status.json
# ============================================================

# Read the hashes we already computed
with open(f"{OUT}/hashes_raw.json") as f:
    hashes = json.load(f)

# Build file-status.json with all four sources
file_status = {}

# Group A files
group_a = [
    ".dockerignore",
    ".memory/phase2-hicache-design/work/ARTIFACT-CAPABILITY-INVENTORY-20260916.md",
    ".memory/phase2-hicache-design/work/OPEN4-SHIM-NECESSITY-VERDICT-20260916.md",
    ".memory/phase2-hicache-design/work/TOKENIZER-PROVENANCE-RESOLUTION-20260916.md",
    "python/sglang/_version.py",
    "python/sglang/srt/environ.py",
    "python/sglang/srt/managers/scheduler_components/output_streamer.py",
    "python/sglang/srt/managers/tokenizer_manager.py",
    "python/sglang/srt/mem_cache/cpp_radix_tree/.clang-format",
    "python/sglang/srt/mem_cache/unified_radix_cache.py",
    "python/sglang/srt/observability/hicache_telemetry.py",
    "sgl-model-gateway/LICENSE",
    "test/registered/unit/observability/test_hicache_request_telemetry.py",
    "test/registered/unit/observability/test_output_streamer_hicache_telemetry_wiring.py",
]

# Group B files
group_b = [
    "python/sglang/srt/configs/qwen3_5.py",
    "python/sglang/srt/layers/quantization/gguf.py",
    "python/sglang/srt/mem_cache/storage/extent/extent_allocator.py",
    "python/sglang/srt/model_loader/gguf_name_maps.py",
    "python/sglang/srt/model_loader/loader.py",
    "python/sglang/srt/model_loader/weight_utils.py",
    "python/sglang/srt/models/qwen3_5.py",
    "python/sglang/srt/models/qwen3_5_text.py",
    "python/sglang/srt/utils/hf_transformers/gguf_native.py",
]

# Group C files
group_c = [
    "python/sglang/srt/mem_cache/storage/extent/extent_file_backend.py",
    "test/registered/unit/mem_cache/test_extent_file_backend_unit.py",
]

# Verify each group
print("=== GROUP A VERIFICATION ===")
for f in group_a:
    h = hashes.get(f, {})
    wt_match = h.get("worktree_sha256") == h.get("frozen_v1.1.2_sha256")
    print(f"  {f}: worktree==frozen_v1.1.2 ? {wt_match} (wt={h.get('worktree_sha256','?')[:16]}...)")

print("\n=== GROUP B VERIFICATION ===")
for f in group_b:
    h = hashes.get(f, {})
    wt_absent = h.get("worktree_sha256") is None
    head_differs = h.get("head_sha256") != h.get("frozen_v1.1.2_sha256")
    print(f"  {f}: worktree_absent={wt_absent}, head_differs_from_frozen={head_differs}")

print("\n=== GROUP C VERIFICATION ===")
for f in group_c:
    h = hashes.get(f, {})
    wt_differs_frozen = h.get("worktree_sha256") != h.get("frozen_v1.1.2_sha256")
    wt_differs_head = h.get("worktree_sha256") != h.get("head_sha256")
    print(f"  {f}: wt!=frozen={wt_differs_frozen}, wt!=head={wt_differs_head}")
    print(f"    head={h.get('head_sha256','?')[:16]}... wt={h.get('worktree_sha256','?')[:16]}... frozen={h.get('frozen_v1.1.2_sha256','?')[:16]}...")

# ============================================================
# 2. Verify Option-C cross-check
# ============================================================
print("\n=== OPTION C CROSS-CHECK ===")
for f in group_b:
    optc_path = os.path.join(OPTIONC, f)
    frozen_path = os.path.join(FROZEN, f)
    if os.path.exists(optc_path) and os.path.exists(frozen_path):
        import hashlib
        def sha256(p):
            with open(p, 'rb') as fh:
                return hashlib.sha256(fh.read()).hexdigest()
        optc_h = sha256(optc_path)
        frozen_h = sha256(frozen_path)
        match = optc_h == frozen_h
        print(f"  {f}: frozen == optionC ? {match}")

# ============================================================
# 3. Read the C diffs to understand the missing hunk
# ============================================================
print("\n=== GROUP C: extent_file_backend.py diff ===")
result = subprocess.run(
    ["diff", "-u",
     "-L", "worktree",
     "-L", "frozen-v1.1.2",
     os.path.join(REPO, "python/sglang/srt/mem_cache/storage/extent/extent_file_backend.py"),
     os.path.join(FROZEN, "python/sglang/srt/mem_cache/storage/extent/extent_file_backend.py")],
    capture_output=True, text=True, cwd=REPO
)
# Find the specific hunk around line 2163 (v1.1) / 2337 (v1.1.2)
for line in result.stdout.split('\n'):
    if "wal_recovered_next_seq" in line or "checkpoint" in line.lower() or line.startswith("@@"):
        print(line)

# ============================================================
# 4. Get merge info
# ============================================================
print("\n=== MERGE TOPOLOGY ===")
result = subprocess.run(
    ["git", "merge-base", "ad749d6f28", "origin/3090-24g-hicache"],
    capture_output=True, text=True, cwd=REPO
)
print(f"Merge-base: {result.stdout.strip()}")

# Get commit counts on each side since merge-base
result = subprocess.run(
    ["git", "log", "--oneline", "34bd2ed49f..ad749d6f28"],
    capture_output=True, text=True, cwd=REPO
)
opt_commits = result.stdout.strip().split('\n')
print(f"3090-24g-opt commits since merge-base: {len(opt_commits)}")
for c in opt_commits:
    print(f"  {c}")

result = subprocess.run(
    ["git", "log", "--oneline", "34bd2ed49f..origin/3090-24g-hicache"],
    capture_output=True, text=True, cwd=REPO
)
hicache_commits = result.stdout.strip().split('\n')
print(f"3090-24g-hicache commits since merge-base: {len(hicache_commits)}")
for c in hicache_commits:
    print(f"  {c}")

# ============================================================
# 5. Check what would differ in a fresh clone vs production
# ============================================================
print("\n=== FRESH CLONE vs PRODUCTION ===")
# Check launcher/, manifest/, tools/, env symlink in frozen
for d in ["launcher", "manifest", "tools", "env"]:
    frozen_path = os.path.join(FROZEN, "..", d)
    repo_path = os.path.join(REPO, d)
    frozen_exists = os.path.exists(frozen_path)
    repo_exists = os.path.exists(repo_path)
    print(f"  {d}: frozen={frozen_exists}, repo={repo_exists}")

# Check if there's an env symlink
result = subprocess.run(
    ["ls", "-la", os.path.join(FROZEN, "..")],
    capture_output=True, text=True
)
print(f"\n  Frozen parent dir listing:")
for line in result.stdout.split('\n'):
    if any(x in line for x in ["env", "launcher", "manifest", "tools"]):
        print(f"    {line}")

# Save file-status.json
with open(f"{OUT}/file-status.json", "w") as f:
    json.dump(hashes, f, indent=2)

print("\nfile-status.json written.")

