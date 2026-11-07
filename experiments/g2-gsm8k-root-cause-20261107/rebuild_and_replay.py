#!/usr/bin/env python3
"""Rebuild exact five-shot GSM8K inputs and replay a bounded failure sample.

The run inputs are pinned by hashes in report.md. Runtime output is saved verbatim.
"""

import hashlib, json, random, re, subprocess, time
from pathlib import Path
import requests
from transformers import AutoTokenizer

TRAIN_PARQUET = Path("/tmp/gsm8k-train.parquet")
TEST_JSONL = Path("/tmp/gsm8k-test.jsonl")
TOKENIZER = Path("/data/sglang-hicache/gemma4/model")
PROMPT_OUT = Path("/tmp/g2-rebuilt-fewshot-14.jsonl")
RESULT_OUT = Path("/tmp/g2-gsm8k-controlled-14.jsonl")
IDS = [0, 1, 2, 3, 5, 6, 8, 18, 20, 24, 36, 39, 47, 70]
STOP = ["Question:", "</s>", "<|im_end|>"]


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def rebuild():
    from pyarrow import parquet

    assert (
        sha256(TRAIN_PARQUET)
        == "ea82612ea9582142387730c793eb67d3b12849002bc0b7fa6f8efafa7351419d"
    )
    train = parquet.read_table(TRAIN_PARQUET).to_pylist()
    train_bytes = "".join(
        json.dumps(x, ensure_ascii=False, separators=(", ", ": ")) + "\n" for x in train
    ).encode()
    assert (
        hashlib.sha256(train_bytes).hexdigest()
        == "6043ef64147b59871f4fd3adf669c306fe0a4c27e5a5c4bfb761f3f084895a13"
    )
    assert (
        sha256(TEST_JSONL)
        == "3730d312f6e3440559ace48831e51066acaca737f6eabec99bccb9e4b3c39d14"
    )
    test = [json.loads(x) for x in TEST_JSONL.read_text().splitlines() if x]
    assert len(train) == 7473 and len(test) == 1319
    rng = random.Random(1234)  # lm-eval 0.4.13 DEFAULT_SEED[3]
    tok = AutoTokenizer.from_pretrained(TOKENIZER, trust_remote_code=True)
    rows = []
    for i, doc in enumerate(test):
        shots = rng.sample(train, 5)  # same shared RNG and test-doc traversal order
        prompt = "".join(
            f"Question: {s['question']}\nAnswer: {s['answer']}\n\n" for s in shots
        )
        prompt += f"Question: {doc['question']}\nAnswer:"
        ids = [tok.bos_token_id] + tok.encode(prompt, add_special_tokens=False)
        if i in IDS:
            rows.append(
                {
                    "doc_id": i,
                    "fewshot_train_indices": [train.index(s) for s in shots],
                    "prompt": prompt,
                    "prompt_token_ids": ids,
                    "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
                    "prompt_ids_sha256": hashlib.sha256(
                        json.dumps(ids, separators=(",", ":")).encode()
                    ).hexdigest(),
                    "target": doc["answer"],
                }
            )
    PROMPT_OUT.write_text(
        "".join(json.dumps(x, ensure_ascii=False) + "\n" for x in rows)
    )
    return rows


def replay(rows, cap, base_url="http://127.0.0.1:31221"):
    with RESULT_OUT.open("a") as f:
        for x in rows:
            body = {
                "model": "gemma-4-E4B-it-QUASAR-Q4_0.gguf",
                "prompt": x["prompt_token_ids"],
                "temperature": 0,
                "top_p": 1,
                "top_k": 1,
                "seed": 1234,
                "max_tokens": cap,
                "stop": STOP,
                "return_token_ids": True,
                "stream": False,
                "rid": f"g2-controlled-{x['doc_id']}-cap{cap}",
            }
            started = time.time()
            r = requests.post(
                base_url.rstrip("/") + "/v1/completions", json=body, timeout=3600
            )
            r.raise_for_status()
            choice = r.json()["choices"][0]
            echo = choice.get("prompt_token_ids") or []
            assert echo == x["prompt_token_ids"]
            text = choice.get("text") or ""
            m = re.findall(r"####\s+(-?[0-9.,]+)", text)
            gold = re.findall(r"#### (-?[0-9.,]+)", x["target"])
            pred, ref = (
                (m[0] if m else "[invalid]"),
                (gold[-1] if gold else "[invalid]"),
            )
            norm = lambda s: s.replace(",", "").replace("$", "")
            correct = norm(pred).lower() == norm(ref).lower() or (
                norm(pred).endswith(".")
                and norm(pred)[:-1].lower() == norm(ref).lower()
            )
            row = {
                "doc_id": x["doc_id"],
                "max_tokens": cap,
                "prompt": x["prompt"],
                "prompt_sha256": x["prompt_sha256"],
                "prompt_ids_sha256": x["prompt_ids_sha256"],
                "fewshot_train_indices": x["fewshot_train_indices"],
                "prompt_echo_match": True,
                "target": x["target"],
                "text": text,
                "output_ids": choice.get("token_ids") or [],
                "finish_reason": choice.get("finish_reason"),
                "matched_stop": choice.get("matched_stop"),
                "prediction": pred,
                "reference": ref,
                "correct": correct,
                "answer_marker_count": len(m),
                "elapsed_s": time.time() - started,
            }
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            f.flush()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--rebuild", action="store_true")
    parser.add_argument("--replay", action="store_true")
    parser.add_argument("--base-url", default="http://127.0.0.1:31221")
    parser.add_argument("--caps", type=int, nargs="+", default=[512, 2048])
    args = parser.parse_args()
    if not args.rebuild and not args.replay:
        parser.error("select --rebuild and/or --replay")
    subset = (
        rebuild()
        if args.rebuild
        else [json.loads(x) for x in PROMPT_OUT.open()]
    )
    if args.replay:
        # Caller must start the documented G2 BF16 service under the project GPU lock.
        for cap in args.caps:
            replay(subset, cap, args.base_url)
