#!/usr/bin/env python3
"""Tensor-type histogram + list of non-quantized (F32/F16/BF16) tensors."""
import sys
from collections import Counter, defaultdict

from gguf import GGUFReader


def main(path: str) -> None:
    reader = GGUFReader(path)
    counts = Counter(t.tensor_type.name for t in reader.tensors)
    print("### TYPE_HISTOGRAM")
    for name, count in sorted(counts.items()):
        print(f"{count:5d}  {name}")
    print("### NON_QUANT_BY_ROLE")
    roles = defaultdict(Counter)
    for t in reader.tensors:
        if t.tensor_type.name in ("F32", "F16", "BF16"):
            parts = t.name.split(".")
            role = ".".join(parts[2:]) if len(parts) >= 3 and parts[0] == "blk" else t.name
            roles[role][t.tensor_type.name] += 1
    for role, c in sorted(roles.items()):
        print(f"{role:40s} {dict(c)}")


if __name__ == "__main__":
    main(sys.argv[1])
