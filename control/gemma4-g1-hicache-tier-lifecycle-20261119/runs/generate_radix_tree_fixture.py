#!/usr/bin/env python3
"""Create/validate the deterministic Gemma4 16K/16K/32K radix-tree fixture."""

import argparse
import hashlib
import json
import random
from pathlib import Path

from transformers import AutoTokenizer

ROOT = 16_384
BRANCH = 16_384
LEAF = 32_768
REQUESTS = 8


def digest(values):
    return hashlib.sha256(
        json.dumps(values, separators=(",", ":")).encode()
    ).hexdigest()


def validate(obj):
    rows = obj["requests"]
    assert len(rows) == REQUESTS
    roots = {tuple(r["input_ids"][:ROOT]) for r in rows}
    assert len(roots) == 1
    branches = {tuple(r["input_ids"][ROOT : ROOT + BRANCH]) for r in rows}
    assert len(branches) == 2
    leaves = {tuple(r["input_ids"][ROOT + BRANCH :]) for r in rows}
    assert len(leaves) == REQUESTS
    assert all(len(r["input_ids"]) == 65_536 for r in rows)
    for r in rows:
        branch_id = int(r["rid"].rsplit("-", 1)[1]) // 4
        assert r["branch_id"] == branch_id
        assert r["root_sha256"] == digest(r["input_ids"][:ROOT])
        assert r["branch_sha256"] == digest(r["input_ids"][ROOT : ROOT + BRANCH])
        assert r["leaf_sha256"] == digest(r["input_ids"][ROOT + BRANCH :])
    unique_workset = ROOT + 2 * BRANCH + REQUESTS * LEAF
    assert unique_workset == 311_296
    assert obj["unique_prefix_workset_tokens"] == unique_workset
    return {
        "request_count": len(rows),
        "tokens_per_request": 65_536,
        "root_tokens": ROOT,
        "branch_count": 2,
        "branch_tokens_each": BRANCH,
        "leaf_count": REQUESTS,
        "leaf_tokens_each": LEAF,
        "unique_prefix_workset_tokens": unique_workset,
        "root_sha256": rows[0]["root_sha256"],
        "branch_sha256": sorted({r["branch_sha256"] for r in rows}),
        "fixture_sha256": digest([[r["rid"], r["sha256"]] for r in rows]),
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--model", default="/data/sglang-hicache/gemma4/model")
    p.add_argument("--out", required=True)
    p.add_argument("--seed", type=int, default=20261119)
    p.add_argument("--validate", action="store_true")
    a = p.parse_args()
    target = Path(a.out)
    if a.validate:
        obj = json.loads(target.read_text())
        print(json.dumps(validate(obj), indent=2))
        return

    tokenizer = AutoTokenizer.from_pretrained(a.model, trust_remote_code=True)
    vocab_size = len(tokenizer)
    forbidden = set(int(x) for x in tokenizer.all_special_ids)
    if vocab_size <= 512:
        raise SystemExit(f"Unexpected tokenizer vocabulary size: {vocab_size}")

    rng = random.Random(a.seed)

    def token_block(length):
        out = []
        while len(out) < length:
            token_id = rng.randrange(32, vocab_size)
            if token_id not in forbidden:
                out.append(token_id)
        return out

    root = token_block(ROOT)
    branch_blocks = [token_block(BRANCH) for _ in range(2)]
    leaf_blocks = [token_block(LEAF) for _ in range(REQUESTS)]
    rows = []
    for i in range(REQUESTS):
        branch_id = i // 4
        ids = root + branch_blocks[branch_id] + leaf_blocks[i]
        assert len(ids) == 65_536
        rows.append(
            {
                "rid": f"g1-tree-{a.seed}-{i:02d}",
                "branch_id": branch_id,
                "input_ids": ids,
                "root_sha256": digest(root),
                "branch_sha256": digest(branch_blocks[branch_id]),
                "leaf_sha256": digest(leaf_blocks[i]),
                "sha256": digest(ids),
            }
        )
    obj = {
        "schema": "gemma4.radix_tree.fixture.v1",
        "seed": a.seed,
        "tokenizer_path": a.model,
        "tokenizer_vocab_size": vocab_size,
        "special_token_ids_excluded": sorted(forbidden),
        "shape": {
            "root_tokens": ROOT,
            "branches": 2,
            "branch_tokens_each": BRANCH,
            "leaves_per_branch": 4,
            "leaf_tokens_each": LEAF,
            "prompt_tokens_each": ROOT + BRANCH + LEAF,
        },
        "unique_prefix_workset_tokens": ROOT + 2 * BRANCH + REQUESTS * LEAF,
        "requests": rows,
    }
    summary = validate(obj)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(obj, separators=(",", ":")) + "\n")
    summary["seed"] = a.seed
    summary["tokenizer_vocab_size"] = vocab_size
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
