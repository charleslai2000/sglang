#!/usr/bin/env python3
"""Teacher-forced HF Gemma4 BF16 reference on fixed saved token IDs."""

import json, hashlib
from pathlib import Path
import torch
from transformers import AutoModelForCausalLM

DATA = Path("/data/sglang-hicache/gemma4")
OUT = DATA / "runs/20261115T-g1-e5m2-boundary-new"
MODEL = DATA / "model"
torch.manual_seed(0)
model = AutoModelForCausalLM.from_pretrained(
    MODEL,
    torch_dtype=torch.bfloat16,
    device_map="cuda",
    trust_remote_code=True,
    local_files_only=True,
).eval()
res = []
for n in (512, 513, 514):
    f = OUT / f"n{n}.json"
    d = json.loads(f.read_text())
    ids = torch.tensor([d["token_ids"]], device="cuda")
    with torch.inference_mode():
        logits = model(input_ids=ids).logits[0, -1].float()
        lp = torch.log_softmax(logits, dim=-1)
    x = logits.cpu()
    res.append(
        {
            "probe_class": d["probe_class"],
            "n": n,
            "fixture_sha256": hashlib.sha256(f.read_bytes()).hexdigest(),
            "full_logits": x.tolist(),
            "greedy_token": int(x.argmax()),
            "greedy_logprob": float(torch.log_softmax(x.double(), 0)[int(x.argmax())]),
            "dtype": "bfloat16",
            "implementation": "transformers HF Gemma4 causal LM, same checkpoint",
        }
    )
(OUT / "hf-reference.json").write_text(json.dumps(res) + "\n")
