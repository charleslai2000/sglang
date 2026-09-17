#!/usr/bin/env python3
import json, os, hashlib
OUT="/tmp/opencode/reconcile-20260917"
d=json.load(open(os.path.join(OUT,"repo-vs-frozen-gap.json")))
for r in d["files"]:
    r["worktree_equals_head"] = (r["head_sha256"] is not None and r["head_sha256"]==r["worktree_sha256"])
    r["is_generated_or_build"] = r["path"].endswith(("_version.py",".so"))
d["counts"]["symlink_present_in_both"] = 1
d["notes"] = [
 "Symlink python/sglang/srt/mem_cache/cpp_radix_tree/.clang-format -> ../../../kernels/aot/.clang-format is present+identical in repo and frozen (not a gap; walks skip symlinks).",
 "Group c splits into two causes: (c1) GGUF/norm production fixes that exist only in frozen and NOT in any git object; (c2) extent Option-C/WAL production fixes.",
 "python/sglang/_version.py and rust_extensions/*.so are gitignored generated/build byproducts, not source gaps.",
]
json.dump(d, open(os.path.join(OUT,"repo-vs-frozen-gap.json"),"w"), indent=1)

c={r["path"]:r for r in d["files"]}
print("=== group c detail ===")
for p,r in sorted(c.items()):
    if r["status"]=="c_frozen_differs_from_both":
        print(f"  {p}\n     wt==HEAD: {r['worktree_equals_head']}")
print("=== group b detail ===")
for p,r in sorted(c.items()):
    if r["status"]=="b_frozen_equals_worktree_only":
        print(" ",p)
