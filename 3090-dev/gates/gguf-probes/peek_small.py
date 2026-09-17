#!/usr/bin/env python3
"""Read a few small tensors to check converter-time transforms (read-only)."""
import sys

import torch
from gguf import GGUFReader


def main(path: str, names) -> None:
    reader = GGUFReader(path)
    wanted = set(names)
    for tensor in reader.tensors:
        if tensor.name not in wanted:
            continue
        raw = torch.tensor(tensor.data)
        flat = raw.float().flatten()
        print(
            f"{tensor.name:24s} type={tensor.tensor_type.name:6s} shape={raw.shape} "
            f"min={flat.min().item():.6g} max={flat.max().item():.6g} "
            f"n_neg={(flat < 0).sum().item()} n_pos={(flat > 0).sum().item()} "
            f"head={[round(x, 5) for x in flat[:6].tolist()]}"
        )


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:])
