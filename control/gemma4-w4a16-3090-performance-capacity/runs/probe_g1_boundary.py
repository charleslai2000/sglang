#!/usr/bin/env python3
"""Request new fixed boundary probes with generation IDs and per-token logprobs."""

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
        "return_token_ids": True,
        "skip_special_tokens": False,
        "ignore_eos": True,
        "stop": [],
    },
)
choice = r["choices"][0]
lp = choice.get("logprobs") or {}
result = {
    "probe_class": f["probe_class"],
    "n": f["n"],
    "dtype": a.dtype,
    "fixture": str(a.fixture),
    "prompt_token_ids": choice.get("prompt_token_ids"),
    "generated_token_ids": choice.get("token_ids"),
    "generated_text": choice.get("text"),
    "token_logprobs": lp.get("token_logprobs"),
    "top_logprobs": lp.get("top_logprobs"),
    "finish_reason": choice.get("finish_reason"),
}
if result["prompt_token_ids"] != ids:
    raise RuntimeError("service prompt echo mismatch")
Path(a.output).write_text(json.dumps(result, indent=2) + "\n")
