#!/usr/bin/env python3
"""Print name/type/shape for selected tensors (metadata only)."""
import sys

from gguf import GGUFReader


def main(path: str, patterns) -> None:
    reader = GGUFReader(path)
    for tensor in reader.tensors:
        if any(p in tensor.name for p in patterns):
            print(
                f"{tensor.name:48s} type={tensor.tensor_type.name:8s} "
                f"shape={tuple(int(x) for x in tensor.shape)} n={tensor.n_elements}"
            )


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:])
