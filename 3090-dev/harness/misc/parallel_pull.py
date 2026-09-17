import concurrent.futures as cf
import json
import os
import re
import subprocess
import sys
import threading
import time

MAPPING = "/tmp/blind24_dataset_image_refs.json"
RESULTS = "/tmp/blind24-pull-results.json"
LOG = "/tmp/blind24-pull.log"
MIN_FREE_GB = 5.0
WORKERS = int(os.environ.get("PULL_WORKERS", "6"))

lock = threading.Lock()
results = {}
abort = threading.Event()


def free_gb(path="/"):
    st = os.statvfs(path)
    return st.f_bavail * st.f_frsize / 1e9


def log(msg):
    line = "[%s] %s" % (time.strftime("%H:%M:%S"), msg)
    with lock:
        print(line, flush=True)
        with open(LOG, "a") as f:
            f.write(line + "\n")


def ghcr_ref(dh):
    tail = dh.split("sweb.eval.x86_64.")[1]
    return "ghcr.io/epoch-research/swe-bench.eval.x86_64." + tail.replace("_1776_", "__")


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)


def pull_one(inst, dhref):
    ghref = ghcr_ref(dhref)
    if abort.is_set():
        return {"instance_id": inst, "status": "skipped_abort"}
    fg = free_gb()
    if fg < MIN_FREE_GB:
        abort.set()
        log("ABORT low disk %.2f GB before %s" % (fg, inst))
        return {"instance_id": inst, "status": "aborted_low_disk", "root_free_gb": fg}
    last = ""
    for attempt in range(1, 4):
        t0 = time.time()
        p = run(["docker", "pull", ghref])
        dt = time.time() - t0
        if p.returncode == 0:
            break
        last = p.stderr.strip()[-300:]
        log("retry %d %s: %s" % (attempt, inst, last))
        time.sleep(5)
    else:
        return {"instance_id": inst, "status": "pull_failed", "ghcr_ref": ghref, "error": last}
    digest = None
    m = re.search(r"Digest:\s*(sha256:[0-9a-f]{64})", p.stdout)
    if m:
        digest = m.group(1)
    insp = run(["docker", "image", "inspect", ghref,
                "--format", "{{json .RepoDigests}}|{{.Id}}|{{.Size}}"])
    rd, image_id, size = insp.stdout.strip().split("|")
    rd = json.loads(rd)
    ghd = next((d for d in rd if d.startswith("ghcr.io/epoch-research/")), None)
    if not digest and ghd:
        digest = "sha256:" + ghd.split("@sha256:")[1]
    tagp = run(["docker", "tag", ghref, dhref])
    if tagp.returncode != 0:
        return {"instance_id": inst, "status": "tag_failed", "ghcr_ref": ghref,
                "dataset_ref": dhref, "error": tagp.stderr.strip()[-300:]}
    log("ok %-45s digest=%s dt=%.0fs free=%.1fGB" % (inst, (digest or "?")[:20], dt, free_gb()))
    return {"instance_id": inst, "status": "pulled", "ghcr_ref": ghref,
            "dataset_ref": dhref, "image_digest": digest, "image_id": image_id,
            "size_bytes": int(size), "root_free_gb_after": round(free_gb(), 2),
            "pull_seconds": round(dt, 1)}


def main():
    mapping = json.load(open(MAPPING))
    insts = sorted(mapping)
    log("PARALLEL PULL start n=%d workers=%d free=%.1fGB" % (len(insts), WORKERS, free_gb()))
    with cf.ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = {ex.submit(pull_one, i, mapping[i]): i for i in insts}
        for fut in cf.as_completed(futs):
            r = fut.result()
            results[r["instance_id"]] = r
            out = [results[i] for i in insts if i in results]
            json.dump(out, open(RESULTS, "w"), indent=2)
    ok = sum(1 for r in results.values() if r.get("status") == "pulled")
    log("PARALLEL PULL done pulled=%d/%d free=%.1fGB" % (ok, len(insts), free_gb()))
    if ok != len(insts):
        sys.exit(2)


if __name__ == "__main__":
    main()
