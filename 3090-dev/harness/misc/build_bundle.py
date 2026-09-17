#!/usr/bin/env python3
"""Build the minimal forensic bundle for task l3-disk-reclaim-20260916.

Copies the small evidence files (preserving names and modes), records sha256
identity of every retained file, and records the identity of the two 64 GiB
hicache.data_* payload files (size + first/last 64 KiB sha256) that are NOT kept.
"""
import hashlib, json, os, shutil, stat, time

BUNDLE = "/var/log/sglang/local-prod-v1/phase8/l3-forensic-bundle-20260916"
GROUPS = {
    "fleet-forensics-v2-20260916": {
        "src": "/data/l3/fleet-forensics-v2-20260916",
        "retain": [
            "hicache.meta_-data-models-qwen35-9b-w4a16_0_1.manifest",
            "hicache.meta_-data-models-qwen35-9b-w4a16_0_1.wal.7",
            "hicache.meta_-data-models-qwen35-9b-w4a16_0_1.manifest.tmp.03wo4fnz",
            "hicache.meta_-data-models-qwen35-9b-w4a16_0_1.manifest.tmp.akjcesqj",
            "hicache.meta_-data-models-qwen35-9b-w4a16_0_1.wal.current",
            "hicache.meta_-data-models-qwen35-9b-w4a16_0_1.lock",
        ],
        "data": ["hicache.data_-data-models-qwen35-9b-w4a16_0_1"],
    },
    "local-prod-v1": {
        "src": "/data/l3/local-prod-v1",
        "retain": [
            "hicache.meta_-data-models-qwen35-9b-w4a16_0_1.manifest",
            "hicache.meta_-data-models-qwen35-9b-w4a16_0_1.wal.current",
            "hicache.meta_-data-models-qwen35-9b-w4a16_0_1.lock",
        ],
        "data": ["hicache.data_-data-models-qwen35-9b-w4a16_0_1"],
        # wal.0 is documented but NOT retained (see README / decision)
        "document_only": ["hicache.meta_-data-models-qwen35-9b-w4a16_0_1.wal.0"],
    },
}

def sha256_file(path, limit=None, offset=None):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        if offset is not None:
            f.seek(offset)
        remaining = limit
        while True:
            n = 1024 * 1024 if remaining is None else min(1024 * 1024, remaining)
            if n <= 0:
                break
            b = f.read(n)
            if not b:
                break
            h.update(b)
            if remaining is not None:
                remaining -= len(b)
    return h.hexdigest()

def sample_sha(path, size, span=65536):
    first = sha256_file(path, limit=min(span, size), offset=0)
    last_off = max(0, size - span)
    last = sha256_file(path, limit=min(span, size), offset=last_off)
    return first, last

os.makedirs(BUNDLE, exist_ok=True)
identity = {
    "task": "l3-disk-reclaim-20260916",
    "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "bundle": BUNDLE,
    "retained": [],
    "payload_identity_not_retained": [],
    "document_only_not_retained": [],
}

for gname, g in GROUPS.items():
    dst = os.path.join(BUNDLE, gname)
    os.makedirs(dst, exist_ok=True)
    for name in g["retain"]:
        src = os.path.join(g["src"], name)
        dpath = os.path.join(dst, name)
        st = os.stat(src)
        pre = sha256_file(src)
        shutil.copy2(src, dpath)
        post = sha256_file(dpath)
        assert pre == post, (src, pre, post)
        identity["retained"].append({
            "bundle_relpath": f"{gname}/{name}",
            "source": src,
            "size": st.st_size,
            "mtime_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(st.st_mtime)),
            "mode": oct(stat.S_IMODE(st.st_mode)),
            "sha256": pre,
        })
    for name in g["data"]:
        src = os.path.join(g["src"], name)
        st = os.stat(src)
        first, last = sample_sha(src, st.st_size)
        identity["payload_identity_not_retained"].append({
            "source": src,
            "size": st.st_size,
            "mtime_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(st.st_mtime)),
            "first_65536_sha256": first,
            "last_65536_sha256": last,
        })
    for name in g.get("document_only", []):
        src = os.path.join(g["src"], name)
        st = os.stat(src)
        identity["document_only_not_retained"].append({
            "source": src,
            "size": st.st_size,
            "mtime_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(st.st_mtime)),
            "sha256": sha256_file(src),
        })

with open(os.path.join(BUNDLE, "MANIFEST-IDENTITY.json"), "w") as f:
    json.dump(identity, f, indent=2)
    f.write("\n")

with open(os.path.join(BUNDLE, "MANIFEST-IDENTITY.txt"), "w") as f:
    f.write("MANIFEST-IDENTITY — l3-disk-reclaim-20260916\n")
    f.write(f"created_utc: {identity['created_utc']}\n\n")
    f.write("RETAINED FILES (copied into bundle; sha256 == original)\n")
    for r in identity["retained"]:
        f.write(f"{r['sha256']}  {r['size']:>12}  {r['mtime_utc']}  {r['mode']}  {r['bundle_relpath']}\n")
    f.write("\nPAYLOAD FILES NOT RETAINED (identity pinned by size + first/last 64KiB sha256)\n")
    for r in identity["payload_identity_not_retained"]:
        f.write(f"{r['source']}\n")
        f.write(f"  size={r['size']} mtime={r['mtime_utc']}\n")
        f.write(f"  first_65536_sha256={r['first_65536_sha256']}\n")
        f.write(f"  last_65536_sha256={r['last_65536_sha256']}\n")
    f.write("\nDOCUMENT-ONLY FILES NOT RETAINED (size + full sha256)\n")
    for r in identity["document_only_not_retained"]:
        f.write(f"{r['sha256']}  {r['size']:>12}  {r['mtime_utc']}  {r['source']}\n")

print(json.dumps({k: len(v) for k, v in identity.items() if isinstance(v, list)}, indent=2))
print("bundle:", BUNDLE)
