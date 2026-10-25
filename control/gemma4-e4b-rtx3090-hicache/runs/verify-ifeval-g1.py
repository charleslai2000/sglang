#!/usr/bin/env python3
"""Re-score and pair the two official 541-item IFEval sample ledgers."""

import argparse
import json
from pathlib import Path

from lm_eval.tasks.ifeval.utils import process_results


def load(path):
    rows = [
        json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()
    ]
    return {int(row["doc"]["key"]): row for row in rows}


def score(doc, response):
    return process_results(doc, [response])["prompt_level_strict_acc"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("bf16")
    parser.add_argument("e5m2")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    bf16, e5m2 = load(args.bf16), load(args.e5m2)
    assert len(bf16) == len(e5m2) == 541, (len(bf16), len(e5m2))
    assert bf16.keys() == e5m2.keys()
    items = []
    for key in sorted(bf16):
        b, e = bf16[key], e5m2[key]
        db, de = b["doc"], e["doc"]
        assert db["prompt"] == de["prompt"]
        bo, eo = b["resps"][0][0], e["resps"][0][0]
        bs = score(db, bo)
        es = score(de, eo)
        items.append(
            {
                "key": key,
                "instruction_id_list": db["instruction_id_list"],
                "kwargs": db["kwargs"],
                "prompt": db["prompt"],
                "bf16_output": bo,
                "e5m2_output": eo,
                "bf16_prompt_strict": bool(bs),
                "e5m2_prompt_strict": bool(es),
                "strict_changed": bool(bs) != bool(es),
            }
        )
    bscore = sum(x["bf16_prompt_strict"] for x in items)
    escore = sum(x["e5m2_prompt_strict"] for x in items)
    summary = {
        "dataset_n": 541,
        "bf16_prompt_strict_correct": bscore,
        "bf16_prompt_strict_accuracy": bscore / 541,
        "e5m2_prompt_strict_correct": escore,
        "e5m2_prompt_strict_accuracy": escore / 541,
        "changed_items": sum(x["strict_changed"] for x in items),
        "bf16_only_correct": [
            x["key"]
            for x in items
            if x["bf16_prompt_strict"] and not x["e5m2_prompt_strict"]
        ],
        "e5m2_only_correct": [
            x["key"]
            for x in items
            if x["e5m2_prompt_strict"] and not x["bf16_prompt_strict"]
        ],
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(
        json.dumps({"summary": summary, "items": items}, ensure_ascii=False, indent=2)
        + "\n"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
