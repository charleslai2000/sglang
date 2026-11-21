#!/usr/bin/env python3
"""Generate disjoint deterministic suffix blocks for sequential tier pressure."""

import argparse
import hashlib
import json
from pathlib import Path

ROOT_TOKENS = 16_384
BRANCH_TOKENS = 16_384
LEAF_TOKENS = 32_768


def sha(values):
    return hashlib.sha256(
        json.dumps(values, separators=(",", ":")).encode()
    ).hexdigest()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--tree-fixture", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--seed", type=int, default=20261120)
    a = p.parse_args()
    tree = json.loads(Path(a.tree_fixture).read_text())
    rows = tree["requests"]
    assert len(rows) == 8

    # This is an operator plan, not fabricated runtime capacity: the eight
    # request tree itself has 311,296 unique tokens, exceeding the requested
    # 172,032-token Full-device pool. The E5M2 byte estimate is used only to
    # explain why the 4GB CPU tier should also turn over; runtime pool splits
    # are collected from server logs/metrics before the claim is adjudicated.
    capacity = {"max_total_tokens": 172_032, "hicache_size_gb": 4}
    kv_bytes_per_unique_prompt_token_estimate = 42 * 2 * 1 * 256 * 2
    estimated_host_token_equivalent = 4_000_000_000 // kv_bytes_per_unique_prompt_token_estimate
    tree_unique = ROOT_TOKENS + 2 * BRANCH_TOKENS + 8 * LEAF_TOKENS
    output = {
        "schema": "gemma4.tier_capacity.plan.v1",
        "seed": a.seed,
        "tree_fixture_sha256": hashlib.sha256(
            Path(a.tree_fixture).read_bytes()
        ).hexdigest(),
        "capacity_target": capacity,
        "kv_bytes_per_unique_prompt_token_estimate": kv_bytes_per_unique_prompt_token_estimate,
        "tree_unique_prefix_workset_tokens": tree_unique,
        "estimated_host_token_equivalent_not_a_measurement": estimated_host_token_equivalent,
        "estimated_total_three_tier_tokens": 172_032 + estimated_host_token_equivalent,
        "tree_workset_exceeds_estimated_total_tokens": tree_unique > 172_032 + estimated_host_token_equivalent,
        "note": "Planning-only estimate, not a generated fixture or measurement. Acceptance uses actual Full/SWA pool capacities, tier occupancy, transfers, request source and post-restore Decode observed at runtime.",
    }
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(output, separators=(",", ":")) + "\n")
    print(json.dumps({k: v for k, v in output.items() if k != "prompts"}, indent=2))


if __name__ == "__main__":
    main()
