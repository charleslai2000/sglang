#!/usr/bin/env python3
"""Score strict final GSM8K answers and paired CI from lm-eval sample files."""

import argparse, json, random, re
from pathlib import Path
from lm_eval.api.metrics import exact_match_hf_evaluate

START = re.compile(r'(?m)^\{"doc_id": \d+, "doc":')


def parse(path):
    text = Path(path).read_text()
    starts = [m.start() for m in START.finditer(text)]
    return [
        json.loads(
            text[p : starts[i + 1] if i + 1 < len(starts) else len(text)]
            .strip()
            .replace("\n", "\\n")
        )
        for i, p in enumerate(starts)
    ]


def answer(text):
    matches = list(re.finditer(r"#### (-?[0-9.,]+)", text))
    return matches[-1].group(1).strip() if matches else "[invalid]"


def correct(pred, target):
    return bool(
        exact_match_hf_evaluate(
            [pred],
            [target],
            regexes_to_ignore=[",", r"\$", r"(?s).*#### ", r"\.$"],
            ignore_case=True,
            ignore_punctuation=False,
        )["exact_match"]
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("bf16")
    ap.add_argument("e5m2")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    b, e = parse(a.bf16), parse(a.e5m2)
    assert len(b) == len(e) == 1319
    assert [(r["doc_id"], r["doc"]) for r in b] == [(r["doc_id"], r["doc"]) for r in e]
    sb = [correct(answer(r["resps"][0][0]), r["doc"]["answer"]) for r in b]
    se = [correct(answer(r["resps"][0][0]), r["doc"]["answer"]) for r in e]
    bo = sum(x and not y for x, y in zip(sb, se))
    eo = sum(y and not x for x, y in zip(sb, se))
    d = [int(y) - int(x) for x, y in zip(sb, se)]
    rng = random.Random(20261026)
    means = sorted(sum(d[rng.randrange(1319)] for _ in d) / 1319 for _ in range(20000))
    ci = [means[499], means[19499]]
    print(
        "N",
        len(d),
        "BF16",
        sum(sb),
        sum(sb) / 1319,
        "E5M2",
        sum(se),
        sum(se) / 1319,
        "both",
        sum(x and y for x, y in zip(sb, se)),
        "neither",
        sum(not x and not y for x, y in zip(sb, se)),
        "BF16-only",
        bo,
        "E5M2-only",
        eo,
        "delta",
        (eo - bo) / 1319,
        "paired percentile bootstrap 95% CI",
        ci,
    )
    result = {
        "n": 1319,
        "bf16_correct": sum(sb),
        "e5m2_correct": sum(se),
        "both_correct": sum(x and y for x, y in zip(sb, se)),
        "both_wrong": sum(not x and not y for x, y in zip(sb, se)),
        "bf16_only": bo,
        "e5m2_only": eo,
        "delta": (eo - bo) / 1319,
        "bootstrap_seed": 20261026,
        "bootstrap_replicates": 20000,
        "paired_95_ci": ci,
        "records": [
            {
                "doc_id": x["doc_id"],
                "question": x["doc"]["question"],
                "reference": answer(x["doc"]["answer"]),
                "bf16_generated": x["resps"][0][0],
                "e5m2_generated": y["resps"][0][0],
                "bf16_prediction": answer(x["resps"][0][0]),
                "e5m2_prediction": answer(y["resps"][0][0]),
                "bf16_correct": u,
                "e5m2_correct": v,
            }
            for x, y, u, v in zip(b, e, sb, se)
        ],
    }
    Path(a.out).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
