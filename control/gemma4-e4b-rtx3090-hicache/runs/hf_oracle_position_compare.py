#!/usr/bin/env python3
"""Compare saved CPU/GPU HF eager logits to existing exact-ID SGLang/Fork rows."""

import json
from pathlib import Path
import torch
from hf_oracle_cache_audit import metrics

ROOT = Path("/data/sglang-hicache/gemma4/runs")
CACHE = ROOT / "hf-oracle-audit-20261025"
BOUNDARY = ROOT / "20261022T065916Z-e5m2-swa-boundary"
OFFICIAL = ROOT / "official-fork-n8-20261024T2100Z"


def load_logits(path):
    return torch.load(path, map_location="cpu", weights_only=False)


def main():
    cpu = load_logits(CACHE / "cpu-eager.pt")
    gpu = load_logits(CACHE / "cuda-eager.pt")
    rows = []
    for n in (512, 514):
        comp = json.loads((BOUNDARY / f"n{n}/comparison.json").read_text())
        bfid = comp["bf16_forward_id"]
        bf = (
            load_logits(BOUNDARY / f"bf16/forward.{bfid}.logits")["output"]
            .float()[-1]
            .flatten()
        )
        sgl = load_logits(OFFICIAL / f"n{n}-response.json") if False else None
        # Exact BF16 Fork row is retained by the same-run boundary capture above.
        c, g = (
            cpu["sequences"][str(n)]["runs"]["False"]["logits"],
            gpu["sequences"][str(n)]["runs"]["False"]["logits"],
        )
        row = {
            "n": n,
            "positions": [1, n],
            "ids_sha256": cpu["sequences"][str(n)]["input_ids_sha256"],
            "cpu_hf_vs_gpu_hf": metrics(c, g),
            "sglang_bf16_vs_cpu_hf": metrics(c, bf),
            "sglang_bf16_vs_gpu_hf": metrics(g, bf),
            "hf_cpu_logits": c,
            "hf_gpu_logits": g,
            "sglang_logits": bf,
        }
        rows.append(row)
        print(json.dumps({k: v for k, v in row.items() if not k.endswith("_logits")}))
    torch.save(rows, CACHE / "cpu-gpu-sglang-comparison.pt")


if __name__ == "__main__":
    main()
