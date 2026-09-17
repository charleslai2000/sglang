import json, subprocess, os
ref="ghcr.io/epoch-research/swe-bench.eval.x86_64.sphinx-doc__sphinx-9320:latest"
blobdir="/var/lib/containerd/io.containerd.content.v1.content/blobs/sha256"
existing=set(os.fsdecode(x) for x in subprocess.run(["sudo","ls",blobdir],capture_output=True,text=True).stdout.splitlines())
man=json.loads(subprocess.run(["docker","manifest","inspect",ref],capture_output=True,text=True).stdout)
miss=[(L["size"],L["digest"]) for L in man["layers"] if L["digest"].split(":")[1] not in existing]
print("layers total", len(man["layers"]), "missing", len(miss), "missing_bytes", sum(s for s,_ in miss))
for s,d in sorted(miss, reverse=True): print(f"  {s/1e6:9.1f} MB  {d[:30]}")
