#!/usr/bin/env python3
import argparse, json, re
from pathlib import Path

from lm_eval.api.metrics import exact_match_hf_evaluate

p = argparse.ArgumentParser()
p.add_argument("records")
p.add_argument("sglang_samples")
p.add_argument("--out", required=True)
a = p.parse_args()
ref = json.loads(Path(a.records).read_text())["records"]
sg = {
    int(x["doc_id"]): x
    for x in map(json.loads, Path(a.sglang_samples).read_text().splitlines())
}
assert len(ref) == len(sg) == 1319 and {int(x["doc_id"]) for x in ref} == set(
    range(1319)
) == set(sg)
match = 0
exact_ids = 0
diffs = []
for r in ref:
    i = int(r["doc_id"])
    s = sg[i]
    assert (
        r["original_prompt_ids"][0] == 2 and r["prompt_ids"] == s["audit"]["prompt_ids"]
    )
    assert r["prompt_sha256"] == s["audit"]["prompt_sha256"]
    text = r["text"]
    found = re.findall(r"#### (-?[0-9.,]+)", text)
    pred = found[0] if found else "[invalid]"
    ans = s["doc"]["answer"]
    ok = bool(
        exact_match_hf_evaluate(
            [pred],
            [ans],
            regexes_to_ignore=[",", r"\\$", r"(?s).*#### ", r"\\.$"],
            ignore_case=True,
            ignore_punctuation=False,
        )["exact_match"]
    )
    match += ok
    ids = r["token_ids"]
    sids = s["audit"]["output_ids"]
    exact_ids += ids == sids
    if ids != sids:
        d = next(
            (j for j, (x, y) in enumerate(zip(ids, sids)) if x != y),
            min(len(ids), len(sids)),
        )
        diffs.append(
            {
                "doc_id": i,
                "first_token_divergence": d,
                "vllm_tokens": len(ids),
                "sglang_tokens": len(sids),
                "vllm_correct": ok,
            }
        )
result = {
    "n": 1319,
    "vllm_correct": match,
    "vllm_accuracy": match / 1319,
    "sglang_bf16kv_correct": 1079,
    "sglang_accuracy": 1079 / 1319,
    "output_token_ids_exact": exact_ids,
    "different_ids": len(diffs),
    "different_ids_detail": diffs,
    "scorer": "lm-eval 0.4.13 exact_match_hf_evaluate; first #### answer",
    "reference": "same W4A16 checkpoint; vLLM BF16 compute, auto/BF16 KV; greedy; explicit BOS",
}
Path(a.out).write_text(json.dumps(result, indent=2) + "\n")
print(
    json.dumps(
        {k: v for k, v in result.items() if k != "different_ids_detail"}, indent=2
    )
)
