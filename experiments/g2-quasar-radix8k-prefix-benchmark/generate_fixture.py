#!/usr/bin/env python3
"""Rebuild the historical Radix8K natural-token fixture with the QUASAR tokenizer."""

import argparse
import hashlib
import json
from pathlib import Path
from tokenizers import Tokenizer

CONCURRENCIES = (1, 2, 4, 8, 16, 24, 32)
ROUNDS = 4
PREFIX, SUFFIX, OUTPUT = 7168, 1024, 256


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tokenizer", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    if a.out.exists():
        raise FileExistsError(a.out)
    tok = Tokenizer.from_file(str(a.tokenizer / "tokenizer.json"))
    ids = tok.encode(
        "Radix cache prefix benchmark. The shared context is fixed and deterministic. "
        * 5000,
        add_special_tokens=False,
    ).ids
    prefix = ids[:PREFIX]
    if len(prefix) != PREFIX:
        raise RuntimeError("historical prefix construction is too short")
    # Verify prompt-prefix text can be restored without changing token IDs.
    prefix_text = tok.decode(prefix, skip_special_tokens=False)
    if tok.encode(prefix_text, add_special_tokens=False).ids != prefix:
        raise RuntimeError("QUASAR tokenizer cannot round-trip the shared prefix")
    prompts, suffixes = {"primer": prefix}, {}
    for c in CONCURRENCIES:
        for r in range(ROUNDS):
            for i in range(c):
                key = f"c{c}-r{r}-i{i}"
                suffix = tok.encode(
                    f" Unique request suffix {key} ", add_special_tokens=False
                ).ids
                k = 0
                while len(suffix) < SUFFIX:
                    suffix.extend(
                        tok.encode(f" {key} payload{k} ", add_special_tokens=False).ids
                    )
                    k += 1
                suffix = suffix[:SUFFIX]
                if len(suffix) != SUFFIX:
                    raise RuntimeError(f"{key}: suffix token count {len(suffix)}")
                suffixes[key] = suffix
                prompts[key] = prefix + suffix
    if len({tuple(s) for s in suffixes.values()}) != len(suffixes):
        raise RuntimeError("duplicate suffixes")
    validation_suffix = list(suffixes["c1-r0-i0"])
    validation_suffix[0] = 50
    prompts["validation"] = prefix + validation_suffix
    suffixes["validation"] = validation_suffix
    fixture = {
        "model_tokenizer": str(a.tokenizer),
        "tokenizer_json_sha256": sha((a.tokenizer / "tokenizer.json").read_bytes()),
        "tokenizer_class": type(tok).__name__,
        "prefix_tokens": PREFIX,
        "suffix_tokens": SUFFIX,
        "input_tokens": PREFIX + SUFFIX,
        "output_tokens": OUTPUT,
        "concurrencies": CONCURRENCIES,
        "rounds_including_warmup": ROUNDS,
        "prefix_ids_sha256": sha(json.dumps(prefix, separators=(",", ":")).encode()),
        "prefix_ids": prefix,
        "prompts": prompts,
        "suffixes": suffixes,
    }
    raw = json.dumps(fixture, separators=(",", ":")).encode()
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_bytes(raw)
    a.out.with_suffix(a.out.suffix + ".sha256").write_text(sha(raw) + "\n")
    print(
        json.dumps(
            {
                k: fixture[k]
                for k in (
                    "tokenizer_class",
                    "prefix_tokens",
                    "suffix_tokens",
                    "input_tokens",
                    "output_tokens",
                    "concurrencies",
                    "rounds_including_warmup",
                    "prefix_ids_sha256",
                )
            }
        )
    )


if __name__ == "__main__":
    main()
