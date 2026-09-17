#!/usr/bin/env python3
"""Read-only repo-vs-frozen gap classifier. No writes outside /tmp/opencode/reconcile-20260917."""
import hashlib, json, os, sys, subprocess

REPO = "/home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt"
FROZEN = "/opt/sglang/local-prod-v1.1.2-candidate/src"
HEAD = "/tmp/opencode/reconcile-20260917/head"
OUT = "/tmp/opencode/reconcile-20260917"

def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()

# repo-relative path -> frozen path mapping
def repo_to_frozen(rel):
    if rel.startswith("python/sglang/"):
        return "python/sglang/" + rel[len("python/sglang/"):]
    if rel.startswith("test/"):
        return "test/" + rel[len("test/"):]
    return rel

# Collect repo HEAD tracked files (already extracted), repo worktree files, frozen files
def walk(root, prefix):
    out = {}
    base = os.path.join(root, prefix)
    for dp, dns, fns in os.walk(base):
        dns[:] = [d for d in dns if d not in ("__pycache__", ".pytest_cache")]
        for fn in fns:
            full = os.path.join(dp, fn)
            if not os.path.isfile(full):
                continue
            rel = os.path.relpath(full, root)
            out[rel] = full
    return out

head_files = {}
head_files.update(walk(HEAD, "python/sglang"))
head_files.update(walk(HEAD, "test"))
wt_files = {}
wt_files.update(walk(REPO, "python/sglang"))
wt_files.update(walk(REPO, "test"))
fz_files = {}
fz_files.update(walk(FROZEN, "python/sglang"))
fz_files.update(walk(FROZEN, "test"))

# Precompute hashes
head_hash = {r: sha(p) for r, p in head_files.items()}
wt_hash = {r: sha(p) for r, p in wt_files.items()}
fz_hash = {r: sha(p) for r, p in fz_files.items()}

rows = []
# universe = union of repo (HEAD/worktree) and frozen paths
all_rel = sorted(set(head_files) | set(wt_files) | set(fz_files))
for rel in all_rel:
    in_head = rel in head_files
    in_wt = rel in wt_files
    in_fz = rel in fz_files
    fh = head_hash.get(rel)
    wh = wt_hash.get(rel)
    zh = fz_hash.get(rel)
    if in_fz and not in_head:
        status = "d_frozen_absent_from_git"
    elif in_head and not in_fz:
        status = "e_repo_absent_from_frozen"
    elif in_fz and in_head:
        if zh == fh:
            status = "a_frozen_equals_HEAD"
        elif in_wt and zh == wh:
            status = "b_frozen_equals_worktree_only"
        else:
            status = "c_frozen_differs_from_both"
    else:
        status = "e_repo_absent_from_frozen"
    rows.append({
        "path": rel,
        "status": status,
        "frozen_sha256": zh,
        "head_sha256": fh,
        "worktree_sha256": wh,
        "in_head": in_head,
        "in_worktree": in_wt,
        "in_frozen": in_fz,
        "frozen_path": repo_to_frozen(rel),
    })

counts = {}
for r in rows:
    counts[r["status"]] = counts.get(r["status"], 0) + 1

report = {
    "generated_from": {
        "repo": REPO,
        "repo_branch": "3090-24g-opt",
        "repo_head": subprocess.check_output(["git", "-C", REPO, "rev-parse", "HEAD"]).decode().strip(),
        "frozen_tree": "/opt/sglang/local-prod-v1.1.2-candidate",
        "frozen_src": FROZEN,
        "identity": "LOCAL-PROD-v1.1.2",
        "scanned": ["python/sglang/**", "test/**"],
        "excluded": ["__pycache__", ".pytest_cache"],
    },
    "counts": counts,
    "total_rows": len(rows),
    "files": rows,
}
os.makedirs(OUT, exist_ok=True)
with open(os.path.join(OUT, "repo-vs-frozen-gap.json"), "w") as f:
    json.dump(report, f, indent=1, sort_keys=False)

print(json.dumps(counts, indent=2))
print("total rows:", len(rows))
for st in ("c_frozen_differs_from_both", "d_frozen_absent_from_git", "e_repo_absent_from_frozen", "b_frozen_equals_worktree_only"):
    print("\n===", st, "===")
    for r in rows:
        if r["status"] == st:
            print(" ", r["path"])
