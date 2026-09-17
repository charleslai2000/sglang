import subprocess
import os

REPO = "/home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt"
FROZEN = "/opt/sglang/local-prod-v1.1.2-candidate/src"
OUT = "/tmp/opencode/reconcile-20260917"

# Group B files - generate diff from HEAD to frozen v1.1.2
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

# Group C files - generate diff from worktree to frozen v1.1.2
group_c = [
    "python/sglang/srt/mem_cache/storage/extent/extent_file_backend.py",
    "test/registered/unit/mem_cache/test_extent_file_backend_unit.py",
]

os.makedirs(OUT, exist_ok=True)

# Generate B patch: HEAD -> frozen v1.1.2
with open(f"{OUT}/B-frozen-only.patch", "w") as out:
    out.write("# Group B: 9 files present ONLY in frozen v1.1.2 (absent from HEAD working tree)\n")
    out.write("# These files exist in HEAD as tracked blobs but with OLDER content.\n")
    out.write("# Patch: HEAD content -> frozen v1.1.2 content\n")
    out.write("# Generated: 2026-09-17\n")
    out.write("#\n")
    
    for f in group_b:
        frozen_path = os.path.join(FROZEN, f)
        # Get HEAD content via git show
        result = subprocess.run(
            ["git", "show", f"HEAD:{f}"],
            capture_output=True, cwd=REPO
        )
        head_content = result.stdout
        
        with open(frozen_path, "rb") as fh:
            frozen_content = fh.read()
        
        # Write temp files for diff
        head_tmp = f"/tmp/opencode/reconcile-20260917/head_{f.replace('/', '_')}"
        frozen_tmp = f"/tmp/opencode/reconcile-20260917/frozen_{f.replace('/', '_')}"
        
        with open(head_tmp, "wb") as fh:
            fh.write(head_content)
        with open(frozen_tmp, "wb") as fh:
            fh.write(frozen_content)
        
        # Generate unified diff
        result = subprocess.run(
            ["diff", "-u", head_tmp, frozen_tmp, f"--label", f"a/{f} (HEAD)", f"--label", f"b/{f} (frozen v1.1.2)"],
            capture_output=True, text=True
        )
        
        out.write(f"\n{'='*60}\n")
        out.write(f"# FILE: {f}\n")
        out.write(f"# HEAD SHA256: {subprocess.run(['sha256sum', head_tmp], capture_output=True, text=True).stdout.split()[0]}\n")
        out.write(f"# FROZEN v1.1.2 SHA256: {subprocess.run(['sha256sum', frozen_tmp], capture_output=True, text=True).stdout.split()[0]}\n")
        out.write(f"{'='*60}\n")
        out.write(result.stdout)
        out.write("\n")

# Generate C provenance patch: worktree -> frozen v1.1.2
with open(f"{OUT}/C-provenance.patch", "w") as out:
    out.write("# Group C: 2 files where worktree holds an OLDER/PARTIAL version\n")
    out.write("# Patch: worktree content -> frozen v1.1.2 content\n")
    out.write("# Generated: 2026-09-17\n")
    out.write("#\n")
    
    for f in group_c:
        repo_path = os.path.join(REPO, f)
        frozen_path = os.path.join(FROZEN, f)
        
        with open(repo_path, "rb") as fh:
            wt_content = fh.read()
        with open(frozen_path, "rb") as fh:
            frozen_content = fh.read()
        
        wt_tmp = f"/tmp/opencode/reconcile-20260917/wt_{f.replace('/', '_')}"
        frozen_tmp = f"/tmp/opencode/reconcile-20260917/frozen_{f.replace('/', '_')}"
        
        with open(wt_tmp, "wb") as fh:
            fh.write(wt_content)
        with open(frozen_tmp, "wb") as fh:
            fh.write(frozen_content)
        
        result = subprocess.run(
            ["diff", "-u", wt_tmp, frozen_tmp, f"--label", f"a/{f} (worktree)", f"--label", f"b/{f} (frozen v1.1.2)"],
            capture_output=True, text=True
        )
        
        out.write(f"\n{'='*60}\n")
        out.write(f"# FILE: {f}\n")
        out.write(f"# WORKTREE SHA256: {subprocess.run(['sha256sum', wt_tmp], capture_output=True, text=True).stdout.split()[0]}\n")
        out.write(f"# FROZEN v1.1.2 SHA256: {subprocess.run(['sha256sum', frozen_tmp], capture_output=True, text=True).stdout.split()[0]}\n")
        out.write(f"{'='*60}\n")
        out.write(result.stdout)
        out.write("\n")

print("Patches generated successfully.")
