#!/usr/bin/env python3
import argparse
import json
import random
import re
from pathlib import Path

from lm_eval.api.metrics import exact_match_hf_evaluate


def parse_samples(path):
    text = Path(path).read_text()
    decoder = json.JSONDecoder()
    rows, pos = [], 0
    while pos < len(text):
        while pos < len(text) and text[pos].isspace():
            pos += 1
        if pos == len(text):
            break
        row, pos = decoder.raw_decode(text, pos)
        rows.append(row)
    assert len(rows) == 1319, (path, len(rows))
    return {int(row["doc_id"]): row for row in rows}


def score(text, target):
    # Match lm-eval GSM8K filter_list: regex finds every answer, take_first
    # selects the first; then use the task's exact-match normalization.
    matches = list(re.finditer(r"#### (-?[0-9.,]+)", text))
    prediction = matches[0].group(1) if matches else "[invalid]"
    return bool(
        exact_match_hf_evaluate(
            [prediction], [target],
            regexes_to_ignore=[",", r"\\$", r"(?s).*#### ", r"\\.$"],
            ignore_case=True, ignore_punctuation=False,
        )["exact_match"]
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("bf16")
    ap.add_argument("e5m2")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    arms = {"bf16": parse_samples(args.bf16), "e5m2": parse_samples(args.e5m2)}
    audits = {}
    for arm, sample_path in (("bf16", args.bf16), ("e5m2", args.e5m2)):
        audit_path = Path(sample_path).with_name("stop-audit.jsonl")
        audits[arm] = {int(row["doc_id"]): row for row in map(json.loads, audit_path.read_text().splitlines())}
        assert len(audits[arm]) == 1319 and set(audits[arm]) == set(range(1319))
        for doc_id, sample in arms[arm].items():
            audit = audits[arm][doc_id]
            assert sample["resps"][0][0] == audit["raw_completion"]
            assert sample["audit"]["prompt_ids"] == audit["prompt_ids"]
            assert sample["audit"]["output_ids"] == audit["response_token_ids"]
            assert sample["audit"]["finish_reason"] == audit["finish_reason"]
            assert sample["audit"]["matched_stop"] == audit["matched_stop"]
    assert arms["bf16"].keys() == arms["e5m2"].keys() == set(range(1319))
    cells = {"both_correct": 0, "both_wrong": 0, "bf16_only": 0, "e5m2_only": 0}
    deltas, different = [], []
    for i in range(1319):
        b, e = arms["bf16"][i], arms["e5m2"][i]
        assert b["doc"] == e["doc"] and b["arguments"] == e["arguments"], (
            f"input mismatch: {i}"
        )
        bt, et = b["resps"][0][0], e["resps"][0][0]
        bc, ec = score(bt, b["doc"]["answer"]), score(et, e["doc"]["answer"])
        assert float(b["exact_match"]) == int(bc) and float(e["exact_match"]) == int(ec), f"official scorer mismatch {i}"
        cells[
            "both_correct"
            if bc and ec
            else "both_wrong"
            if not bc and not ec
            else "bf16_only"
            if bc
            else "e5m2_only"
        ] += 1
        deltas.append(int(ec) - int(bc))
        if bc != ec or b["resps"][0] != e["resps"][0]:
            ba, ea = audits["bf16"][i], audits["e5m2"][i]
            different.append(
                {
                    "doc_id": i,
                    "bf16_correct": bc,
                    "e5m2_correct": ec,
                    "bf16_text": bt,
                    "e5m2_text": et,
                    "bf16_output_ids": ba["response_token_ids"],
                    "e5m2_output_ids": ea["response_token_ids"],
                    "bf16_finish_reason": ba["finish_reason"],
                    "e5m2_finish_reason": ea["finish_reason"],
                    "bf16_matched_stop": ba["matched_stop"],
                    "e5m2_matched_stop": ea["matched_stop"],
                }
            )
    rng = random.Random(20261114)
    boot = sorted(
        sum(deltas[rng.randrange(1319)] for _ in range(1319)) / 1319 * 100
        for _ in range(20000)
    )
    result = {
        "n": 1319,
        "bf16_correct": cells["both_correct"] + cells["bf16_only"],
        "e5m2_correct": cells["both_correct"] + cells["e5m2_only"],
        "bf16_accuracy": (cells["both_correct"] + cells["bf16_only"]) / 1319,
        "e5m2_accuracy": (cells["both_correct"] + cells["e5m2_only"]) / 1319,
        "paired": cells,
        "delta_percentage_points": (cells["e5m2_only"] - cells["bf16_only"])
        / 1319
        * 100,
        "paired_bootstrap_95ci_percentage_points": [boot[499], boot[19499]],
        "bootstrap_replicates": 20000,
        "bootstrap_seed": 20261114,
        "different_items": different,
    }
    Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            {k: v for k, v in result.items() if k != "different_items"}, indent=2
        )
    )


if __name__ == "__main__":
    main()
