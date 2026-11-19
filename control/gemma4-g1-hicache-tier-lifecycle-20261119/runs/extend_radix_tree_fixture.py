#!/usr/bin/env python3
"""Extend the pinned eight-leaf tree without changing its root/branches/leaves."""

import argparse
import hashlib
import json
import random
from pathlib import Path

ROOT = 16_384
BRANCH = 16_384
LEAF = 32_768


def digest(values):
    return hashlib.sha256(
        json.dumps(values, separators=(",", ":")).encode()
    ).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--new-leaves", type=int, default=4)
    parser.add_argument("--seed", type=int, default=20261120)
    args = parser.parse_args()
    if args.new_leaves < 4:
        raise SystemExit("at least four additional leaves are required")
    old = json.loads(Path(args.base).read_text())
    rows = old["requests"]
    if len(rows) != 8:
        raise SystemExit(f"expected exactly 8 base leaves; got {len(rows)}")
    root = rows[0]["input_ids"][:ROOT]
    branches = [
        rows[0]["input_ids"][ROOT : ROOT + BRANCH],
        rows[4]["input_ids"][ROOT : ROOT + BRANCH],
    ]
    for row in rows:
        if row["input_ids"][:ROOT] != root:
            raise SystemExit("base root mismatch")
        bid = row["branch_id"]
        if row["input_ids"][ROOT : ROOT + BRANCH] != branches[bid]:
            raise SystemExit(f"base branch mismatch for {row['rid']}")
    forbidden = set(int(x) for x in old.get("special_token_ids_excluded", []))
    vocab_size = int(old["tokenizer_vocab_size"])
    rng = random.Random(args.seed)
    added = []
    start = len(rows)
    for offset in range(args.new_leaves):
        index = start + offset
        # Alternate to retain a balanced six-leaf fanout for the 12-leaf target.
        branch_id = offset % 2
        tail = []
        while len(tail) < LEAF:
            token = rng.randrange(32, vocab_size)
            if token not in forbidden:
                tail.append(token)
        ids = root + branches[branch_id] + tail
        rid = f"g1-tree-{old['seed']}-{index:02d}"
        added.append(
            {
                "rid": rid,
                "branch_id": branch_id,
                "input_ids": ids,
                "root_sha256": digest(root),
                "branch_sha256": digest(branches[branch_id]),
                "leaf_sha256": digest(tail),
                "sha256": digest(ids),
            }
        )
    all_rows = rows + added
    root_set = {tuple(r["input_ids"][:ROOT]) for r in all_rows}
    branch_set = {tuple(r["input_ids"][ROOT : ROOT + BRANCH]) for r in all_rows}
    leaves = {tuple(r["input_ids"][ROOT + BRANCH :]) for r in all_rows}
    if len(root_set) != 1 or len(branch_set) != 2 or len(leaves) != len(all_rows):
        raise SystemExit(
            "extended tree structure is not 1 root / 2 branches / unique leaves"
        )
    unique = ROOT + 2 * BRANCH + len(all_rows) * LEAF
    out = dict(old)
    out["schema"] = "gemma4.radix_tree.fixture.v2"
    out["parent_fixture_sha256"] = hashlib.sha256(
        Path(args.base).read_bytes()
    ).hexdigest()
    out["extension_seed"] = args.seed
    out["requests"] = all_rows
    out["shape"] = {
        "root_tokens": ROOT,
        "branches": 2,
        "branch_tokens_each": BRANCH,
        "leaves": len(all_rows),
        "leaves_per_branch": {
            str(b): sum(r["branch_id"] == b for r in all_rows) for b in (0, 1)
        },
        "leaf_tokens_each": LEAF,
        "prompt_tokens_each": ROOT + BRANCH + LEAF,
    }
    out["unique_prefix_workset_tokens"] = unique
    if len(all_rows) < 12 or unique < 442_368:
        raise SystemExit("fixture is below authorized 12-leaf / 442368-token target")
    target = Path(args.out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(out, separators=(",", ":")) + "\n")
    print(
        json.dumps(
            {
                "schema": out["schema"],
                "base_sha256": out["parent_fixture_sha256"],
                "request_count": len(all_rows),
                "root_tokens": ROOT,
                "branch_count": len(branch_set),
                "branch_fanout": out["shape"]["leaves_per_branch"],
                "unique_leaves": len(leaves),
                "prompt_tokens_each": ROOT + BRANCH + LEAF,
                "unique_prefix_workset_tokens": unique,
                "fixture_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
                "seed": args.seed,
                "preserved_base_request_ids": [r["rid"] for r in rows],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
