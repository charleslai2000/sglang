#!/usr/bin/env python3
"""Deterministic independent long-prefix requests for HiCache tier pressure."""

import argparse, hashlib, json
from pathlib import Path
from transformers import AutoTokenizer

p = argparse.ArgumentParser()
p.add_argument("--model", default="/data/sglang-hicache/gemma4/model")
p.add_argument("--out", required=True)
p.add_argument("--count", type=int, default=16)
p.add_argument("--tokens", type=int, default=65536)
p.add_argument("--seed", type=int, default=20261120)
a = p.parse_args()
tok = AutoTokenizer.from_pretrained(a.model, trust_remote_code=True)
rows = []
for i in range(a.count):
    parts = []
    ids = []
    j = 0
    while len(ids) < a.tokens:
        text = f"Independent Gemma4 HiCache pressure session seed {a.seed} prefix {i:03d} block {j:05d}. This history is intentionally unique per request to prevent radix sharing and exercise cache tier movement.\n"
        chunk = tok.encode(text, add_special_tokens=False)
        parts.append(text)
        ids.extend(chunk)
        j += 1
    ids = ids[: a.tokens]
    rows.append(
        {
            "rid": f"g1-pressure-{a.seed}-{i:03d}",
            "input_ids": ids,
            "tokens": len(ids),
            "sha256": hashlib.sha256(
                json.dumps(ids, separators=(",", ":")).encode()
            ).hexdigest(),
        }
    )
obj = {
    "kind": "independent-long-prefix-pressure",
    "seed": a.seed,
    "count": a.count,
    "tokens": a.tokens,
    "requests": rows,
}
Path(a.out).parent.mkdir(parents=True, exist_ok=True)
Path(a.out).write_text(json.dumps(obj, separators=(",", ":")) + "\n")
print(json.dumps({k: v for k, v in obj.items() if k != "requests"}))
