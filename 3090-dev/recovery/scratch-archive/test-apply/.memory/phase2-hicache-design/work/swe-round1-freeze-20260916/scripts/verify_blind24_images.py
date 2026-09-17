#!/usr/bin/env python3
"""Verify the 24 blind images: digest presence + baked-in base_commit vs dataset.

Read-only checks (no model, no GPU):
  * `docker image inspect` -> RepoDigests (pinned digest), Id, Size, labels
  * `docker run --rm --network none --entrypoint git <img> -C /testbed rev-parse HEAD`
    -> the base_commit baked into the image, compared to the pinned dataset value.

Inputs:
  /tmp/blind24_dataset_image_refs.json  {instance_id: dataset 'image' ref}
  /tmp/blind_round1_sample.py310.json   published sample (instance_id + base_commit)
  /tmp/blind24-pull-results.json        pull results (digests)
Output: /tmp/blind24-verify.json
"""

import json
import subprocess

REFS = "/tmp/blind24_dataset_image_refs.json"
SAMPLE = "/tmp/blind_round1_sample.py310.json"
PULLS = "/tmp/blind24-pull-results.json"
OUT = "/tmp/blind24-verify.json"


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)


def main():
    refs = json.load(open(REFS))
    sample = {x["instance_id"]: x for x in json.load(open(SAMPLE))["selected"]}
    pulls = {x["instance_id"]: x for x in json.load(open(PULLS))}
    out = []
    for inst in sorted(refs):
        ref = refs[inst]
        rec = {
            "instance_id": inst,
            "dataset_base_commit": sample[inst]["base_commit"],
            "dataset_image_ref": ref,
            "ghcr_ref": pulls.get(inst, {}).get("ghcr_ref"),
            "image_digest": pulls.get(inst, {}).get("image_digest"),
            "image_id": pulls.get(inst, {}).get("image_id"),
            "size_bytes": pulls.get(inst, {}).get("size_bytes"),
        }
        insp = run(["docker", "image", "inspect", ref,
                    "--format", "{{json .RepoDigests}}|{{.Id}}|{{.Size}}|{{json .Config.Labels}}"])
        if insp.returncode == 0:
            rd, iid, size, labels = insp.stdout.strip().split("|", 3)
            rec["local_repodigests"] = json.loads(rd)
            rec["local_image_id"] = iid
            rec["local_size"] = int(size)
            rec["labels"] = json.loads(labels) if labels and labels != "null" else {}
        else:
            rec["inspect_error"] = insp.stderr.strip()[-300:]
        head = run(["docker", "run", "--rm", "--network", "none", "--entrypoint", "git",
                    ref, "-C", "/testbed", "rev-parse", "HEAD"])
        rec["image_head"] = head.stdout.strip() if head.returncode == 0 else None
        rec["image_head_error"] = None if head.returncode == 0 else head.stderr.strip()[-300:]
        rec["base_commit_match"] = rec["image_head"] == rec["dataset_base_commit"]
        out.append(rec)
    json.dump(out, open(OUT, "w"), indent=2)
    ok = sum(1 for r in out if r.get("base_commit_match"))
    dig = sum(1 for r in out if r.get("image_digest"))
    print("verified_commit_match=%d/%d  digests_present=%d/%d" % (ok, len(out), dig, len(out)))
    for r in out:
        flag = "OK " if r.get("base_commit_match") else "BAD"
        print("%s %-40s %s %s" % (flag, r["instance_id"], (r.get("image_digest") or "?")[:26],
                                  r.get("image_head") or r.get("image_head_error")))


if __name__ == "__main__":
    main()
