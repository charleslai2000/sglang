#!/usr/bin/env python3
"""Freeze new boundary probes sliced from the saved BOS-correct GSM8K prompts.

These are new probes, not reconstructions of the missing historical requests.
"""

import hashlib, json
from pathlib import Path
from transformers import AutoTokenizer

BASE = Path(
    "/data/sglang-hicache/gemma4/runs/20261115T-g1-bf16-gsm8k-explicit-bos/samples.jsonl"
)
MODEL = Path("/data/sglang-hicache/gemma4/model")
OUT = Path("/data/sglang-hicache/gemma4/runs/20261115T-g1-e5m2-boundary-new")
rows = {}
for line in BASE.read_text().splitlines():
    r = json.loads(line)
    ids = r["audit"]["prompt_ids"]
    assert ids[0] == 2 and len(ids) > 514
    for n in (512, 513, 514):
        if n not in rows:
            rows[n] = {"doc_id": int(r["doc_id"]), "prompt_ids": ids[:n]}
assert set(rows) == {512, 513, 514}
OUT.mkdir(parents=True, exist_ok=True)
tok = AutoTokenizer.from_pretrained(
    MODEL, local_files_only=True, trust_remote_code=True
)
for n, x in rows.items():
    ids = x["prompt_ids"]
    text = tok.decode(ids, skip_special_tokens=False)
    assert tok.encode(text, add_special_tokens=False) == ids, (n, "roundtrip mismatch")
    data = {
        "probe_class": "NEW_PREFIX_SLICE_OF_SAVED_EXPLICIT_BOS_GSM8K_PROMPT_NOT_HISTORICAL_REPLAY",
        "n": n,
        "source_doc_id": x["doc_id"],
        "checkpoint_revision": "6cd26aaa2357fb2bad8c51699a7558a4d1a965bb",
        "weight_sha256": "19d89d2a4b3e401a3eae75ec08ab112810421a036c91d8c8226b686be7fe0c5d",
        "prompt_protocol": "gemma-explicit-bos-v1",
        "token_ids": ids,
        "prompt_text": text,
        "token_ids_sha256": hashlib.sha256(
            json.dumps(ids, separators=(",", ":")).encode()
        ).hexdigest(),
    }
    (OUT / f"n{n}.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    )
print(
    json.dumps(
        {
            n: {
                "source_doc_id": x["doc_id"],
                "sha256": hashlib.sha256(
                    json.dumps(x["prompt_ids"], separators=(",", ":")).encode()
                ).hexdigest(),
            }
            for n, x in rows.items()
        },
        indent=2,
    )
)
