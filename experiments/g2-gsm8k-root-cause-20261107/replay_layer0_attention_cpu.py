#!/usr/bin/env python3
"""Compare frozen doc24 Layer0 A8/FP32 attention from captured Q/K/V on CPU."""

import argparse, json
from pathlib import Path
import torch

p = argparse.ArgumentParser()
p.add_argument("--a8-prefix", required=True)
p.add_argument("--fp32-prefix", required=True)
p.add_argument("--position", type=int, default=1103)
p.add_argument("--window", type=int, default=511)
p.add_argument("--output", required=True)
a = p.parse_args()


def load(prefix, stage):
    return torch.load(f"{prefix}.{stage}.pt", map_location="cpu", weights_only=False)[
        "value"
    ].float()


records = {
    name: {
        stage: load(prefix, stage) for stage in ["q_rope", "k_rope", "attention_output"]
    }
    for name, prefix in [("a8", a.a8_prefix), ("fp32", a.fp32_prefix)]
}
row = a.position


def attn(q, k, v):
    q = q[0].float()
    k = k.float()
    v = v.float()
    start = max(0, a.position - a.window)
    ends = a.position + 1
    out = []
    for h in range(q.shape[0]):
        kh = h // (q.shape[0] // k.shape[1])
        scores = q[h] @ k[start:ends, kh].T
        out.append(torch.softmax(scores, dim=-1) @ v[start:ends, kh].float())
    return torch.stack(out).unsqueeze(0)


def metrics(x, y):
    d = x.float() - y.float()
    return {
        "rel_l2": float(d.norm() / x.float().norm().clamp_min(1e-30)),
        "max_abs": float(d.abs().max()),
        "bf16_equal": bool(torch.equal(x.to(torch.bfloat16), y.to(torch.bfloat16))),
    }


q = {n: r["q_rope"][row : row + 1] for n, r in records.items()}
k = {n: r["k_rope"] for n, r in records.items()}
v = {
    n: r["attention_output"].new_zeros((r["q_rope"].shape[0], 2, 256))
    for n, r in records.items()
}
# V must be loaded as a separately captured value by the caller's prefixes.
for n, prefix in [("a8", a.a8_prefix), ("fp32", a.fp32_prefix)]:
    v[n] = load(prefix, "v_normed").reshape(-1, 2, 256)
prods = {
    "a8_qkv": attn(q["a8"], k["a8"], v["a8"]),
    "fp32_qkv": attn(q["fp32"], k["fp32"], v["fp32"]),
    "a8q_fp32kv": attn(q["a8"], k["fp32"], v["fp32"]),
    "fp32q_a8kv": attn(q["fp32"], k["a8"], v["a8"]),
}
# Captured attention outputs are [1,H,D] at the selected position.
obs = {n: r["attention_output"] for n, r in records.items()}
result = {
    "position": a.position,
    "causal_window": [max(0, a.position - a.window), a.position],
    "attention_output_a8_vs_fp32": metrics(obs["a8"], obs["fp32"]),
    "cross_replay": {
        name: {
            "vs_a8": metrics(x.to(torch.bfloat16), obs["a8"]),
            "vs_fp32": metrics(x.to(torch.bfloat16), obs["fp32"]),
        }
        for name, x in prods.items()
    },
    "qkv_input_delta": {
        "q": metrics(q["a8"], q["fp32"]),
        "k": metrics(k["a8"][row : row + 1], k["fp32"][row : row + 1]),
        "v": metrics(v["a8"][row : row + 1], v["fp32"][row : row + 1]),
    },
}
Path(a.output).write_text(json.dumps(result, indent=2))
print(json.dumps(result, indent=2))
