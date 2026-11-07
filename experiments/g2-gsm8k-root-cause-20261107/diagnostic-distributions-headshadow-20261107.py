#!/usr/bin/env python3
"""Analyze full-vocabulary log-probability vectors for the fixed 14 prompts."""

import glob
import json
import math
import os
from pathlib import Path

D = Path("/data/sglang-hicache/g2-quasar-runs/20261107T-g2-first-logits")
ll = {
    json.loads(line)["doc_id"]: json.loads(line)["response"][
        "completion_probabilities"
    ][0]["top_logprobs"]
    for line in (D / "llama-first-top1.jsonl").open()
}
rows = []


def logsumexp(values):
    maximum = max(values)
    return maximum + math.log(sum(math.exp(value - maximum) for value in values))


for filename in glob.glob(str(D / "toplogprobs-*-correct.json")):
    response = json.load(open(filename))
    doc_id = int(os.path.basename(filename).split("-")[1])
    sglang = response["response"]["meta_info"]["output_top_logprobs"][0]
    llama = ll[doc_id]
    assert len(sglang) == len(llama) == 262144
    s_ids = [int(item[1]) for item in sglang]
    l_ids = [int(item["id"]) for item in llama]
    assert len(set(s_ids)) == len(set(l_ids)) == 262144
    assert set(s_ids) == set(l_ids), "vocab coverage/ID mismatch"
    s_map = {int(item[1]): float(item[0]) for item in sglang}
    l_map = {int(item["id"]): float(item["logprob"]) for item in llama}
    token_ids = s_ids
    s_logp = [s_map[token] for token in token_ids]
    l_logp = [l_map[token] for token in token_ids]
    s_norm, l_norm = logsumexp(s_logp), logsumexp(l_logp)
    s_logp = [value - s_norm for value in s_logp]
    l_logp = [value - l_norm for value in l_logp]
    s_prob = [math.exp(value) for value in s_logp]
    l_prob = [math.exp(value) for value in l_logp]
    s_order = sorted(s_logp, reverse=True)
    l_order = sorted(l_logp, reverse=True)
    s_top = max(range(len(s_logp)), key=s_logp.__getitem__)
    l_top = max(range(len(l_logp)), key=l_logp.__getitem__)
    kl_s_l = sum(p * (s - l) for p, s, l in zip(s_prob, s_logp, l_logp))
    kl_l_s = sum(p * (l - s) for p, l, s in zip(l_prob, l_logp, s_logp))
    js = 0.5 * sum(
        p * (s - math.log((p + q) / 2)) for p, q, s in zip(s_prob, l_prob, s_logp) if p
    ) + 0.5 * sum(
        q * (l - math.log((p + q) / 2)) for p, q, l in zip(s_prob, l_prob, l_logp) if q
    )
    rows.append(
        {
            "doc_id": doc_id,
            "sglang_top1": token_ids[s_top],
            "llama_top1": token_ids[l_top],
            "sglang_margin": s_order[0] - s_order[1],
            "llama_margin": l_order[0] - l_order[1],
            "H_sglang_to_llama": -sum(p * q for p, q in zip(s_prob, l_logp)),
            "H_llama_to_sglang": -sum(p * q for p, q in zip(l_prob, s_logp)),
            "KL_sglang_llama": kl_s_l,
            "KL_llama_sglang": kl_l_s,
            "JS_nats": js,
            "overlap_coefficient": sum(min(p, q) for p, q in zip(s_prob, l_prob)),
        }
    )
rows.sort(key=lambda row: row["doc_id"])
output = D / "distribution-comparison-14.json"
output.write_text(
    json.dumps(
        {
            "scope": "fixed 14 only",
            "semantics": "Full per-engine normalized log probabilities at the first generated position, before greedy selection. APIs return rows independently ranked; values are aligned by token ID. Not raw logits.",
            "rows": rows,
            "means": {
                key: sum(row[key] for row in rows) / len(rows)
                for key in rows[0]
                if isinstance(rows[0][key], float)
            },
        },
        indent=2,
    )
    + "\n"
)
for row in rows:
    print(row)
print("saved", output)
