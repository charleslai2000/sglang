#!/usr/bin/env python3
"""Offline verify the hash-pinned 16K/16K/32K multi-branch tree fixture."""

import argparse
import hashlib
import json
from pathlib import Path

ROOT = 16_384
BRANCH = 16_384
LEAF = 32_768
EXPECTED_SHA256 = "ac06790a415e772880dac9cb0415d09cc1bdc04142652733d1314f583f841a8b"
EXPECTED_BASE_SHA256 = "b2795f5dbb03abb01940fd33fb44aaee947439ba38355677adad2c62de9df7a9"
EXPECTED_REQUESTS = 12
EXPECTED_LEAVES_PER_BRANCH = 6
EXPECTED_UNIQUE = 442_368


def digest(values):
    return hashlib.sha256(
        json.dumps(values, separators=(",", ":")).encode()
    ).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("fixture")
    parser.add_argument("--expected-sha256", default=EXPECTED_SHA256)
    args = parser.parse_args()
    path = Path(args.fixture)
    raw = path.read_bytes()
    actual_sha = hashlib.sha256(raw).hexdigest()
    if actual_sha != args.expected_sha256:
        raise SystemExit(
            f"FIXTURE_SHA256_MISMATCH expected={args.expected_sha256} actual={actual_sha}"
        )
    fixture = json.loads(raw)
    if fixture.get("schema") != "gemma4.radix_tree.fixture.v2":
        raise SystemExit("FIXTURE_SCHEMA_MISMATCH")
    rows = fixture["requests"]
    if len(rows) != EXPECTED_REQUESTS:
        raise SystemExit(f"FIXTURE_REQUEST_COUNT:{len(rows)}")
    if fixture.get("parent_fixture_sha256") != EXPECTED_BASE_SHA256:
        raise SystemExit("FIXTURE_PARENT_SHA256_MISMATCH")
    if int(fixture.get("extension_seed", -1)) != 20261120:
        raise SystemExit("FIXTURE_EXTENSION_SEED_MISMATCH")
    roots = {tuple(row["input_ids"][:ROOT]) for row in rows}
    branches_by_id = {}
    leaves = set()
    prompts = set()
    for row in rows:
        ids = row["input_ids"]
        if len(ids) != ROOT + BRANCH + LEAF:
            raise SystemExit(f"FIXTURE_PROMPT_LENGTH:{row['rid']}:{len(ids)}")
        bid = int(row["branch_id"])
        branch = tuple(ids[ROOT : ROOT + BRANCH])
        if bid in branches_by_id and branches_by_id[bid] != branch:
            raise SystemExit(f"FIXTURE_BRANCH_MISMATCH:{row['rid']}")
        branches_by_id[bid] = branch
        leaves.add(tuple(ids[ROOT + BRANCH :]))
        prompts.add(tuple(ids))
        if row.get("sha256") != digest(ids):
            raise SystemExit(f"FIXTURE_PROMPT_DIGEST_MISMATCH:{row['rid']}")
    unique = ROOT * len(roots) + BRANCH * len(branches_by_id) + LEAF * len(leaves)
    fanout = {b: sum(int(row["branch_id"]) == b for row in rows) for b in (0, 1)}
    if (
        len(roots) != 1
        or len(branches_by_id) != 2
        or len(leaves) != len(rows)
        or set(fanout.values()) != {EXPECTED_LEAVES_PER_BRANCH}
    ):
        raise SystemExit("FIXTURE_RADIX_SHAPE_MISMATCH")
    if fixture.get("shape", {}).get("leaves_per_branch") != {str(k): v for k, v in fanout.items()}:
        raise SystemExit("FIXTURE_RECORDED_BRANCH_FANOUT_MISMATCH")
    if (
        unique < EXPECTED_UNIQUE
        or fixture.get("unique_prefix_workset_tokens") != unique
    ):
        raise SystemExit(f"FIXTURE_UNIQUE_WORKSET:{unique}")
    print(
        json.dumps(
            {
                "path": str(path),
                "sha256": actual_sha,
                "requests": len(rows),
                "prompt_tokens_each": ROOT + BRANCH + LEAF,
                "root_count": len(roots),
                "branch_count": len(branches_by_id),
                "leaf_count": len(leaves),
                "branch_fanout": {
                    str(b): sum(int(r["branch_id"]) == b for r in rows) for b in (0, 1)
                },
                "unique_prefix_workset_tokens": unique,
                "verified": True,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
