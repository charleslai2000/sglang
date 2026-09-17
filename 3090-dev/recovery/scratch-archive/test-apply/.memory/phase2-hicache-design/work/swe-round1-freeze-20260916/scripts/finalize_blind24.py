#!/usr/bin/env python3
"""Finalize the 24 blind images: local dataset-name tag, digest, baked base_commit.

For each selected instance:
  1. docker tag <ghcr ref> <dataset image ref>   (local alias so the swebench
     verifier, which uses the dataset `image` column, resolves without Docker Hub)
  2. docker image inspect -> RepoDigests (pinned digest), Id, Size, labels
  3. docker run --rm --network none --entrypoint git <ref> -C /testbed rev-parse HEAD
     -> compare against the pinned dataset base_commit

Reads : /tmp/blind24_dataset_image_refs.json, /tmp/blind_round1_sample.py310.json
Writes: /tmp/blind24-verify.json, /tmp/blind24-pull-results.json
"""

import json
import subprocess

REFS = "/tmp/blind24_dataset_image_refs.json"
SAMPLE = "/tmp/blind_round1_sample.py310.json"


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)


def main():
    refs = json.load(open(REFS))
    sample = {x["instance_id"]: x for x in json.load(open(SAMPLE))["selected"]}
    pulls, verify = [], []
    for inst in sorted(refs):
        dhref = refs[inst]
        ghref = "ghcr.io/epoch-research/swe-bench.eval.x86_64." + dhref.split(
            "sweb.eval.x86_64.")[1].replace("_1776_", "__")
        tag = run(["docker", "tag", ghref, dhref])
        insp = run(["docker", "image", "inspect", dhref,
                    "--format", "{{json .RepoDigests}}|{{.Id}}|{{.Size}}|{{json .Config.Labels}}"])
        if insp.returncode != 0:
            print("INSPECT FAIL", inst, insp.stderr.strip()[-200:])
            continue
        rd, iid, size, labels = insp.stdout.strip().split("|", 3)
        rd = json.loads(rd)
        labels = json.loads(labels) if labels and labels != "null" else {}
        ghd = next((d for d in rd if d.startswith("ghcr.io/epoch-research/")), None)
        digest = "sha256:" + ghd.split("@sha256:")[1] if ghd else None
        head = run(["docker", "run", "--rm", "--network", "none", "--entrypoint", "git",
                    dhref, "-C", "/testbed", "rev-parse", "HEAD"])
        image_head = head.stdout.strip() if head.returncode == 0 else None
        m = image_head == sample[inst]["base_commit"]
        pulls.append({
            "instance_id": inst, "status": "pulled", "ghcr_ref": ghref, "dataset_ref": dhref,
            "image_digest": digest, "image_id": iid, "size_bytes": int(size),
        })
        verify.append({
            "instance_id": inst, "dataset_base_commit": sample[inst]["base_commit"],
            "dataset_image_ref": dhref, "ghcr_ref": ghref, "image_digest": digest,
            "image_id": iid, "local_repodigests": rd, "labels": labels,
            "image_head": image_head, "base_commit_match": m,
        })
        print("%s %-42s %s" % ("OK " if m else "BAD", inst, (digest or "?")[:26]))
    json.dump(pulls, open("/tmp/blind24-pull-results.json", "w"), indent=2)
    json.dump(verify, open("/tmp/blind24-verify.json", "w"), indent=2)
    ok = sum(1 for v in verify if v["base_commit_match"])
    print("DONE n=%d digest=%d base_commit_match=%d" % (
        len(verify), sum(1 for p in pulls if p["image_digest"]), ok))


if __name__ == "__main__":
    main()
