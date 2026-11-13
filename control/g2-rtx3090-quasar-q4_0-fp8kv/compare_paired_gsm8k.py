#!/usr/bin/env python3
"""Pair complete multiline lm-eval-compatible GSM8K result records."""

import argparse, hashlib, json, re
from pathlib import Path

START = re.compile(r'(?m)^\{"doc_id": \d+, "prompt":')


def read(path):
    text = Path(path).read_text()
    marks = list(START.finditer(text))
    out = []
    for i, m in enumerate(marks):
        chunk = text[
            m.start() : marks[i + 1].start() if i + 1 < len(marks) else len(text)
        ].strip()
        out.append(json.loads(chunk.replace("\n", "\\n")))
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("bf16")
    p.add_argument("e5m2")
    p.add_argument("--out", required=True)
    a = p.parse_args()
    b = read(a.bf16)
    e = read(a.e5m2)
    assert len(b) == len(e) == 1319, (len(b), len(e))
    for i, (x, y) in enumerate(zip(b, e)):
        assert x["doc_id"] == y["doc_id"] == i
        assert x["prompt"] == y["prompt"] and x["target"] == y["target"]
    both = sum(x["score"]["correct"] and y["score"]["correct"] for x, y in zip(b, e))
    bw = sum(
        not x["score"]["correct"] and not y["score"]["correct"] for x, y in zip(b, e)
    )
    bo = sum(x["score"]["correct"] and not y["score"]["correct"] for x, y in zip(b, e))
    eo = sum(not x["score"]["correct"] and y["score"]["correct"] for x, y in zip(b, e))
    out = {
        "n": 1319,
        "bf16_correct": sum(x["score"]["correct"] for x in b),
        "e5m2_correct": sum(x["score"]["correct"] for x in e),
        "both_correct": both,
        "both_wrong": bw,
        "bf16_only_correct": bo,
        "e5m2_only_correct": eo,
        "delta_e5m2_minus_bf16_pp": 100 * (eo - bo) / 1319,
        "answer_changed": sum(x["answer"] != y["answer"] for x, y in zip(b, e)),
        "token_ids_equal": sum(
            x["output_token_ids"] == y["output_token_ids"] for x, y in zip(b, e)
        ),
        "finish_reason_counts": {
            arm: {
                k: sum(r["finish_reason"] == k for r in rows)
                for k in sorted({str(z["finish_reason"]) for z in rows})
            }
            for arm, rows in [("bf16", b), ("e5m2", e)]
        },
        "input_prompt_hashes_equal": all(
            x["prompt_sha256"] == y["prompt_sha256"] for x, y in zip(b, e)
        ),
        "bf16_sha256": hashlib.sha256(Path(a.bf16).read_bytes()).hexdigest(),
        "e5m2_sha256": hashlib.sha256(Path(a.e5m2).read_bytes()).hexdigest(),
        "items": [
            {
                "doc_id": i,
                "question": b[i]["prompt"],
                "target": b[i]["target"],
                "bf16": b[i],
                "e5m2": e[i],
            }
            for i in range(1319)
        ],
    }
    Path(a.out).write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({k: v for k, v in out.items() if k != "items"}, indent=2))


if __name__ == "__main__":
    main()
