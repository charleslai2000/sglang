#!/usr/bin/env python3
"""Replay frozen GSM8K token IDs against a local llama.cpp /completion server."""

import hashlib, json, re, time
from pathlib import Path
import requests

ROOT = Path("/data/sglang-hicache/g2-quasar-runs/20261107T-g2-cross-engine")
PROMPTS = ROOT / "prompts.jsonl"
OUT = ROOT / "llama-cpu-14x512.jsonl"
URL = "http://127.0.0.1:18888/completion"
STOP = ["Question:", "</s>", "<|im_end|>"]


def main():
    prompts = [json.loads(line) for line in PROMPTS.open()]
    assert len(prompts) == 14
    assert (
        hashlib.sha256(
            Path(
                "/data/models/gemma4-quasar-q4_0/gemma-4-E4B-it-QUASAR-Q4_0.gguf"
            ).read_bytes()
        ).hexdigest()
        == "7d6269096c9acbce4422fd1aa3a249436b01288868961e48ca9bb2541997f669"
    )
    with OUT.open("w") as out:
        for x in prompts:
            body = {
                "prompt": x["prompt_token_ids"],
                "n_predict": 512,
                "temperature": 0,
                "top_k": 1,
                "top_p": 1,
                "seed": 1234,
                "repeat_penalty": 1,
                "presence_penalty": 0,
                "frequency_penalty": 0,
                "dry_penalty_last_n": 0,
                "stop": STOP,
                "n_probs": 1,
                "cache_prompt": False,
            }
            started = time.time()
            r = requests.post(URL, json=body, timeout=3600)
            r.raise_for_status()
            j = r.json()
            # Persist the unmodified server response and explicit request for reproducibility.
            row = {
                "doc_id": x["doc_id"],
                "prompt_ids_sha256": x["prompt_ids_sha256"],
                "prompt_token_ids": x["prompt_token_ids"],
                "target": x["target"],
                "request": body,
                "response": j,
                "elapsed_s": time.time() - started,
            }
            out.write(json.dumps(row, ensure_ascii=False) + "\n")
            out.flush()
            print(
                x["doc_id"],
                j.get("stop"),
                j.get("tokens_predicted"),
                repr(j.get("content", "")[-120:]),
                flush=True,
            )
    print("sha256", hashlib.sha256(OUT.read_bytes()).hexdigest())


if __name__ == "__main__":
    main()
