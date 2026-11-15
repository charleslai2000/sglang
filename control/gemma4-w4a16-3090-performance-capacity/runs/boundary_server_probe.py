#!/usr/bin/env python3
"""Capture matching SGLang boundary forward/logits and continuous decode output."""

import argparse, hashlib, json, urllib.request
from pathlib import Path


def post(url, obj):
    req = urllib.request.Request(
        url, data=json.dumps(obj).encode(), headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=1800) as r:
        return json.load(r)


p = argparse.ArgumentParser()
p.add_argument("--url", required=True)
p.add_argument("--dtype", required=True)
p.add_argument("--fixture", required=True)
p.add_argument("--output", required=True)
p.add_argument("--capture-prefix", required=True)
a = p.parse_args()
f = json.loads(Path(a.fixture).read_text())
ids = f["token_ids"]
assert len(ids) == f["n"] and ids[0] == 2
r = post(
    a.url + "/v1/completions",
    {
        "model": "gemma4",
        "prompt": ids,
        "max_tokens": 32,
        "temperature": 0,
        "top_p": 1,
        "logprobs": 1,
        "echo": True,
        "return_token_ids": True,
        "skip_special_tokens": False,
        "ignore_eos": True,
        "stop": [],
    },
)
c = r["choices"][0]
lp = c.get("logprobs") or {}
captured = sorted(
    Path(a.capture_prefix).parent.glob(Path(a.capture_prefix).name + ".captured-*.pt")
)
import torch

entries = []
for file in captured:
    obj = torch.load(file, map_location="cpu", weights_only=True)
    log = obj["logits"].float()
    length = obj.get("extend_seq_lens")
    if log.shape[-1] >= 250000 and length and f["n"] in length:
        entries.append({"file": str(file), "logits": log[-1].flatten().tolist()})
if len(entries) != 1:
    raise RuntimeError(
        f"expected exactly one N={f['n']} full-vocab forward capture, got {len(entries)}"
    )
if c.get("prompt_token_ids") != ids:
    raise RuntimeError("prompt IDs returned by server do not match fixture")
out = {
    "probe_class": f["probe_class"],
    "n": f["n"],
    "source_doc_id": f["source_doc_id"],
    "dtype": a.dtype,
    "fixture_sha256": hashlib.sha256(Path(a.fixture).read_bytes()).hexdigest(),
    "prompt_token_ids": ids,
    "first_step_logits": entries[0]["logits"],
    "first_step_capture": entries[0]["file"],
    "generated_token_ids": c.get("token_ids"),
    "generated_text": c.get("text"),
    "generated_token_logprobs": lp.get("token_logprobs"),
    "generated_token_texts": lp.get("tokens"),
    "finish_reason": c.get("finish_reason"),
}
Path(a.output).write_text(json.dumps(out) + "\n")
