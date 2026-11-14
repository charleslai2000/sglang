#!/usr/bin/env python3
"""Join request token/stop audit to lm-eval's concatenated JSON sample stream."""

import argparse
import json
from pathlib import Path


def read_records(path):
    text = Path(path).read_text()
    dec = json.JSONDecoder()
    rows, pos = [], 0
    while pos < len(text):
        while pos < len(text) and text[pos].isspace():
            pos += 1
        if pos == len(text):
            break
        row, pos = dec.raw_decode(text, pos)
        rows.append(row)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("samples")
    ap.add_argument("audit")
    args = ap.parse_args()
    path = Path(args.samples)
    samples = read_records(path)
    audits = {
        int(x["doc_id"]): x
        for x in map(json.loads, Path(args.audit).read_text().splitlines())
    }
    assert len(samples) == len(audits) == 1319
    assert {int(x["doc_id"]) for x in samples} == set(range(1319)) == set(audits)
    for sample in samples:
        x = audits[int(sample["doc_id"])]
        assert x["raw_completion"] == sample["resps"][0][0]
        sample["audit"] = {
            "request_id": x["request_id"],
            "prompt_ids": x["prompt_ids"],
            "prompt_sha256": x["prompt_sha256"],
            "finish_reason": x["finish_reason"],
            "matched_stop": x["matched_stop"],
            "prompt_tokens": x["prompt_tokens"],
            "completion_tokens": x["completion_tokens"],
            "output_ids": x["response_token_ids"],
        }
    path.write_text("".join(json.dumps(x, ensure_ascii=True, separators=(",", ":")) + "\n" for x in samples))
    print(f"joined {len(samples)} records")


if __name__ == "__main__":
    main()
