#!/usr/bin/env python3
"""Enforce stop/finish invariants against each lm-eval sample's doc_id."""

import argparse, json, re
from pathlib import Path

START = re.compile(r'(?m)^\{"doc_id": \d+, "doc":')


def parse_samples(p):
    s = Path(p).read_text()
    marks = [m.start() for m in START.finditer(s)]
    rows = []
    for i, x in enumerate(marks):
        rows.append(
            json.loads(
                s[x : marks[i + 1] if i + 1 < len(marks) else len(s)]
                .strip()
                .replace("\n", "\\n")
            )
        )
    return rows


ap = argparse.ArgumentParser()
ap.add_argument("samples")
ap.add_argument("audit")
ap.add_argument("--arm", required=True)
ap.add_argument("--out", required=True)
a = ap.parse_args()
rows = parse_samples(a.samples)
audit = [json.loads(x) for x in Path(a.audit).read_text().splitlines() if x.strip()]
by = {str(x["doc_id"]): x for x in audit}
assert len(rows) == 1319 and len(audit) == 1319 and len(by) == 1319, (
    len(rows),
    len(audit),
    len(by),
)
errors = []
for r in rows:
    k = str(r["doc_id"])
    x = by.get(k)
    text = r["resps"][0][0]
    if not x:
        errors.append({"doc_id": k, "error": "missing audit"})
        continue
    if x["finish_reason"] == "stop" and x["matched_stop"] not in ("Question:", 106):
        errors.append(
            {"doc_id": k, "error": "unexpected-stop-match", "value": x["matched_stop"]}
        )
    if x["finish_reason"] == "length" and int(x["completion_tokens"]) != 512:
        errors.append({"doc_id": k, "error": "inconsistent-length-finish"})
    if x["finish_reason"] not in ("stop", "length"):
        errors.append({"doc_id": k, "error": "unexpected-finish-reason", "value": x["finish_reason"]})
    # Keep repetitive/non-compliant generations as invalid predictions; score
    # the full pinned-protocol sample set using the official first-match filter.
    if int(x["prompt_tokens"]) < 1:
        errors.append({"doc_id": k, "error": "missing-prompt-token-count"})
    if "Question:" not in x["requested_stop"]:
        errors.append({"doc_id": k, "error": "question-stop-not-requested"})
    if not x["raw_completion"]:
        errors.append({"doc_id": k, "error": "empty-completion"})
    if "Question:" in text:
        errors.append({"doc_id": k, "error": "question-leakage-in-output"})
    matches = re.findall(r"#### (\-?[0-9\.\,]+)", text)
    expected = matches[0].strip() if matches else "[invalid]"
    if r["filtered_resps"][0] != expected:
        errors.append({"doc_id": k, "error": "strict-score-input-mismatch"})
summary = {
    "arm": a.arm,
    "samples": len(rows),
    "audit_records": len(audit),
    "finish_reason_stop": sum(x["finish_reason"] == "stop" for x in audit),
    "matched_question": sum(x["matched_stop"] == "Question:" for x in audit),
    "errors": errors,
}
Path(a.out).write_text(json.dumps(summary, indent=2) + "\n")
print(json.dumps(summary, indent=2))
assert not errors
