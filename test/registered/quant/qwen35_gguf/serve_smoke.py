"""Small, auditable serving gate; this is not a model-quality benchmark."""

import argparse
import json
import math
import time
from pathlib import Path

import requests


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8035")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    cases = [
        ("english", "What is the capital of France? Answer with the city name only.", "Paris"),
        ("chinese", "中国的首都是哪里？只输出城市名。", "北京"),
        ("arithmetic", "计算 17 * 23，只输出整数结果。", "391"),
        ("python", "What does Python print for sum(i*i for i in range(5))? Output only the integer.", "30"),
        ("json", '只输出合法 JSON，包含键 "ok" 值 true，键 "count" 值 3。', None),
    ]
    records = []
    for label, prompt, expected in cases:
        start = time.perf_counter()
        response = requests.post(
            args.url + "/v1/chat/completions",
            json={
                "model": "qwen3.8-27b-iq3s",
                "messages": [{"role": "user", "content": prompt}],
                "chat_template_kwargs": {"enable_thinking": False},
                "temperature": 0,
                "max_tokens": 128,
                "logprobs": True,
                "top_logprobs": 3,
            },
            timeout=600,
        )
        response.raise_for_status()
        body = response.json()
        choice = body["choices"][0]
        content = choice["message"]["content"]
        probabilities = choice["logprobs"]["content"]
        finite = bool(probabilities) and all(
            math.isfinite(token["logprob"])
            and all(math.isfinite(p["logprob"]) for p in token["top_logprobs"])
            for token in probabilities
        )
        if label == "json":
            try:
                correct = json.loads(content) == {"ok": True, "count": 3}
            except (ValueError, TypeError):
                correct = False
        else:
            correct = expected in content
        record = {
            "case": label, "prompt": prompt, "response": body,
            "elapsed_s": time.perf_counter() - start,
            "finite_returned_logprobs": finite, "correct": correct,
        }
        records.append(record)
        args.output.write_text(json.dumps(records, ensure_ascii=False, indent=2))
        print(json.dumps({k: v for k, v in record.items() if k != "response"}, ensure_ascii=False), flush=True)
        print(content, flush=True)
    assert all(r["finite_returned_logprobs"] and r["correct"] for r in records)
    print("Serving smoke PASS", flush=True)


if __name__ == "__main__":
    main()
