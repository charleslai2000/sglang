#!/usr/bin/env python3
"""Read lm-eval sample artifacts, verify complete paired set, bootstrap delta."""

import argparse, json, random, re
from pathlib import Path
from lm_eval.api.metrics import exact_match_hf_evaluate

START = re.compile(r'(?m)^\{"doc_id": \d+, "doc":')


def read(path):
    text = Path(path).read_text()
    starts = [m.start() for m in START.finditer(text)]
    rows = []
    for i, start in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else len(text)
        chunk = text[start:end].strip()
        # lm-eval 0.4.13's JSONL logger may emit literal newlines inside string fields.
        chunk = json.loads(chunk.replace("\n", "\\n"))
        rows.append(chunk)
    out = {}
    for r in rows:
        doc = r["doc"]
        key = str(r["doc_id"])
        gen = r["resps"][0][0]
        matches = re.findall(r"#### (-?[0-9.,]+)", gen)
        prediction = matches[0].strip() if matches else "[invalid]"
        gold = doc["answer"]
        out[key] = {
            "question": doc["question"],
            "answer": doc["answer"],
            "generated": gen,
            "prediction": prediction,
            "correct": bool(r["exact_match"]),
            "lm_eval_sample_correct": bool(r["exact_match"]),
            "generation_valid": bool(
                "Question:" not in gen
                and len(gen) < 4000
            ),
        }
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("bf16")
    ap.add_argument("e5m2")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    b, e = read(a.bf16), read(a.e5m2)
    assert len(b) == len(e) == 1319, (len(b), len(e))
    assert b.keys() == e.keys()
    assert all(
        (b[k]["question"], b[k]["answer"]) == (e[k]["question"], e[k]["answer"])
        for k in b
    )
    assert all(x["correct"] == x["lm_eval_sample_correct"] for x in b.values())
    assert all(x["correct"] == x["lm_eval_sample_correct"] for x in e.values())
    keys = list(b)
    both = sum(b[k]["correct"] and e[k]["correct"] for k in keys)
    neither = sum(not b[k]["correct"] and not e[k]["correct"] for k in keys)
    bo = sum(b[k]["correct"] and not e[k]["correct"] for k in keys)
    eo = sum(e[k]["correct"] and not b[k]["correct"] for k in keys)
    dif = [int(e[k]["correct"]) - int(b[k]["correct"]) for k in keys]
    rng = random.Random(20261026)
    means = []
    for _ in range(20000):
        means.append(sum(dif[rng.randrange(len(dif))] for _ in dif) / len(dif))
    means.sort()
    ci = [means[499], means[19499]]
    result = {
        "n": len(keys),
        "bf16_correct": sum(x["correct"] for x in b.values()),
        "e5m2_correct": sum(x["correct"] for x in e.values()),
        "both_correct": both,
        "both_wrong": neither,
        "bf16_only_correct": bo,
        "e5m2_only_correct": eo,
        "paired_accuracy_delta_e5m2_minus_bf16": (eo - bo) / len(keys),
        "bootstrap_replicates": 20000,
        "bootstrap_seed": 20261026,
        "paired_bootstrap_95_ci": ci,
        "samples": [
            {
                "doc_id": k,
                "question": b[k]["question"],
                "reference": b[k]["answer"].split("####")[-1].strip(),
                "bf16": b[k],
                "e5m2": e[k],
            }
            for k in keys
        ],
    }
    Path(a.out).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "samples"}, indent=2))


if __name__ == "__main__":
    main()
