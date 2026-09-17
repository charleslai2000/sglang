#!/usr/bin/env python3
"""Read-only GGUF metadata + tensor-name dump (no tensor payload read)."""
import sys
from collections import Counter, defaultdict

from gguf import GGUFReader


def main(path: str) -> None:
    reader = GGUFReader(path)
    print(f"### FILE {path}")
    print(f"tensor_count={len(reader.tensors)}")
    print("### METADATA")
    for key in sorted(reader.fields):
        field = reader.fields[key]
        try:
            value = field.contents()
        except Exception as exc:  # pragma: no cover - diagnostics
            value = f"<unreadable: {exc}>"
        text = repr(value)
        if len(text) > 400:
            text = text[:400] + f"... (+{len(text) - 400} chars)"
        print(f"{key} = {text}")
    names = sorted(t.name for t in reader.tensors)
    print("### TENSOR_NAMES_BEGIN")
    for name in names:
        print(name)
    print("### TENSOR_NAMES_END")
    # Summaries by normalized role.
    prefixes = Counter()
    for name in names:
        parts = name.split(".")
        if len(parts) >= 3 and parts[0] == "blk":
            prefixes["blk.*." + ".".join(parts[2:])] += 1
        else:
            prefixes[name] += 1
    print("### ROLE_COUNTS")
    for role, count in sorted(prefixes.items()):
        print(f"{count:5d}  {role}")


if __name__ == "__main__":
    main(sys.argv[1])
