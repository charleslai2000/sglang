#!/usr/bin/env python3
import argparse, hashlib, json, requests
from pathlib import Path
from datasets import load_dataset
import os

ap = argparse.ArgumentParser()
ap.add_argument("--out", required=True)
a = ap.parse_args()
out = Path(a.out)
out.mkdir(parents=True, exist_ok=True)

local_dataset = Path(os.environ.get("GSM8K_DATA_DIR", ""))
if (local_dataset / "train.jsonl").is_file() and (local_dataset / "test.jsonl").is_file():
    d = {
        split: [json.loads(line) for line in (local_dataset / f"{split}.jsonl").open() if line.strip()]
        for split in ("train", "test")
    }
else:
    d = load_dataset("openai/gsm8k", "main")
summary = {}
for split in ("train", "test"):
    p = out / f"{split}.jsonl"
    rows = [dict(x) for x in d[split]]
    p.write_text(
        "".join(
            json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n"
            for r in rows
        )
    )
    with p.open(encoding="utf-8") as f:
        parsed = [json.loads(line) for line in f if line.strip()]
    assert len(parsed) == len(rows) and parsed == rows
    summary[split] = {
        "count": len(rows),
        "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
    }
print(json.dumps(summary, indent=2))
