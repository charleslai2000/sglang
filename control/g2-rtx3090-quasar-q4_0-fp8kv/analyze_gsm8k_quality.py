#!/usr/bin/env python3
"""Audit GSM8K score protocol, stop-boundary and paired outcomes."""

import json, random, re, math, hashlib
from pathlib import Path

START = re.compile(r'(?m)^\{"doc_id": \d+, "prompt":')


def rows(p):
    s = Path(p).read_text()
    m = list(START.finditer(s))
    out = []
    for i, x in enumerate(m):
        out.append(
            json.loads(
                s[x.start() : m[i + 1].start() if i + 1 < len(m) else len(s)]
                .strip()
                .replace("\n", "\\n")
            )
        )
    return out


def score(text, target):
    m = re.findall(r"####\s+(-?[0-9.,]+)", text)
    g = re.findall(r"#### (-?[0-9.,]+)", target)
    p = m[0] if m else "[invalid]"
    gold = g[-1] if g else "[invalid]"
    p = p.replace(",", "").replace("$", "")
    gold = gold.replace(",", "").replace("$", "")
    return bool(
        p.lower() == gold.lower()
        or (p.endswith(".") and p[:-1].lower() == gold.lower())
    )


def main():
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("bf16")
    p.add_argument("e5m2")
    p.add_argument("--out", required=True)
    a = p.parse_args()
    b = rows(a.bf16)
    e = rows(a.e5m2)
    assert len(b) == len(e) == 1319
    for i, (x, y) in enumerate(zip(b, e)):
        assert (
            x["doc_id"] == y["doc_id"] == i
            and x["prompt"] == y["prompt"]
            and x["target"] == y["target"]
        )
    both = bo = eo = bw = ans_diff = ids_diff = prompt_ids_diff = score_diff = (
        stop_leak
    ) = 0
    transitions = []
    raw_delta = []
    for x, y in zip(b, e):
        xb = score(x["answer"], x["target"])
        ye = score(y["answer"], y["target"])
        assert xb == x["score"]["correct"] and ye == y["score"]["correct"], (
            "score drift",
            x["doc_id"],
            xb,
            x["score"],
        )
        if xb and ye:
            both += 1
        elif xb:
            bo += 1
        elif ye:
            eo += 1
        else:
            bw += 1
        ans_diff += x["answer"] != y["answer"]
        ids_diff += x["output_token_ids"] != y["output_token_ids"]
        prompt_ids_diff += x["prompt_token_ids"] != y["prompt_token_ids"]
        score_diff += xb != ye
        stop_leak += "Question:" in x["answer"] or "Question:" in y["answer"]
        if x["finish_reason"] == "length" or y["finish_reason"] == "length":
            pass
        transitions.append(
            {
                "doc_id": x["doc_id"],
                "bf16_correct": xb,
                "e5m2_correct": ye,
                "bf16_prediction": x["score"]["prediction"],
                "e5m2_prediction": y["score"]["prediction"],
                "bf16_finish": x["finish_reason"],
                "e5m2_finish": y["finish_reason"],
            }
        )
        if xb != ye:
            raw_delta.append((int(ye) - int(xb)))
    # Paired bootstrap on accuracy delta, fixed seed and 20k replicates.
    rng = random.Random(20261106)
    means = []
    diff = [
        int(y["score"]["correct"]) - int(x["score"]["correct"]) for x, y in zip(b, e)
    ]
    for _ in range(20000):
        means.append(sum(diff[rng.randrange(1319)] for _ in range(1319)) / 1319)
    means.sort()
    ci = [means[499] * 100, means[19499] * 100]
    result = {
        "n": 1319,
        "bf16_correct": sum(x["score"]["correct"] for x in b),
        "e5m2_correct": sum(x["score"]["correct"] for x in e),
        "both_correct": both,
        "both_wrong": bw,
        "bf16_only_correct": bo,
        "e5m2_only_correct": eo,
        "delta_pp": 100 * (eo - bo) / 1319,
        "paired_bootstrap_20k_seed_20261106_95ci_pp": ci,
        "answers_differ": ans_diff,
        "output_token_sequences_differ": ids_diff,
        "prompt_ids_differ": prompt_ids_diff,
        "prompt_text_equal": all(x["prompt"] == y["prompt"] for x, y in zip(b, e)),
        "per_item_scores_recompute_match": True,
        "contains_next_question_text": stop_leak,
        "bf16_invalid_marker": sum(not x["score"]["has_answer_marker"] for x in b),
        "e5m2_invalid_marker": sum(not x["score"]["has_answer_marker"] for x in e),
        "bf16_cap_hits": sum(x["finish_reason"] == "length" for x in b),
        "e5m2_cap_hits": sum(x["finish_reason"] == "length" for x in e),
        "both_prompt_token_ids_equal": prompt_ids_diff == 0,
        "items": transitions,
    }
    Path(a.out).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "items"}, indent=2))


if __name__ == "__main__":
    main()
