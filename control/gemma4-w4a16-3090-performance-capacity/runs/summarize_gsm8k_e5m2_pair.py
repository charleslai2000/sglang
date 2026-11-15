#!/usr/bin/env python3
import json
import re
import sys
from pathlib import Path
from lm_eval.api.metrics import exact_match_hf_evaluate

bf_path, e_path = map(Path, sys.argv[1:3])


def records(path):
    d = json.JSONDecoder()
    text = path.read_text()
    out = []
    p = 0
    while p < len(text):
        while p < len(text) and text[p].isspace():
            p += 1
        if p < len(text):
            x, p = d.raw_decode(text, p)
            out.append(x)
    assert len(out) == 1319
    return {int(x["doc_id"]): x for x in out}


def exact(text, target):
    m = re.search(r"#### (-?[0-9.,]+)", text)
    pred = m.group(1) if m else "[invalid]"
    return bool(
        exact_match_hf_evaluate(
            [pred],
            [target],
            regexes_to_ignore=[",", r"\\$", r"(?s).*#### ", r"\\.$"],
            ignore_case=True,
            ignore_punctuation=False,
        )["exact_match"]
    )


B, E = records(bf_path), records(e_path)
assert B.keys() == E.keys() == set(range(1319))
assert all(B[i]["audit"]["prompt_ids"] == E[i]["audit"]["prompt_ids"] for i in B)
assert all(B[i]["audit"]["output_ids"] == B[i]["audit"]["output_ids"] for i in B)
counts = {"both_correct": 0, "both_wrong": 0, "bf16_only": 0, "e5m2_only": 0}
tok = text = 0
for i in B:
    target = B[i]["doc"]["answer"].split("####")[-1].strip()
    b = exact(B[i]["resps"][0][0], target)
    e = exact(E[i]["resps"][0][0], target)
    counts[
        "both_correct"
        if b and e
        else "both_wrong"
        if not b and not e
        else "bf16_only"
        if b
        else "e5m2_only"
    ] += 1
    tok += B[i]["audit"]["output_ids"] != E[i]["audit"]["output_ids"]
    text += B[i]["resps"][0] != E[i]["resps"][0]
result = {
    "paired": counts,
    "token_sequence_different": tok,
    "text_different": text,
    "n": 1319,
}
out = e_path.parent / "summary.json"
out.write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps(result, indent=2))
