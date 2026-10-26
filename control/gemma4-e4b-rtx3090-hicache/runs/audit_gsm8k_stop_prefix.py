#!/usr/bin/env python3
"""Offline audit of GSM8K score flips and decoded-prefix boundaries.

Sample JSONL preserves prompt text and decoded responses, but not actual runtime
request/output token IDs for the old run. This script therefore compares decoded
character prefixes only and explicitly does not claim token-ID prefix parity.
"""

import argparse
import json
import re
from pathlib import Path

ROW = re.compile(r'(?m)^\{"doc_id": (\d+), "doc":')
ANSWER = re.compile(r"#### (-?[0-9.,]+)")
QUESTION = re.compile(r"Question:")


def load(path):
    text = Path(path).read_text()
    matches = list(ROW.finditer(text))
    rows = {}
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        row = json.loads(text[match.start() : end].strip().replace("\n", "\\n"))
        rows[int(row["doc_id"])] = row
    return rows


def answer(text):
    match = ANSWER.search(text)
    return match.group(1).replace(",", "") if match else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("old_samples")
    ap.add_argument("new_samples")
    ap.add_argument("--arm", choices=("bf16", "e5m2"), required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    old, new = load(args.old_samples), load(args.new_samples)
    assert len(old) == len(new) == 1319 and old.keys() == new.keys()
    totals = {
        "arm": args.arm,
        "n": len(old),
        "score_flips": 0,
        "old_correct_new_wrong": 0,
        "old_wrong_new_correct": 0,
        "old_first_hash_pre_question": 0,
        "old_first_hash_post_question": 0,
        "old_question_missing_in_text": 0,
        "flip_old_hash_post_question": 0,
        "flip_old_hash_pre_question_but_decoded_prefix_differs_before_question": 0,
        "flip_decoded_prefix_identical_through_question": 0,
        "flip_decoded_prefix_first_difference_char_before_question": 0,
        "old_score_from_post_question_answer_correct": 0,
        "new_score_from_stop_protected_first_answer_correct": 0,
        "runtime_old_request_ids_available": False,
        "runtime_old_output_token_ids_available": False,
    }
    detail = []
    for doc_id in old:
        a, b = old[doc_id], new[doc_id]
        old_text, new_text = a["resps"][0][0], b["resps"][0][0]
        gold = a["doc"]["answer"].split("####")[-1].strip().replace(",", "")
        old_answer, new_answer = answer(old_text), answer(new_text)
        old_ok, new_ok = old_answer == gold, new_answer == gold
        question = QUESTION.search(old_text)
        marker = ANSWER.search(old_text)
        qpos = question.start() if question else len(old_text)
        hpos = marker.start() if marker else None
        if question:
            if marker and hpos >= qpos:
                totals["old_first_hash_post_question"] += 1
            else:
                totals["old_first_hash_pre_question"] += 1
        else:
            totals["old_question_missing_in_text"] += 1
        if not (old_ok != new_ok):
            continue
        totals["score_flips"] += 1
        if old_ok:
            totals["old_correct_new_wrong"] += 1
        else:
            totals["old_wrong_new_correct"] += 1
        common = 0
        while (
            common < min(len(old_text), len(new_text))
            and old_text[common] == new_text[common]
        ):
            common += 1
        same_through_question = common >= qpos
        if same_through_question:
            totals["flip_decoded_prefix_identical_through_question"] += 1
        else:
            totals["flip_decoded_prefix_first_difference_char_before_question"] += 1
        if marker and question and hpos >= qpos:
            totals["flip_old_hash_post_question"] += 1
            if old_ok:
                totals["old_score_from_post_question_answer_correct"] += 1
        elif not same_through_question:
            totals[
                "flip_old_hash_pre_question_but_decoded_prefix_differs_before_question"
            ] += 1
        if new_ok:
            totals["new_score_from_stop_protected_first_answer_correct"] += 1
        detail.append(
            {
                "doc_id": doc_id,
                "old_correct": old_ok,
                "new_correct": new_ok,
                "gold": gold,
                "old_first_answer": old_answer,
                "new_first_answer": new_answer,
                "old_first_question_char_offset": question.start()
                if question
                else None,
                "old_first_hash_char_offset": marker.start() if marker else None,
                "old_first_hash_pre_question": bool(marker and marker.start() < qpos),
                "decoded_common_prefix_chars": common,
                "decoded_prefix_same_through_first_question": same_through_question,
                "old_prompt_hash": a.get("prompt_hash"),
                "new_prompt_hash": b.get("prompt_hash"),
                "prompt_text_identical": a["arguments"]["gen_args_0"]["arg_0"]
                == b["arguments"]["gen_args_0"]["arg_0"],
                "old_saved_until": a["arguments"]["gen_args_0"].get(
                    "until", ["</s>", "<|im_end|>"]
                ),
                "new_saved_until": b["arguments"]["gen_args_0"].get(
                    "until", ["Question:", "</s>", "<|im_end|>"]
                ),
            }
        )
    out = {"summary": totals, "flips": detail}
    Path(args.out).write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(totals, indent=2))


if __name__ == "__main__":
    main()
