#!/usr/bin/env python3
"""Bounded selected-item SGLang replay with a larger completion cap."""

import argparse, json, hashlib
from pathlib import Path
import requests

p = argparse.ArgumentParser()
p.add_argument("--base-url", required=True)
p.add_argument("--fixture", required=True)
p.add_argument("--out", required=True)
p.add_argument("--max-tokens", type=int, default=2048)
a = p.parse_args()
src = [json.loads(x) for x in open(a.fixture)]
out = []
for x in src:
    payload = {
        "model": "gemma-4-E4B-it-QUASAR-Q4_0.gguf",
        "prompt": x["prompt_token_ids"],
        "temperature": 0,
        "top_p": 1,
        "top_k": 1,
        "seed": 1234,
        "max_tokens": a.max_tokens,
        "stop": ["Question:", "</s>", "<|im_end|>"],
        "return_token_ids": True,
        "stream": False,
        "rid": f"g2-diag-{x['doc_id']}",
    }
    r = requests.post(
        a.base_url.rstrip("/") + "/v1/completions", json=payload, timeout=3600
    )
    r.raise_for_status()
    b = r.json()
    c = b["choices"][0]
    assert c.get("prompt_token_ids") == x["prompt_token_ids"]
    row = {
        "doc_id": x["doc_id"],
        "prompt_token_ids_sha256": x["prompt_ids_sha256"],
        "target": x["target"],
        "text": c.get("text") or "",
        "finish_reason": c.get("finish_reason"),
        "matched_stop": c.get("matched_stop"),
        "output_ids": c.get("token_ids") or [],
        "score": {"correct": None, "prediction": None},
    }
    import re

    m = re.findall(r"####\s+(-?[0-9.,]+)", row["text"])
    gold = re.findall(r"####\s+(-?[0-9.,]+)", row["target"])
    pred = m[0] if m else "[invalid]"
    g = gold[-1] if gold else "[invalid]"
    norm = lambda s: s.replace(",", "").replace("$", "")
    row["score"] = {
        "correct": norm(pred) == norm(g)
        or norm(pred).endswith(".")
        and norm(pred)[:-1] == norm(g),
        "prediction": pred,
        "reference": g,
        "has_answer_marker": bool(m),
    }
    out.append(row)
    print(x["doc_id"], row["finish_reason"], row["score"], flush=True)
Path(a.out).write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n")
