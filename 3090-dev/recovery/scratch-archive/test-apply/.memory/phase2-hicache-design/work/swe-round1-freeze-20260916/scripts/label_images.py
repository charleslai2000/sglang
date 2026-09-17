#!/usr/bin/env python3
"""Surface the CALIBRATION / BLIND classification as local docker tags.

Docker image labels are immutable at build time, so the authoritative mapping is
in the frozen manifest; this adds a visible local tag on VM901:
  * calibration: swe-calibration/<repo>_1776_<inst>:non-scored
  * blind R1   : swe-blind-round1/<repo>_1776_<inst>:scored
and records the digest for each so the manifest can carry digest -> label.

Inputs: /tmp/calibration_images.tsv (instance_id<TAB>ghcr_ref),
        /tmp/blind24-verify.json
Output: /tmp/calibration-details.json, /tmp/blind-details.json
"""

import json
import subprocess


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)


def tag_and_inspect(inst, src, tag, label):
    p = run(["docker", "tag", src, tag])
    if p.returncode != 0:
        return {"instance_id": inst, "tag": tag, "status": "tag_failed",
                "error": p.stderr.strip()[-200:]}
    i = run(["docker", "image", "inspect", tag, "--format", "{{json .RepoDigests}}|{{.Id}}|{{.Size}}"])
    rd, iid, size = i.stdout.strip().split("|")
    rd = json.loads(rd)
    digest = next((d.split("@sha256:")[1] for d in rd if d.startswith("ghcr.io/epoch-research/")), None)
    return {"instance_id": inst, "classification": label, "source_ref": src, "local_tag": tag,
            "image_digest": "sha256:" + digest if digest else None, "image_id": iid,
            "size_bytes": int(size), "status": "tagged"}


def main():
    cal, blind = [], []
    for line in open("/tmp/calibration_images.tsv"):
        if not line.strip():
            continue
        inst, ref = line.rstrip("\n").split("\t")
        tail = ref.split("swe-bench.eval.x86_64.")[1].split(":")[0]  # already repo__inst
        tag = "swe-calibration/%s:non-scored" % tail
        cal.append(tag_and_inspect(inst, ref, tag, "CALIBRATION / NON-SCORED"))
    for v in json.load(open("/tmp/blind24-verify.json")):
        tail = v["ghcr_ref"].split("swe-bench.eval.x86_64.")[1].split(":")[0]
        tag = "swe-blind-round1/%s:scored" % tail
        blind.append(tag_and_inspect(v["instance_id"], v["ghcr_ref"], tag, "BLIND ROUND-1 / SCORED"))
    json.dump(cal, open("/tmp/calibration-details.json", "w"), indent=2)
    json.dump(blind, open("/tmp/blind-details.json", "w"), indent=2)
    print("calibration tagged=%d/%d  blind tagged=%d/%d" % (
        sum(1 for x in cal if x["status"] == "tagged"), len(cal),
        sum(1 for x in blind if x["status"] == "tagged"), len(blind)))
    print("calibration no-image (expected): psf__requests-1921")


if __name__ == "__main__":
    main()
