#!/usr/bin/env python3
import argparse, json, re
from pathlib import Path
from lm_eval.api.metrics import exact_match_hf_evaluate

p = argparse.ArgumentParser()
p.add_argument("samples")
p.add_argument("--out", required=True)
a = p.parse_args()
samples = [json.loads(x) for x in Path(a.samples).read_text().splitlines()]
assert len(samples) == 1319 and {int(x["doc_id"]) for x in samples} == set(range(1319))
audits = {
    int(x["doc_id"]): x
    for x in map(
        json.loads,
        Path(a.samples).with_name("stop-audit.jsonl").read_text().splitlines(),
    )
}
assert len(audits) == 1319 and set(audits) == set(range(1319))
correct = 0
stops = {}
lengths = {}
for s in samples:
    i = int(s["doc_id"])
    x = audits[i]
    text = s["resps"][0][0]
    assert (
        x["raw_completion"] == text
        and x["prompt_ids"][0] == 2
        and x["prompt_protocol"] == "gemma-explicit-bos-v1"
    )
    assert (
        x["source_sha"]
        and s["audit"]["prompt_ids"] == x["prompt_ids"]
        and s["audit"]["output_ids"] == x["response_token_ids"]
    )
    matches = re.findall(r"#### (-?[0-9.,]+)", text)
    pred = matches[0] if matches else "[invalid]"
    score = bool(
        exact_match_hf_evaluate(
            [pred],
            [s["doc"]["answer"]],
            regexes_to_ignore=[",", r"\\$", r"(?s).*#### ", r"\\.$"],
            ignore_case=True,
            ignore_punctuation=False,
        )["exact_match"]
    )
    assert int(float(s["exact_match"])) == int(score)
    correct += score
    stops[x["matched_stop"]] = stops.get(x["matched_stop"], 0) + 1
    lengths[x["finish_reason"]] = lengths.get(x["finish_reason"], 0) + 1
result = {
    "n": len(samples),
    "correct": correct,
    "accuracy": correct / len(samples),
    "prompt_protocol": "gemma-explicit-bos-v1",
    "prompt_bos_token_id": 2,
    "finish_reasons": lengths,
    "matched_stops": stops,
    "source_sha": samples[0]["audit"]["source_sha"],
}
Path(a.out).write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps(result, indent=2))
