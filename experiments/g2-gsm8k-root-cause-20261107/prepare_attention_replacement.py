#!/usr/bin/env python3
"""Build a single-row Layer0 attention-output replacement from a frozen capture."""

import argparse
from pathlib import Path
import torch

p = argparse.ArgumentParser()
p.add_argument("--capture", required=True)
p.add_argument("--output", required=True)
a = p.parse_args()
r = torch.load(a.capture, map_location="cpu", weights_only=False)
x = r.get("value", r.get("output"))
if x is None or x.ndim != 3 or tuple(x.shape[0:1]) != (1,):
    raise ValueError(
        f"expected [1, heads, head_dim], got {None if x is None else tuple(x.shape)}"
    )
torch.save({"output": x.float().cpu()}, a.output)
print({"source": a.capture, "shape": tuple(x.shape), "output": a.output})
