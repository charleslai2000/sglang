import hashlib
import os
import json

REPO = "/home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt"
FROZEN_V112 = "/opt/sglang/local-prod-v1.1.2-candidate/src"
FROZEN_V11 = "/opt/sglang/local-prod-v1.1-candidate/src"
FROZEN_V1 = "/opt/sglang/local-prod-v1/src"
OPTIONC = "/tmp/opencode/v1.1.2-optionC-20260917/src"

def sha256_file(path):
    if not os.path.exists(path):
        return None
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()

# Group A files (14)
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

# Group B files (9)
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

# Group C files (2)
group_c = [
    "python/sglang/srt/mem_cache/storage/extent/extent_file_backend.py",
    "test/registered/unit/mem_cache/test_extent_file_backend_unit.py",
]

all_groups = {"A": group_a, "B": group_b, "C": group_c}
results = {}

for group_name, files in all_groups.items():
    for f in files:
        repo_path = os.path.join(REPO, f)
        frozen_v112_path = os.path.join(FROZEN_V112, f)
        frozen_v11_path = os.path.join(FROZEN_V11, f)
        frozen_v1_path = os.path.join(FROZEN_V1, f)
        optionc_path = os.path.join(OPTIONC, f)
        
        # HEAD hash: use git hash-object for tracked files
        head_hash = None
        # We'll compute this separately with git
        
        wt_hash = sha256_file(repo_path)
        frozen_v112_hash = sha256_file(frozen_v112_path)
        frozen_v11_hash = sha256_file(frozen_v11_path)
        frozen_v1_hash = sha256_file(frozen_v1_path)
        optionc_hash = sha256_file(optionc_path)
        
        results[f] = {
            "group": group_name,
            "worktree_sha256": wt_hash,
            "frozen_v1.1.2_sha256": frozen_v112_hash,
            "frozen_v1.1_sha256": frozen_v11_hash,
            "frozen_v1_sha256": frozen_v1_hash,
            "optionc_sha256": optionc_hash,
        }

# Now get HEAD hashes via git
import subprocess
head_hashes = {}
for group_name, files in all_groups.items():
    for f in files:
        # Check if file is tracked in HEAD
        result = subprocess.run(
            ["git", "hash-object", f],
            capture_output=True, text=True,
            cwd=REPO
        )
        if result.returncode == 0:
            head_hashes[f] = result.stdout.strip()
        else:
            head_hashes[f] = "NOT_IN_HEAD"

# Also check git ls-files to confirm which are tracked
tracked_result = subprocess.run(
    ["git", "ls-files"],
    capture_output=True, text=True,
    cwd=REPO
)
tracked_set = set(tracked_result.stdout.strip().split('\n'))

for f in results:
    results[f]["head_sha256"] = head_hashes.get(f, "UNKNOWN")
    results[f]["tracked_in_head"] = f in tracked_set

# Print results
print(json.dumps(results, indent=2))

# Also save to file
with open("/tmp/opencode/reconcile-20260917/hashes_raw.json", "w") as fh:
    json.dump(results, fh, indent=2)

