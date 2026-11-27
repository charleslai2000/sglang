"""Decode-path top-k logprobs at the divergence step (per backend)."""

import json
import os
import sys

import requests

PORT = sys.argv[1]
OUT = sys.argv[2]
IDS = json.load(open(os.path.join(OUT, "divergence-input.json")))[:1024]

data = {
    "input_ids": IDS,
    "return_logprob": True,
    "logprob_start_len": -1,
    "top_logprobs_num": 5,
    "sampling_params": {
        "temperature": 0.0,
        "top_k": 1,
        "max_new_tokens": 23,
        "ignore_eos": True,
    },
}
r = requests.post(f"http://127.0.0.1:{PORT}/generate", json=data, timeout=600)
r.raise_for_status()
payload = r.json()
json.dump(payload, open(os.path.join(OUT, sys.argv[3], "logprob-response.json"), "w"), indent=1)
meta = payload.get("meta_info", {})
print("ids", payload.get("output_ids"))
print("keys", sorted(meta.keys()))
