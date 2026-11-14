#!/usr/bin/env python3
"""Offline GSM8K paired score and stop-boundary analysis; no service/GPU use."""

import argparse
import json
import re
from pathlib import Path

from lm_eval.api.metrics import exact_match_hf_evaluate

ANSWER = re.compile(r"#### (-?[0-9.,]+)")
QUESTION = re.compile(r"Question:")


def load_json_stream(path):
    text = Path(path).read_text()
    dec = json.JSONDecoder()
    rows, pos = [], 0
    while pos < len(text):
        while pos < len(text) and text[pos].isspace():
            pos += 1
        if pos == len(text):
            break
        row, pos = dec.raw_decode(text, pos)
        rows.append(row)
    output = {int(row["doc_id"]): row for row in rows}
    assert len(output) == 1319
    return output


def score(text, target):
    match = ANSWER.search(text)  # GSM8K strict-match filter is regex + take_first.
    prediction = match.group(1) if match else "[invalid]"
    return bool(
        exact_match_hf_evaluate(
            [prediction],
            [target],
            regexes_to_ignore=[",", r"\\$", r"(?s).*#### ", r"\\.$"],
            ignore_case=True,
            ignore_punctuation=False,
        )["exact_match"]
    )


def compare(old, current):
    cells = {"both_correct": 0, "both_wrong": 0, "old_only": 0, "current_only": 0}
    audit = {
        "old_question_stop_declared": 0,
        "old_question_stop_absent": 0,
        "old_has_question_text": 0,
        "old_first_answer_after_question": 0,
        "old_at_512_cap": 0,
        "current_at_512_cap": 0,
        "flips": 0,
        "flips_decoded_prefix_same_through_question": 0,
        "flips_diverge_before_question": 0,
        "old_correct_answer_after_question": 0,
    }
    detail = []
    for i in range(1319):
        a, b = old[i], current[i]
        assert a["doc"] == b["doc"], f"input mismatch doc={i}"
        at, bt = a["resps"][0][0], b["resps"][0][0]
        ac, bc = score(at, a["doc"]["answer"]), score(bt, b["doc"]["answer"])
        cells[
            "both_correct"
            if ac and bc
            else "both_wrong"
            if not ac and not bc
            else "old_only"
            if ac
            else "current_only"
        ] += 1
        until = (
            a.get("arguments", {})
            .get("gen_args_0", {})
            .get("arg_1", {})
            .get("until", [])
        )
        if "Question:" in until:
            audit["old_question_stop_declared"] += 1
        else:
            audit["old_question_stop_absent"] += 1
        q = QUESTION.search(at)
        m = ANSWER.search(at)
        if q:
            audit["old_has_question_text"] += 1
        after = bool(q and m and m.start() > q.start())
        if after:
            audit["old_first_answer_after_question"] += 1
        if a.get("finish_reason") == "length" or a.get("completion_tokens", 0) >= 512:
            audit["old_at_512_cap"] += 1
        if b.get("finish_reason") == "length" or b.get("completion_tokens", 0) >= 512:
            audit["current_at_512_cap"] += 1
        if ac != bc:
            audit["flips"] += 1
            common = 0
            while common < min(len(at), len(bt)) and at[common] == bt[common]:
                common += 1
            qpos = q.start() if q else len(at)
            same = common >= qpos
            audit[
                "flips_decoded_prefix_same_through_question"
                if same
                else "flips_diverge_before_question"
            ] += 1
            if after and ac:
                audit["old_correct_answer_after_question"] += 1
            detail.append(
                {
                    "doc_id": i,
                    "old_correct": ac,
                    "current_correct": bc,
                    "old_text": at,
                    "current_text": bt,
                    "old_first_answer": m.group(1) if m else None,
                    "old_question_char": q.start() if q else None,
                    "old_first_answer_char": m.start() if m else None,
                    "old_first_answer_after_question": after,
                    "old_until": until,
                    "current_until": b.get("arguments", {})
                    .get("gen_args_0", {})
                    .get("arg_1", {})
                    .get("until", []),
                }
            )
    return {**cells, **audit}, detail


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("historical", help="historical raw lm-eval JSON stream")
    ap.add_argument("current", help="rebuilt current samples.jsonl")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    stats, items = compare(
        load_json_stream(args.historical), load_json_stream(args.current)
    )
    result = {"historical_vs_current": stats, "changed_items": items}
    Path(args.out).write_text(json.dumps(result, ensure_ascii=True, indent=2) + "\n")
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
