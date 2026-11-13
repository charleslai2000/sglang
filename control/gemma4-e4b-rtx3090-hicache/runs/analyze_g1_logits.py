#!/usr/bin/env python3
"""Offline logit comparison for already-frozen Gemma artifacts only."""

import argparse, json, math
from pathlib import Path
import torch


def flat(obj, prefix=""):
    out = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.update(flat(v, f"{prefix}/{k}"))
    elif isinstance(obj, torch.Tensor):
        if obj.numel() and obj.shape[-1] > 1000:
            out[prefix] = obj
    return out


def compare(a, b):
    a = a.float().flatten()
    b = b.float().flatten()
    assert a.shape == b.shape
    p = torch.softmax(a, dim=-1)
    q = torch.softmax(b, dim=-1)
    lp = torch.log_softmax(a, dim=-1)
    lq = torch.log_softmax(b, dim=-1)
    kl1 = torch.sum(p * (lp - lq)).item()
    kl2 = torch.sum(q * (lq - lp)).item()
    ac = a - a.mean()
    bc = b - b.mean()
    rel = torch.linalg.vector_norm(ac - bc).item() / torch.linalg.vector_norm(ac).item()
    top = torch.topk(a, 2)
    topb = torch.topk(b, 2)
    return {
        "kl_a_to_b": kl1,
        "kl_b_to_a": kl2,
        "centered_relative_l2": rel,
        "raw_relative_l2": torch.linalg.vector_norm(a - b).item()
        / torch.linalg.vector_norm(a).item(),
        "a_top1": int(top.indices[0]),
        "a_top2": int(top.indices[1]),
        "a_margin": float(top.values[0] - top.values[1]),
        "b_top1": int(topb.indices[0]),
        "b_top2": int(topb.indices[1]),
        "b_margin": float(topb.values[0] - topb.values[1]),
        "greedy_agree": int(top.indices[0]) == int(topb.indices[0]),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    blobs = []
    for name in args.files:
        p = Path(name)
        x = torch.load(p, map_location="cpu", weights_only=False)
        blobs.append((name, flat(x)))
    pairs = []
    for i in range(len(blobs)):
        for j in range(i + 1, len(blobs)):
            common = set(blobs[i][1]) & set(blobs[j][1])
            for k in sorted(common):
                try:
                    metrics = compare(blobs[i][1][k], blobs[j][1][k])
                except AssertionError:
                    continue
                pairs.append(
                    {"a": blobs[i][0], "b": blobs[j][0], "tensor": k, **metrics}
                )
    result = {"files": args.files, "matched_tensor_pairs": len(pairs), "pairs": pairs}
    Path(args.out).write_text(json.dumps(result, indent=2) + "\n")
    print("matched tensor pairs", len(pairs))


if __name__ == "__main__":
    main()
