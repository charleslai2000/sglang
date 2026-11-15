#!/usr/bin/env python3
"""Capture first-step full logits and a real continuous greedy decode."""

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
    a.url + "/generate",
    {
        "input_ids": ids,
        "sampling_params": {
            "temperature": 0,
            "max_new_tokens": 32,
            "ignore_eos": True,
            "stop": [],
        },
        "return_logprob": True,
        "logprob_start_len": -1,
        "top_logprobs_num": 0,
    },
)
files = sorted(Path(a.output).parent.glob("captured-*.pt"))
if not files:
    raise RuntimeError("pre-sampling full-logits capture missing")
import torch

logits = torch.load(files[0], map_location="cpu", weights_only=True).float().flatten()
if logits.numel() < 250000:
    raise RuntimeError(f"expected vocab logits, got {tuple(logits.shape)}")
logp = torch.log_softmax(logits, dim=-1)
greedy = int(logits.argmax())
result = {
    "probe_class": f["probe_class"],
    "n": f["n"],
    "dtype": a.dtype,
    "fixture": str(a.fixture),
    "first_step_logits": logits.tolist(),
    "greedy_token": greedy,
    "greedy_logprob": float(logp[greedy]),
    "continuous_response": r,
    "capture_file": str(files[0]),
}
Path(a.output).write_text(json.dumps(result) + "\n")
