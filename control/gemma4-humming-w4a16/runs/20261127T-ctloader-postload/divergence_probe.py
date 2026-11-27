"""Bounded follow-up: is the one long-generation divergence a near-tie?

Feeds prompt `long-300` plus the 22 tokens both arms agreed on, so the next-token
distribution at the divergence point is measured for each backend, then compares
the top-1/top-2 margin with the cross-backend logit difference.
"""

import json
import os
import sys

PORT = sys.argv[1]
OUT = sys.argv[2]
IDS = json.load(open(os.path.join(OUT, "divergence-input.json")))

import requests
import torch

data = {
    "input_ids": IDS,
    "sampling_params": {
        "temperature": 0.0,
        "top_k": 1,
        "max_new_tokens": 1,
        "ignore_eos": True,
    },
}
r = requests.post(f"http://127.0.0.1:{PORT}/generate", json=data, timeout=600)
r.raise_for_status()
json.dump(r.json(), open(os.path.join(OUT, "divergence-response.json"), "w"), indent=1)
print("DIVERGENCE_REQUEST_OK")
