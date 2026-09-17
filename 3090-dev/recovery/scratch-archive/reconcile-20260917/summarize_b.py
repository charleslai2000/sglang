import subprocess
import os

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

summaries = {}

for f in group_b:
    frozen_path = os.path.join(FROZEN, f)
    result = subprocess.run(
        ["git", "show", f"HEAD:{f}"],
        capture_output=True, cwd=REPO
    )
    head_content = result.stdout
    
    with open(frozen_path, "rb") as fh:
        frozen_content = fh.read()
    
    head_tmp = f"/tmp/opencode/reconcile-20260917/head_{f.replace('/', '_')}"
    frozen_tmp = f"/tmp/opencode/reconcile-20260917/frozen_{f.replace('/', '_')}"
    
    with open(head_tmp, "wb") as fh:
        fh.write(head_content)
    with open(frozen_tmp, "wb") as fh:
        fh.write(frozen_content)
    
    # Get diff stat
    result = subprocess.run(
        ["diff", "-u", head_tmp, frozen_tmp],
        capture_output=True, text=True
    )
    
    # Count lines added/removed
    added = 0
    removed = 0
    for line in result.stdout.split('\n'):
        if line.startswith('+') and not line.startswith('+++'):
            added += 1
        elif line.startswith('-') and not line.startswith('---'):
            removed += 1
    
    # Get first few meaningful lines of context to understand what it does
    # Look for function/class names and key comments
    context_lines = []
    for line in result.stdout.split('\n'):
        if line.startswith('+') and not line.startswith('+++'):
            stripped = line[1:].strip()
            if stripped and not stripped.startswith('#') and not stripped.startswith('//'):
                context_lines.append(stripped)
                if len(context_lines) >= 8:
                    break
    
    summaries[f] = {
        "added_lines": added,
        "removed_lines": removed,
        "net_change": added - removed,
        "sample_context": context_lines[:5],
    }

# Print summary
for f, info in summaries.items():
    print(f"\n=== {f} ===")
    print(f"  Lines: +{info['added_lines']}/-{info['removed_lines']} (net {info['net_change']:+d})")
    print(f"  Sample context: {info['sample_context']}")

# Save as JSON
import json
with open(f"{OUT}/B-summaries.json", "w") as fh:
    json.dump(summaries, fh, indent=2)

