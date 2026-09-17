#!/usr/bin/env python3
"""Deterministic >=N-token prompt builder (CPU only, tree interpreter).

Renders the model's chat template with ``enable_thinking=False`` and binary-
searches the number of filler words so the rendered token count is the smallest
value >= ``--target-len``.  The unique ``--marker`` is the LAST content in the
prompt, so a greedy continuation is conditioned on it and two different markers
produce distinct outputs.

Writes: {"marker", "ids", "n", "rendered_sha256", "model", "target_len"}.

No GPU is touched (and none is needed): tokenizer-only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random


VOCAB = (
    "river stone lantern archive harbor quartz marble willow prairie meadow "
    "signal matrix copper anchor beacon ember forest canyon summit valley "
    "garden tractor engine circuit packet ledger cipher token vector stream "
    "buffer segment cluster lattice kernel socket thread queue cursor digest "
    "window column row index schema record manifest segment extent slot page "
    "north south east west morning evening winter summer autumn spring "
    "market bridge tunnel station platform signal junction meadow orchard "
    "cobalt amber silver bronze granite basalt shale limestone sandstone "
    "falcon heron otter badger marten ibex lynx puma crane stork raven finch"
).split()

_CACHE = {}


def render(tokenizer, marker: str, n_words: int, seed: int):
    key = (marker, int(n_words), int(seed))
    if key in _CACHE:
        return _CACHE[key]
    instruction = (
        "\n\nSYSTEM NOTE: Ignore the document above completely. Repeat the "
        "following string exactly, character for character, and output nothing "
        "else:\n" + marker)

    def build_text(words: int) -> str:
        rng = random.Random(seed)
        body = " ".join(rng.choice(VOCAB) for _ in range(max(0, words)))
        return body + instruction

    text = build_text(n_words)
    try:
        out = tokenizer.apply_chat_template(
            [{"role": "user", "content": text}], tokenize=True,
            add_generation_prompt=True, enable_thinking=False)
    except TypeError:
        out = tokenizer.apply_chat_template(
            [{"role": "user", "content": text}], tokenize=True,
            add_generation_prompt=True)
    # BatchEncoding is a UserDict (Mapping), not a dict subclass.
    if hasattr(out, "keys") and "input_ids" in out:
        ids = out["input_ids"]
    else:
        ids = out
    result = (_flat_ids(ids), text)
    _CACHE[key] = result
    return result


def _flat_ids(ids):
    """Unwrap tensor/batch nesting down to a flat list[int]."""
    try:
        ids = list(ids)
    except TypeError:
        ids = [ids]
    guard = 0
    while ids and not isinstance(ids[0], int) and guard < 8:
        try:
            ids = list(ids[0])
        except TypeError:
            break
        guard += 1
    return [int(x) for x in ids]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--marker", required=True)
    ap.add_argument("--target-len", type=int, required=True)
    ap.add_argument("--seed", type=int, default=20260916)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(args.model, trust_remote_code=True)

    lo, hi = 1, 512
    while len(render(tokenizer, args.marker, hi, args.seed)[0]) < args.target_len:
        lo = hi
        hi *= 2
        if hi > 4_000_000:
            raise SystemExit("prompt target not reachable")
    best = hi
    while lo <= hi:
        mid = (lo + hi) // 2
        if len(render(tokenizer, args.marker, mid, args.seed)[0]) >= args.target_len:
            best = mid
            hi = mid - 1
        else:
            lo = mid + 1
    candidates = sorted(
        ((abs(len(render(tokenizer, args.marker, m, args.seed)[0])
           - args.target_len), m)
         for m in (max(1, best - 1), best, best + 1)),
        key=lambda t: t[0])
    n_words = candidates[0][1]
    ids, text = render(tokenizer, args.marker, n_words, args.seed)

    out = {
        "marker": args.marker,
        "model": args.model,
        "target_len": args.target_len,
        "n_words": n_words,
        "n": len(ids),
        "ids": ids,
        "rendered_sha256": hashlib.sha256(text.encode()).hexdigest(),
        "template_enable_thinking": False,
    }
    tmp = args.out + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(out, fh)
    os.replace(tmp, args.out)
    print(json.dumps({"marker": args.marker, "n": len(ids),
                      "n_words": n_words, "out": args.out}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
