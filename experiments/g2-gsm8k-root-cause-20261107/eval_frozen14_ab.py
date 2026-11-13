#!/usr/bin/env python3
"""Run the frozen 14 prompt IDs once against one SGLang arm and score outputs."""

import argparse, hashlib, json, re
from pathlib import Path
import requests

p = argparse.ArgumentParser()
p.add_argument("--base-url", required=True)
p.add_argument("--fixture", required=True)
p.add_argument("--out", required=True)
p.add_argument("--arm", required=True)
a = p.parse_args()
selected = {0, 1, 2, 3, 5, 6, 8, 18, 20, 24, 36, 39, 47, 70}
rows = [
    json.loads(line)
    for line in open(a.fixture)
    if json.loads(line)["doc_id"] in selected
]
rows.sort(key=lambda row: row["doc_id"])
if len(rows) != 14:
    raise RuntimeError(f"expected the frozen 14 prompts, found {len(rows)}")
result = []
for x in rows:
    payload = {
        "input_ids": x["prompt_token_ids"],
        "sampling_params": {
            "temperature": 0,
            "top_p": 1.0,
            "top_k": 1,
            "min_p": 0.0,
            "presence_penalty": 0.0,
            "frequency_penalty": 0.0,
            "repetition_penalty": 1.0,
            "max_new_tokens": 512,
            "stop": ["Question:", "</s>", "<|im_end|>"],
            "sampling_seed": 1234,
        },
        "return_logprob": False,
        "rid": f"g2-ab-{a.arm}-{x['doc_id']}",
    }
    r = requests.post(a.base_url.rstrip("/") + "/generate", json=payload, timeout=3600)
    r.raise_for_status()
    b = r.json()
    if b["meta_info"]["prompt_tokens"] != len(x["prompt_token_ids"]):
        raise RuntimeError(f"prompt token count mismatch doc={x['doc_id']}")
    ids = b["output_ids"]
    text = b.get("text", "")
    markers = re.findall(r"####\s+(-?[0-9.,]+)", text)
    gold = re.findall(r"####\s+(-?[0-9.,]+)", x["target"])
    norm = lambda s: s.replace(",", "").replace("$", "")
    pred = markers[0] if markers else "[invalid]"
    ref = gold[-1] if gold else "[invalid]"
    repeated_4grams = max(
        (
            ids[i : i + 4] == ids[j : j + 4]
            for i in range(max(0, len(ids) - 4))
            for j in range(i + 1, max(0, len(ids) - 3))
        ),
        default=False,
    )
    counts = {}
    for i in range(max(0, len(ids) - 3)):
        k = tuple(ids[i : i + 4])
        counts[k] = counts.get(k, 0) + 1
    rec = {
        "doc_id": x["doc_id"],
        "prompt_ids_sha256": x["prompt_ids_sha256"],
        "prompt_tokens": len(x["prompt_token_ids"]),
        "first_token": ids[0] if ids else None,
        "output_ids": ids,
        "text": text,
        "finish_reason": b["meta_info"]["finish_reason"],
        "correct": norm(pred) == norm(ref)
        or (norm(pred).endswith(".") and norm(pred)[:-1] == norm(ref)),
        "prediction": pred,
        "reference": ref,
        "marker_count": len(markers),
        "length_hit": b["meta_info"]["finish_reason"].get("type") == "length",
        "max_repeated_4gram_count": max(counts.values(), default=0),
        "repetition_flag": max(counts.values(), default=0) >= 8,
        "request": payload,
    }
    result.append(rec)
    print(
        a.arm,
        x["doc_id"],
        rec["first_token"],
        rec["correct"],
        rec["finish_reason"],
        flush=True,
    )
Path(a.out).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
print(
    json.dumps(
        {
            "arm": a.arm,
            "n": len(result),
            "correct": sum(x["correct"] for x in result),
            "length_hit": sum(x["length_hit"] for x in result),
            "repetition_flag": sum(x["repetition_flag"] for x in result),
        },
        indent=2,
    )
)
