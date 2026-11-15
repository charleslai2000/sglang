#!/usr/bin/env python3
"""Run new fixed boundary prompts with IDs and per-token logprobs."""

import argparse, json, urllib.request
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
        "ignore_eos": True,
        "stop": [],
        "return_token_ids": True,
        "skip_special_tokens": False,
    },
)
c = r["choices"][0]
lp = c.get("logprobs") or {}
result = {
    "probe_class": f["probe_class"],
    "n": f["n"],
    "dtype": a.dtype,
    "fixture": str(a.fixture),
    "prompt_token_ids": c.get("prompt_token_ids"),
    "generated_token_ids": c.get("token_ids"),
    "generated_text": c.get("text"),
    "generated_token_logprobs": lp.get("token_logprobs"),
    "generated_token_texts": lp.get("tokens"),
    "finish_reason": c.get("finish_reason"),
}
if result["prompt_token_ids"] != ids:
    raise RuntimeError("completion endpoint prompt echo mismatch")
Path(a.output).write_text(json.dumps(result) + "\n")
