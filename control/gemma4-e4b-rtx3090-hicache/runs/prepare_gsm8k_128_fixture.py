#!/usr/bin/env python3
"""Freeze 64 BF16 score-flips and 64 unchanged GSM8K controls."""

import hashlib
import json
import random
from pathlib import Path

ROOT = Path("/data/sglang-hicache/gemma4/runs")
OLD = ROOT / "20261026T-gsm8k-g1-final/bf16/samples.jsonl"
NEW = ROOT / "20261026T-gsm8k-g1-final-bos/bf16/samples.jsonl"
AUDIT = ROOT / "20261026T-gsm8k-g1-final-bos/bf16/offline-stop-prefix-audit.json"
OUT = ROOT / "20261026T-gsm8k-stop-onoff-rerun/fixture-128.json"


def rows(path):
    return {str(x["doc_id"]): x for x in map(json.loads, path.open())}


old, new = rows(OLD), rows(NEW)
audit = json.load(AUDIT.open())
flips = {str(x["doc_id"]) for x in audit["flips"]}
assert len(flips) == 304 and old.keys() == new.keys() and len(new) == 1319
stable = {k for k in new if (k in flips) is False}
assert len(stable) == 1015
rng = random.Random(20261026)
selected_flip = sorted(rng.sample(sorted(flips), 64), key=int)
selected_control = sorted(rng.sample(sorted(stable), 64), key=int)
fixture = {}
for group, ids in (("flip", selected_flip), ("control", selected_control)):
    for doc_id in ids:
        o, n = old[doc_id], new[doc_id]
        prompt = n["arguments"]["gen_args_0"]["arg_0"]
        assert prompt == o["arguments"]["gen_args_0"]["arg_0"]
        fixture[doc_id] = {
            "group": group,
            "prompt": prompt,
            "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
            "old_text": o["resps"][0][0],
            "new_text": n["resps"][0][0],
            "old_score": bool(o["exact_match"]),
            "new_score": bool(n["exact_match"]),
            "old_prompt_hash": o["prompt_hash"],
            "new_prompt_hash": n["prompt_hash"],
        }
assert sum(x["group"] == "flip" for x in fixture.values()) == 64
assert sum(x["group"] == "control" for x in fixture.values()) == 64
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(fixture, indent=2, ensure_ascii=False) + "\n")
print(
    json.dumps(
        {
            "path": str(OUT),
            "n": len(fixture),
            "flips": selected_flip,
            "controls": selected_control,
            "sha256": hashlib.sha256(OUT.read_bytes()).hexdigest(),
        },
        indent=2,
    )
)
