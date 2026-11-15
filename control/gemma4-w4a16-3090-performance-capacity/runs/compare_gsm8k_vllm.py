#!/usr/bin/env python3
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
    p.add_argument("--add-bos", action="store_true")
    p.add_argument("--prefix-ids", default="")
    p.add_argument("--max-tokens", type=int, default=512)
    p.add_argument("--echo", action="store_true")
    p.add_argument("--resume", action="store_true")
    a = p.parse_args()
    rows = {
        int((r := json.loads(x))["doc_id"]): r
        for x in Path(a.samples).read_text().splitlines()
    }
    tok = AutoTokenizer.from_pretrained(a.model, trust_remote_code=True)
    out = Path(a.out)
    if a.resume and out.exists():
        saved = json.loads(out.read_text())
        assert saved["service"] == a.service
        result = saved["records"]
    else:
        result = []
    done = {int(r["doc_id"]) for r in result}
    forced = [int(x) for x in a.prefix_ids.split(",") if x]
    for doc_id in map(int, a.docs.split(",")):
        if doc_id in done:
            continue
        row = rows[doc_id]
        text = row["arguments"]["gen_args_0"]["arg_0"]
        ids = tok.encode(text, add_special_tokens=True)
        if a.add_bos:
            if tok.bos_token_id is None:
                raise RuntimeError("tokenizer has no BOS token")
            ids = [tok.bos_token_id, *ids]
        else:
            assert ids == row["audit"]["prompt_ids"], doc_id
        prompt_ids = [*ids, *forced]
        payload = {
            "prompt": prompt_ids,
            "model": "google/gemma-4-E4B-it-qat-w4a16-ct",
            "max_tokens": a.max_tokens,
            "temperature": 0.0,
            "top_p": 1.0,
            "seed": 666360643,
            "stop": ["Question:", "</s>", "<|im_end|>"],
            "return_token_ids": True,
            "logprobs": 20,
            "skip_special_tokens": False,
            "ignore_eos": False,
            "rid": f"g1-{a.service}-{doc_id}",
        }
        if a.service == "sglang":
            payload["no_stop_trim"] = False
        if a.echo:
            payload["echo"] = True
        response = requests.post(a.url, json=payload, timeout=a.timeout)
        response.raise_for_status()
        body = response.json()
        c = body["choices"][0]
        result.append(
            {
                "doc_id": doc_id,
                "prompt_ids": prompt_ids,
                "original_prompt_ids": ids,
                "forced_prefix_ids": forced,
                "prompt_sha256": digest(prompt_ids),
                "payload": payload,
                "request_id": body.get("id"),
                "text": c["text"],
                "token_ids": c.get("token_ids", []),
                "finish_reason": c["finish_reason"],
                "matched_stop": c.get("matched_stop"),
                "usage": body.get("usage"),
                "logprobs": c.get("logprobs"),
            }
        )
        result.sort(key=lambda x: int(x["doc_id"]))
        out.write_text(
            json.dumps({"service": a.service, "records": result}, indent=2) + "\n"
        )
        print(
            f"{doc_id}: {len(c.get('token_ids', []))} tokens; saved {len(result)}",
            flush=True,
        )
    out.write_text(
        json.dumps({"service": a.service, "records": result}, indent=2) + "\n"
    )


if __name__ == "__main__":
    main()
