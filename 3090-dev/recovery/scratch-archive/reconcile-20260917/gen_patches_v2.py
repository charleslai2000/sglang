import subprocess
import os
import shutil

REPO = "/home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt"
FROZEN = "/opt/sglang/local-prod-v1.1.2-candidate/src"
OUT = "/tmp/opencode/reconcile-20260917"

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

group_c = [
    "python/sglang/srt/mem_cache/storage/extent/extent_file_backend.py",
    "test/registered/unit/mem_cache/test_extent_file_backend_unit.py",
]

os.makedirs(OUT, exist_ok=True)

def gen_patch(output_path, file_list, label_a, label_b, get_file_a, get_file_b):
    """Generate a clean unified diff patch."""
    with open(output_path, "w") as out:
        out.write(f"# Patch: {label_a} -> {label_b}\n")
        out.write(f"# Generated: 2026-09-17\n")
        out.write(f"# Files: {len(file_list)}\n")
        out.write("#\n")
        
        for f in file_list:
            a_path = get_file_a(f)
            b_path = get_file_b(f)
            
            result = subprocess.run(
                ["diff", "-u", a_path, b_path,
                 "--label", f"a/{f}",
                 "--label", f"b/{f}"],
                capture_output=True, text=True
            )
            
            out.write(f"\n{'='*60}\n")
            out.write(f"# FILE: {f}\n")
            out.write(f"{'='*60}\n")
            out.write(result.stdout)
            out.write("\n")

# B patch: HEAD content -> frozen v1.1.2
def get_head_file(f):
    """Get HEAD version of file as temp file."""
    tmp = f"/tmp/opencode/reconcile-20260917/head_{f.replace('/', '_')}"
    result = subprocess.run(
        ["git", "show", f"HEAD:{f}"],
        capture_output=True, cwd=REPO
    )
    with open(tmp, "wb") as fh:
        fh.write(result.stdout)
    return tmp

def get_frozen_file(f):
    return os.path.join(FROZEN, f)

gen_patch(
    f"{OUT}/B-frozen-only.patch",
    group_b,
    "HEAD", "frozen v1.1.2",
    get_head_file, get_frozen_file
)

# C patch: worktree -> frozen v1.1.2
def get_wt_file(f):
    return os.path.join(REPO, f)

gen_patch(
    f"{OUT}/C-provenance.patch",
    group_c,
    "worktree", "frozen v1.1.2",
    get_wt_file, get_frozen_file
)

print("Patches regenerated with clean labels.")

# Now test applying the C patch on a temp copy
print("\n=== Testing C patch apply ===")
test_dir = "/tmp/opencode/test-apply-c"
if os.path.exists(test_dir):
    shutil.rmtree(test_dir)
shutil.copytree(REPO, test_dir)

result = subprocess.run(
    ["git", "apply", "--check", f"{OUT}/C-provenance.patch"],
    cwd=test_dir, capture_output=True, text=True
)
print(f"C patch dry-run check: exit={result.returncode}")
if result.returncode != 0:
    print(f"stderr: {result.stderr[:500]}")

# Try actual apply
result = subprocess.run(
    ["git", "apply", f"{OUT}/C-provenance.patch"],
    cwd=test_dir, capture_output=True, text=True
)
print(f"C patch actual apply: exit={result.returncode}")
if result.returncode != 0:
    print(f"stderr: {result.stderr[:500]}")
else:
    # Verify the applied file matches frozen
    import hashlib
    def sha256(p):
        with open(p, 'rb') as fh:
            return hashlib.sha256(fh.read()).hexdigest()
    
    for f in group_c:
        applied = os.path.join(test_dir, f)
        frozen = os.path.join(FROZEN, f)
        applied_h = sha256(applied)
        frozen_h = sha256(frozen)
        print(f"  {f}: applied==frozen ? {applied_h == frozen_h}")

# Clean up test dir
shutil.rmtree(test_dir)

# Test B patch on a temp copy
print("\n=== Testing B patch apply ===")
test_dir = "/tmp/opencode/test-apply-b"
if os.path.exists(test_dir):
    shutil.rmtree(test_dir)
shutil.copytree(REPO, test_dir)

result = subprocess.run(
    ["git", "apply", "--check", f"{OUT}/B-frozen-only.patch"],
    cwd=test_dir, capture_output=True, text=True
)
print(f"B patch dry-run check: exit={result.returncode}")
if result.returncode != 0:
    print(f"stderr: {result.stderr[:500]}")

# Try actual apply
result = subprocess.run(
    ["git", "apply", f"{OUT}/B-frozen-only.patch"],
    cwd=test_dir, capture_output=True, text=True
)
print(f"B patch actual apply: exit={result.returncode}")
if result.returncode != 0:
    print(f"stderr: {result.stderr[:500]}")
else:
    import hashlib
    def sha256(p):
        with open(p, 'rb') as fh:
            return hashlib.sha256(fh.read()).hexdigest()
    
    for f in group_b:
        applied = os.path.join(test_dir, f)
        frozen = os.path.join(FROZEN, f)
        applied_h = sha256(applied)
        frozen_h = sha256(frozen)
        print(f"  {f}: applied==frozen ? {applied_h == frozen_h}")

shutil.rmtree(test_dir)

