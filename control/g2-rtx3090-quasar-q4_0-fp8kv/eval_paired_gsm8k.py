#!/usr/bin/env python3
"""Run pinned G1 GSM8K prompts against one live SGLang arm."""

import argparse, hashlib, json, re, time, subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import requests

RUNS = Path("/data/sglang-hicache/gemma4/runs")
G1 = RUNS / "20261026T-gsm8k-g1-final-bos"
DATA = RUNS / "gsm8k-prepare-20261026/data"
TOKENIZER = Path("/data/sglang-hicache/gemma4/model")
MODEL = Path("/data/models/gemma4-quasar-q4_0/gemma-4-E4B-it-QUASAR-Q4_0.gguf")
STOP = ["Question:", "</s>", "<|im_end|>"]
SEED = 1234
START = re.compile(r'(?m)^\{"doc_id": \d+, "doc":')


def parse_samples(path):
    s = Path(path).read_text()
    m = list(START.finditer(s))
    out = {}
    for i, x in enumerate(m):
        r = json.loads(
            s[x.start() : m[i + 1].start() if i + 1 < len(m) else len(s)]
            .strip()
            .replace("\n", "\\n")
        )
        out[int(r["doc_id"])] = r
    return out


def score(text, target):
    m = re.findall(r"####\s+(-?[0-9.,]+)", text)
    g = re.findall(r"#### (-?[0-9.,]+)", target)
    pred = m[0] if m else "[invalid]"
    gold = g[-1] if g else "[invalid]"
    p = pred.replace(",", "").replace("$", "")
    q = gold.replace(",", "").replace("$", "")
    return {
        "prediction": pred,
        "reference": gold,
        "correct": bool(
            p.lower() == q.lower() or (p.endswith(".") and p[:-1].lower() == q.lower())
        ),
        "has_answer_marker": bool(m),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--arm", choices=["bf16", "e5m2"], required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--timeout", type=int, default=1800)
    a = ap.parse_args()
    dst = Path(a.out)
    dst.mkdir(parents=True, exist_ok=True)
    samples = parse_samples(G1 / "bf16/samples.jsonl")
    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(TOKENIZER, trust_remote_code=True)
    test = (DATA / "test.jsonl").read_bytes()
    ds = hashlib.sha256(test).hexdigest()
    assert ds == "752adc99f23132275139f1f7be57126b08735a55daf0c56859ee6df70abafbac"
    docs = [json.loads(x) for x in test.splitlines() if x.strip()]
    assert len(samples) == len(docs) == 1319 and all(
        samples[i]["doc"] == d for i, d in enumerate(docs)
    )
    subprocess.run(
        ["sha256sum", str(MODEL)], stdout=(dst / "model.sha256").open("w"), check=True
    )
    fixture = []
    for i in range(1319):
        r = samples[i]
        prompt = r["arguments"]["gen_args_0"]["arg_0"]
        ids = [tokenizer.bos_token_id] + tokenizer.encode(prompt, add_special_tokens=False)
        assert ids[0] == 2, (i, ids[:4])
        fixture.append(
            {
                "doc_id": i,
                "prompt": prompt,
                "prompt_token_ids": ids,
                "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
                "prompt_ids_sha256": hashlib.sha256(
                    json.dumps(ids, separators=(",", ":")).encode()
                ).hexdigest(),
                "target": r["doc"]["answer"],
            }
        )
    (dst / "fixture.jsonl").write_text(
        "".join(json.dumps(x, ensure_ascii=False) + "\n" for x in fixture)
    )

    def call(item):
        payload = {
            "model": "gemma-4-E4B-it-QUASAR-Q4_0.gguf",
            "prompt": item["prompt_token_ids"],
            "temperature": 0,
            "top_p": 1,
            "top_k": 1,
            "seed": SEED,
            "max_tokens": 512,
            "stop": STOP,
            "return_token_ids": True,
            "stream": False,
            "rid": f"{a.arm}-gsm8k-{item['doc_id']}",
        }
        r = requests.post(
            a.base_url.rstrip("/") + "/v1/completions", json=payload, timeout=a.timeout
        )
        r.raise_for_status()
        body = r.json()
        return item, body, body["choices"][0], payload

    start = time.time()
    done = {}
    with ThreadPoolExecutor(max_workers=a.workers) as pool:
        futures = {pool.submit(call, x): x for x in fixture}
        for fut in as_completed(futures):
            item, body, c, payload = fut.result()
            done[item["doc_id"]] = (item, body, c, payload)
            if len(done) % 100 == 0:
                print(f"completed {len(done)}/1319", flush=True)
    rows = []
    with (dst / "results.jsonl").open("w") as f:
        for i in range(1319):
            item, body, c, payload = done[i]
            text = c.get("text") or ""
            echo = c.get("prompt_token_ids") or []
            row = {
                "doc_id": i,
                "prompt": item["prompt"],
                "prompt_token_ids": item["prompt_token_ids"],
                "prompt_echo_token_ids": echo,
                "prompt_echo_match": echo == item["prompt_token_ids"],
                "prompt_sha256": item["prompt_sha256"],
                "prompt_ids_sha256": item["prompt_ids_sha256"],
                "target": item["target"],
                "answer": text,
                "output_token_ids": c.get("token_ids") or [],
                "finish_reason": c.get("finish_reason"),
                "matched_stop": c.get("matched_stop"),
                "request_id": body.get("id"),
                "request_seed": SEED,
                "score": score(text, item["target"]),
            }
            rows.append(row)
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            f.flush()
    correct = sum(x["score"]["correct"] for x in rows)
    summary = {
        "arm": a.arm,
        "n": len(rows),
        "correct": correct,
        "accuracy": correct / len(rows),
        "answer_marker_whitespace_policy": r"####\s+(-?[0-9.,]+)",
        "elapsed_seconds": time.time() - start,
        "stop": STOP,
        "temperature": 0,
        "top_p": 1,
        "top_k": 1,
        "per_request_seed": SEED,
        "max_tokens": 512,
        "workers": a.workers,
        "dataset_sha256": ds,
        "fixture_sha256": hashlib.sha256(
            (dst / "fixture.jsonl").read_bytes()
        ).hexdigest(),
        "results_sha256": hashlib.sha256(
            (dst / "results.jsonl").read_bytes()
        ).hexdigest(),
        "prompt_echo_all_match": all(x["prompt_echo_match"] for x in rows),
        "finish_reasons": {
            k: sum(r["finish_reason"] == k for r in rows)
            for k in sorted({str(r["finish_reason"]) for r in rows})
        },
    }
    (dst / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
