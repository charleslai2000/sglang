#!/usr/bin/env python3
"""Join exact SGLang and llama.cpp token traces and classify bounded outcomes."""

import hashlib
import json
import re
from pathlib import Path

ROOT = Path("/data/sglang-hicache/g2-quasar-runs/20261107T-g2-cross-engine")
SG_PATH = ROOT / "sglang-bf16-14x512-2048.jsonl"
LLAMA_PATH = ROOT / "llama-cpu-14x512.jsonl"
OUT = ROOT / "comparison.jsonl"


def answer(text):
    m = re.findall(r"####\s*(-?[0-9.,]+)", text)
    return m[0] if m else "[invalid]"


def norm(value):
    return value.replace(",", "").replace("$", "").rstrip(".")


def repeated(text):
    # Detect a substantial exact repeated span; limit search to avoid quadratic work.
    for size in (40, 80, 160, 320):
        if size * 3 > len(text):
            continue
        for i in range(min(len(text) - size * 2, 1000)):
            chunk = text[i : i + size]
            if text.find(chunk, i + size, min(len(text), i + size * 8)) >= 0:
                return True
    return False


def main():
    sg = {}
    for line in SG_PATH.open():
        x = json.loads(line)
        if x["max_tokens"] == 512:
            sg[x["doc_id"]] = x
    llama = {x["doc_id"]: x for x in map(json.loads, LLAMA_PATH.open())}
    assert set(sg) == set(llama) and len(sg) == 14
    rows = []
    for doc_id, a in sg.items():
        b = llama[doc_id]
        la = b["response"]
        sg_text, ll_text = a["text"], la["content"]
        sg_ids = a["output_ids"]
        ll_ids = [item["id"] for item in la.get("completion_probabilities", [])]
        first_diff = next(
            (i for i, (x, y) in enumerate(zip(sg_ids, ll_ids)) if x != y),
            min(len(sg_ids), len(ll_ids)),
        )
        sg_ans, ll_ans = answer(sg_text), answer(ll_text)
        rows.append(
            {
                "doc_id": doc_id,
                "gold": a["reference"],
                "sg_answer": sg_ans,
                "llama_answer": ll_ans,
                "sg_correct": norm(sg_ans) == norm(a["reference"]),
                "llama_correct": norm(ll_ans) == norm(a["reference"]),
                "same_final_answer": norm(sg_ans) == norm(ll_ans),
                "sg_finish": a["finish_reason"],
                "llama_stop": la.get("stopping_word")
                if la.get("stop_type") == "word"
                else la.get("stop_type"),
                "sg_repetition_detected": repeated(sg_text),
                "llama_repetition_detected": repeated(ll_text),
                "sg_output_tokens": len(sg_ids),
                "llama_output_tokens": la.get("tokens_predicted"),
                "first_generated_id_divergence": first_diff,
                "sg_token_at_divergence": sg_ids[first_diff]
                if first_diff < len(sg_ids)
                else None,
                "llama_token_at_divergence": ll_ids[first_diff]
                if first_diff < len(ll_ids)
                else None,
                "sg_prefix": sg_text[:160],
                "llama_prefix": ll_text[:160],
            }
        )
    OUT.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in rows))
    print(
        "doc gold SGLang llama correct(S/L) same stop(S/L) repeat(S/L) tokens(S/L) first_div"
    )
    for x in rows:
        print(
            x["doc_id"],
            x["gold"],
            x["sg_answer"],
            x["llama_answer"],
            f"{x['sg_correct']}/{x['llama_correct']}",
            x["sg_finish"],
            x["llama_stop"],
            f"{x['sg_repetition_detected']}/{x['llama_repetition_detected']}",
            f"{x['sg_output_tokens']}/{x['llama_output_tokens']}",
            x["first_generated_id_divergence"],
        )
    print(
        "scores",
        sum(x["sg_correct"] for x in rows),
        sum(x["llama_correct"] for x in rows),
        "same answers",
        sum(x["same_final_answer"] for x in rows),
        "repetition",
        sum(x["sg_repetition_detected"] for x in rows),
        sum(x["llama_repetition_detected"] for x in rows),
    )
    print("sha256", hashlib.sha256(OUT.read_bytes()).hexdigest())


if __name__ == "__main__":
    main()
