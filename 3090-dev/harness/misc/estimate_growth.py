import json
import os
import subprocess

m = json.load(open("/tmp/blind24_dataset_image_refs.json"))


def ghcr_ref(dh):
    tail = dh.split("sweb.eval.x86_64.")[1]  # e.g. astropy_1776_astropy-12907:latest
    return "ghcr.io/epoch-research/swe-bench.eval.x86_64." + tail.replace("_1776_", "__")


gh = sorted(ghcr_ref(dh) for dh in m.values())
print("n refs", len(gh))
blobdir = "/var/lib/containerd/io.containerd.content.v1.content/blobs/sha256"
try:
    existing = set(os.listdir(blobdir))
except PermissionError:
    existing = set(
        os.fsdecode(x)
        for x in subprocess.run(["sudo", "ls", blobdir], capture_output=True, text=True)
        .stdout.splitlines()
    )
print("existing blobs", len(existing))
tot = 0.0
missed = 0.0
nblob = 0
nmiss = 0
for r in sorted(gh):
    out = subprocess.run(["docker", "manifest", "inspect", r], capture_output=True, text=True)
    if out.returncode != 0:
        print("MANIFEST FAIL", r, out.stderr.strip()[:200])
        continue
    man = json.loads(out.stdout)
    if "layers" not in man:
        print("NOT A MANIFEST", r, man.get("mediaType"))
        continue
    s = sum(L["size"] for L in man["layers"])
    tot += s
    nblob += len(man["layers"])
    for L in man["layers"]:
        if L["digest"].split(":")[1] not in existing:
            missed += L["size"]
            nmiss += 1
    name = r.split("swe-bench.eval.x86_64.")[1]
    print("%-58s %6.2f GB" % (name, s / 1e9))
print("TOTAL compressed all layers   = %.2f GB (%d blobs)" % (tot / 1e9, nblob))
print("INCREMENTAL missing blobs     = %.2f GB (%d blobs)" % (missed / 1e9, nmiss))
