import json
import os
import re
import subprocess
import sys
import time

MAPPING = "/tmp/blind24_dataset_image_refs.json"
RESULTS = "/tmp/blind24-pull-results.json"
LOG = "/tmp/blind24-pull.log"
MIN_FREE_GB = 6.0


def free_gb(path):
    st = os.statvfs(path)
    return st.f_bavail * st.f_frsize / 1e9


def log(msg):
    line = "[%s] %s" % (time.strftime("%H:%M:%S"), msg)
    print(line, flush=True)
    with open(LOG, "a") as f:
        f.write(line + "\n")


def ghcr_ref(dh):
    tail = dh.split("sweb.eval.x86_64.")[1]
    return "ghcr.io/epoch-research/swe-bench.eval.x86_64." + tail.replace("_1776_", "__")


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def main():
    mapping = json.load(open(MAPPING))
    results = []
    for inst in sorted(mapping):
        dhref = mapping[inst]
        ghref = ghcr_ref(dhref)
        fg = free_gb("/")
        log("PULL %s -> %s (root free %.1f GB)" % (inst, ghref, fg))
        if fg < MIN_FREE_GB:
            log("ABORT: root free %.2f GB < floor %.2f GB before %s" % (fg, MIN_FREE_GB, inst))
            results.append({"instance_id": inst, "status": "aborted_low_disk", "root_free_gb": fg})
            break
        t0 = time.time()
        p = run(["docker", "pull", ghref])
        dt = time.time() - t0
        if p.returncode != 0:
            log("PULL FAILED %s: %s" % (ghref, p.stderr.strip()[-400:]))
            results.append({"instance_id": inst, "status": "pull_failed",
                            "ghcr_ref": ghref, "error": p.stderr.strip()[-400:]})
            break
        digest = None
        m = re.search(r"Digest:\s*(sha256:[0-9a-f]{64})", p.stdout)
        if m:
            digest = m.group(1)
        insp = run(["docker", "image", "inspect", ghref,
                    "--format", "{{json .RepoDigests}}|{{.Id}}|{{.Size}}"])
        repodigests, image_id, size = insp.stdout.strip().split("|")
        repodigests = json.loads(repodigests)
        gh_dig = next((d for d in repodigests if d.startswith("ghcr.io/epoch-research/")), None)
        if not digest and gh_dig:
            digest = "sha256:" + gh_dig.split("@sha256:")[1]

        tagp = run(["docker", "tag", ghref, dhref])
        if tagp.returncode != 0:
            log("TAG FAILED %s -> %s: %s" % (ghref, dhref, tagp.stderr.strip()[-300:]))
            results.append({"instance_id": inst, "status": "tag_failed", "ghcr_ref": ghref,
                            "dataset_ref": dhref, "error": tagp.stderr.strip()[-300:]})
            break
        fg2 = free_gb("/")
        log("  ok digest=%s size=%s bytes dt=%.1fs root_free=%.1fGB" % (digest, size, dt, fg2))
        results.append({
            "instance_id": inst,
            "status": "pulled",
            "ghcr_ref": ghref,
            "dataset_ref": dhref,
            "image_digest": digest,
            "image_id": image_id,
            "size_bytes": int(size),
            "root_free_gb_after": round(fg2, 2),
            "pull_seconds": round(dt, 1),
        })
    json.dump(results, open(RESULTS, "w"), indent=2)
    ok = sum(1 for r in results if r.get("status") == "pulled")
    log("DONE pulled=%d/%d results=%s" % (ok, len(mapping), RESULTS))
    if ok != len(mapping):
        sys.exit(2)


if __name__ == "__main__":
    main()
