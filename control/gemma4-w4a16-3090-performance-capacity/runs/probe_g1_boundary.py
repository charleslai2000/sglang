#!/usr/bin/env python3
"""Capture a new fixed-input first-step SGLang result and greedy continuation."""

import argparse, json, math, urllib.request
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
first = post(
    a.url + "/generate",
    {
        "input_ids": ids,
        "sampling_params": {"temperature": 0, "max_new_tokens": 1, "stop": []},
        "return_logprob": True,
        "logprob_start_len": -1,
        "top_logprobs_num": 0,
    },
)
print(json.dumps(first)[:500])
Path(a.output).write_text(
    json.dumps(
        {"dtype": a.dtype, "fixture": str(a.fixture), "first_response": first}, indent=2
    )
    + "\n"
)
