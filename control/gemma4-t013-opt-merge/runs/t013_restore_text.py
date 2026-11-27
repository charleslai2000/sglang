#!/usr/bin/env python3
"""T013: greedy completions on a prefix that came back from the extent tier."""

import json
import os
import sys
import time

import requests

FILLER = (
    "The cache hierarchy keeps a token sequence on the device, then in host DRAM, "
    "then in the durable extent tier. Restoring it must reproduce the same logits. "
)


def filler_text(target_tokens: int, suffix: str = "") -> str:
    return FILLER * max(1, target_tokens // 32) + suffix


def main():
    port, arm, out_dir = int(sys.argv[1]), sys.argv[2], sys.argv[3]
    session = requests.Session()
    session.trust_env = False
    base = f"http://127.0.0.1:{port}"
    for _ in range(900):
        try:
            if session.get(base + "/health", timeout=2).status_code == 200:
                break
        except requests.RequestException:
            pass
        time.sleep(2)
    else:
        raise SystemExit("unhealthy")

    def run(text, max_new_tokens):
        body = {
            "text": text,
            "sampling_params": {
                "temperature": 0.0,
                "max_new_tokens": max_new_tokens,
                "ignore_eos": True,
            },
        }
        response = session.post(base + "/generate", json=body, timeout=1800)
        if response.status_code != 200:
            raise RuntimeError(f"{response.status_code}: {response.text[:200]}")
        body = response.json()
        meta = body.get("meta_info", {})
        return {
            "text": body.get("text"),
            "prompt_tokens": meta.get("prompt_tokens"),
            "cached_tokens": meta.get("cached_tokens"),
            "output_ids": meta.get("output_ids"),
        }

    target = filler_text(20000)
    result = {
        "arm": arm,
        "target": run(target, 8),
        "short": {
            f"short-{i}": run(filler_text(400 + 200 * i), 32) for i in range(4)
        },
    }
    log_path = os.environ.get("T013_SERVER_LOG")
    log = open(log_path, errors="ignore").read() if log_path and os.path.exists(log_path) else ""
    result["log"] = {
        "restore_full": log.count("disposition=RESTORE requested=") ,
        "restore_disposition": log.count("disposition=RESTORE"),
        "extent_read": log.count("extent_read"),
    }
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, f"{arm}-text.json"), "w") as handle:
        json.dump(result, handle, indent=2)
    print(json.dumps(result, indent=2)[:1200])


if __name__ == "__main__":
    main()
