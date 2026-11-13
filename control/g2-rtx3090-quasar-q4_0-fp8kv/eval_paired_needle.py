#!/usr/bin/env python3
"""Exact-length single-needle retrieval probe using GGUF tokenizer IDs."""

import argparse, hashlib, json
from pathlib import Path
import requests

SECRET = "NIMBUS-4827-ORCHID-7316"


def make_prompt(tok, target):
    head = "The following archive contains notes about a small town and its public records."
    note = "Archive note: residents recorded ordinary details about weather gardening travel and community events."
    tail = f"\nAt the winter archive desk, the unique retrieval code is {SECRET}.\nQuestion: What is the archive retrieval code? Answer:"
    ids = [tok.bos_token_id] + tok.encode(
        head + "\n" + note + "\n", add_special_tokens=False
    )
    tail_ids = tok.encode(tail, add_special_tokens=False)
    room = target - len(ids) - len(tail_ids)
    if room < 0:
        raise ValueError("needle framing exceeds target")
    filler = tok.encode(
        " Community records listed ordinary public notices about weather, gardens, local markets, transport, and resident activities.",
        add_special_tokens=False,
    )
    if not filler:
        raise ValueError("empty filler token sequence")
    body = (filler * (room // len(filler) + 1))[:room]
    prompt_ids = ids + body + tail_ids
    assert len(prompt_ids) == target
    return prompt_ids, tok.decode(prompt_ids, skip_special_tokens=False)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--base-url", required=True)
    p.add_argument("--arm", choices=["bf16", "e5m2"], required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--target-tokens", type=int, choices=[16384, 32768], required=True)
    a = p.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    from sglang.srt.utils.hf_transformers.gguf_native import build_gguf_tokenizer

    tok = build_gguf_tokenizer(
        "/data/models/gemma4-quasar-q4_0/gemma-4-E4B-it-QUASAR-Q4_0.gguf"
    )
    ids, decoded = make_prompt(tok, a.target_tokens)
    req = {
        "model": "gemma-4-E4B-it-QUASAR-Q4_0.gguf",
        "prompt": ids,
        "temperature": 0,
        "top_p": 1,
        "top_k": 1,
        "seed": 1234,
        "max_tokens": 24,
        "stop": ["Question:", "</s>", "<|im_end|>"],
        "return_token_ids": True,
        "stream": False,
        "rid": f"{a.arm}-needle-{a.target_tokens}",
    }
    r = requests.post(
        a.base_url.rstrip("/") + "/v1/completions", json=req, timeout=1800
    )
    if not r.ok:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text}")
    body = r.json()
    c = body["choices"][0]
    echo = c.get("prompt_token_ids") or []
    answer = c.get("text") or ""
    assert echo == ids and len(echo) == a.target_tokens, (len(echo), len(ids))
    result = {
        "arm": a.arm,
        "target_prompt_tokens": a.target_tokens,
        "actual_prompt_tokens": len(echo),
        "prompt_token_ids": ids,
        "prompt_token_ids_sha256": hashlib.sha256(
            json.dumps(ids, separators=(",", ":")).encode()
        ).hexdigest(),
        "decoded_prompt": decoded,
        "needle": SECRET,
        "answer": answer,
        "correct": SECRET in answer,
        "output_ids": c.get("token_ids") or [],
        "finish_reason": c.get("finish_reason"),
        "matched_stop": c.get("matched_stop"),
        "request_id": body.get("id"),
        "prompt_echo_exact_ids": echo == ids,
        "request_config": req,
    }
    (out / f"needle-{a.target_tokens}.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    )
    print(
        json.dumps(
            {
                k: v
                for k, v in result.items()
                if k not in ("prompt_token_ids", "decoded_prompt", "request_config")
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
