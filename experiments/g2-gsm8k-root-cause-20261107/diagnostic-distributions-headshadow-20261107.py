#!/usr/bin/env python3
"""Analyze complete 262144-token SGLang/llama.cpp log-prob vectors for fixed 14."""

import glob, json, math, os
from pathlib import Path

D = Path("/data/sglang-hicache/g2-quasar-runs/20261107T-g2-first-logits")
ll = {
    json.loads(l)["doc_id"]: json.loads(l)["response"]["completion_probabilities"][0][
        "top_logprobs"
    ]
    for l in (D / "llama-first-top1.jsonl").open()
}
rows = []


def lse(v):
    m = max(v)
    return m + math.log(sum(math.exp(z - m) for z in v))


for f in glob.glob(str(D / "toplogprobs-*-correct.json")):
    x = json.load(open(f))
    i = int(os.path.basename(f).split("-")[1])
    sg = x["response"]["meta_info"]["output_top_logprobs"][0]
    lm = ll[i]
    assert len(sg) == len(lm) == 262144
    a = [float(z[0]) for z in sg]
    b = [float(z["logprob"]) for z in lm]
    za, zb = lse(a), lse(b)
    a = [z - za for z in a]
    b = [z - zb for z in b]
    pa = [math.exp(z) for z in a]
    pb = [math.exp(z) for z in b]
    ia = max(range(len(a)), key=a.__getitem__)
    ib = max(range(len(b)), key=b.__getitem__)
    sorted_a = sorted(a, reverse=True)
    sorted_b = sorted(b, reverse=True)
    klab = sum(p * (u - v) for p, u, v in zip(pa, a, b))
    klba = sum(p * (u - v) for p, u, v in zip(pb, b, a))
    js = 0.5 * sum(
        p * (u - math.log((p + q) / 2)) for p, q, u in zip(pa, pb, a) if p
    ) + 0.5 * sum(q * (v - math.log((p + q) / 2)) for p, q, v in zip(pa, pb, b) if q)
    # cross entropy H(P_sglang,Q_llama), reverse
    cab = -sum(p * v for p, v in zip(pa, b))
    cba = -sum(p * v for p, v in zip(pb, a))
    rows.append(
        {
            "doc_id": i,
            "sglang_top1": sg[ia][1],
            "llama_top1": lm[ib]["id"],
            "sglang_margin": sorted_a[0] - sorted_a[1],
            "llama_margin": sorted_b[0] - sorted_b[1],
            "H_sglang_to_llama": cab,
            "H_llama_to_sglang": cba,
            "KL_sglang_llama": klab,
            "KL_llama_sglang": klba,
            "JS_nats": js,
            "overlap_coefficient": sum(min(p, q) for p, q in zip(pa, pb)),
        }
    )
rows.sort(key=lambda z: z["doc_id"])
out = D / "distribution-comparison-14.json"
out.write_text(
    json.dumps(
        {
            "scope": "fixed 14 only",
            "semantics": "both APIs return per-engine normalized full-vocabulary log probabilities before greedy token selection; not raw logits; stop/penalty processors configured neutral",
            "rows": rows,
            "means": {
                k: sum(r[k] for r in rows) / len(rows)
                for k in rows[0]
                if isinstance(rows[0][k], float)
            },
        },
        indent=2,
    )
    + "\n"
)
for r in rows:
    print(r)
print("saved", out)
