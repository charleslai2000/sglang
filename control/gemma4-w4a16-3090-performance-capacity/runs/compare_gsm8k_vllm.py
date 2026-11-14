#!/usr/bin/env python3
"""Run one backend on selected frozen GSM8K prompts and retain exact outputs."""

import argparse
import hashlib
import json
from pathlib import Path

import requests
from transformers import AutoTokenizer


def digest(ids):
    return hashlib.sha256(json.dumps(ids, separators=(",", ":")).encode()).hexdigest()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--samples", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--model", required=True)
    p.add_argument("--service", choices=("sglang", "vllm"), required=True)
    p.add_argument("--url", required=True)
    p.add_argument(
        "--docs", default="0,1,2,3,4,5,6,7,8,16,32,64,128,256,512,768,1024,1200,1318"
    )
    p.add_argument("--timeout", type=int, default=600)
    a = p.parse_args()
    rows = {
        int((r := json.loads(x))["doc_id"]): r
        for x in Path(a.samples).read_text().splitlines()
    }
    tok = AutoTokenizer.from_pretrained(a.model, trust_remote_code=True)
    result = []
    for doc_id in map(int, a.docs.split(",")):
        row = rows[doc_id]
        prompt = row["arguments"]["gen_args_0"]["arg_0"]
        ids = tok.encode(prompt, add_special_tokens=True)
        assert ids == row["audit"]["prompt_ids"], doc_id
        payload = {
            "prompt": ids,
            "model": "google/gemma-4-E4B-it-qat-w4a16-ct",
            "max_tokens": 512,
            "temperature": 0.0,
            "top_p": 1.0,
            "seed": 666360643,
            "stop": ["Question:", "</s>", "<|im_end|>"],
            "return_logprob": True,
            "return_token_ids": True,
            "skip_special_tokens": False,
            "ignore_eos": False,
            "no_stop_trim": False,
            "rid": f"g1-{a.service}-{doc_id}",
        }
        resp = requests.post(a.url, json=payload, timeout=a.timeout)
        resp.raise_for_status()
        body = resp.json()
        choice = body["choices"][0]
        rec = {
            "doc_id": doc_id,
            "prompt_ids": ids,
            "prompt_sha256": digest(ids),
            "payload": payload,
            "request_id": body.get("id"),
            "text": choice.get("text", ""),
            "token_ids": choice.get("token_ids", []),
            "finish_reason": choice.get("finish_reason"),
            "matched_stop": choice.get("matched_stop"),
            "usage": body.get("usage"),
            "logprobs": choice.get("logprobs"),
        }
        if a.service == "sglang":
            hist = row["audit"]["output_ids"]
            current = rec["token_ids"]
            rec["historical_sglang_token_ids"] = hist
            rec["first_historical_divergence"] = (
                next(
                    (i for i, (x, y) in enumerate(zip(hist, current)) if x != y),
                    min(len(hist), len(current)),
                )
                if hist != current
                else None
            )
        result.append(rec)
        print(f"{doc_id}: {len(rec['token_ids'])} tokens", flush=True)
    Path(a.out).write_text(
        json.dumps(
            {"service": a.service, "records": result}, ensure_ascii=True, indent=2
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
