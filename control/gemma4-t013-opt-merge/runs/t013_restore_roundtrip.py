#!/usr/bin/env python3
"""T013 L3 restore round trip: prime a fresh extent tier, then restore from it.

Phase ``prime`` (server 1, ``write_through``) sends one long greedy request and
records its ids. Phase ``restore`` (server 2, same extent directory, empty device
and host tiers) sends the identical request: the prefix must now come from the
extent tier, so the cached-token count and the storage-hit log lines are the
evidence, and the ids must still match.

Also sends four short greedy prompts in both phases so the two combinations can
be compared token-for-token.
"""

import json
import os
import sys
import time

import requests

FILLER = (
    "The cache hierarchy keeps a token sequence on the device, then in host DRAM, "
    "then in the durable extent tier. Restoring it must reproduce the same logits. "
)
FILLER_TOKENS = 62


def filler_text(target_tokens: int, suffix: str = "") -> str:
    return FILLER * max(1, target_tokens // FILLER_TOKENS) + suffix


def wait_health(port, timeout=900):
    session = requests.Session()
    session.trust_env = False
    base = f"http://127.0.0.1:{port}"
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if session.get(base + "/health", timeout=2).status_code == 200:
                return session, base
        except requests.RequestException:
            pass
        time.sleep(2)
    raise SystemExit("server did not become healthy")


def generate(session, base, text, max_new_tokens):
    payload = {
        "text": text,
        "sampling_params": {
            "temperature": 0.0,
            "max_new_tokens": max_new_tokens,
            "ignore_eos": True,
        },
    }
    response = session.post(base + "/generate", json=payload, timeout=1800)
    if response.status_code != 200:
        raise RuntimeError(
            f"generate failed {response.status_code}: {response.text[:300]}"
        )
    meta = response.json().get("meta_info", {})
    return {
        "output_ids": meta.get("output_ids"),
        "prompt_tokens": meta.get("prompt_tokens"),
        "cached_tokens": meta.get("cached_tokens"),
    }


def main():
    port, arm, phase, out_dir = (
        int(sys.argv[1]),
        sys.argv[2],
        sys.argv[3],
        sys.argv[4],
    )
    target = filler_text(int(os.environ.get("T013_TARGET_TOKENS", "20000")))
    session, base = wait_health(port)
    if phase == "prime":
        main_result = generate(session, base, target, 8)
        main_result["second_pass_cached"] = generate(session, base, target, 8)[
            "cached_tokens"
        ]
    else:
        main_result = generate(session, base, target, 8)
    short = {
        f"short-{index}": generate(session, base, filler_text(400 + 200 * index), 32)[
            "output_ids"
        ]
        for index in range(4)
    }
    log_path = os.environ.get("T013_SERVER_LOG")
    log = (
        open(log_path, errors="ignore").read()
        if log_path and os.path.exists(log_path)
        else ""
    )
    payload = {
        "arm": arm,
        "phase": phase,
        "main": main_result,
        "short_greedy": short,
        "log": {
            "storage_hit_1": len([l for l in log.splitlines() if "storage_hit=1" in l]),
            "restore_disposition": len(
                [l for l in log.splitlines() if "disposition=RESTORE" in l]
            ),
            "extent_read": log.count("extent_read"),
            "prefetch_revoke": log.count("prefetch_revoke"),
            "restore_recompute": log.count("restore_recompute"),
        },
    }
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, f"{phase}.json"), "w") as handle:
        json.dump(payload, handle, indent=2)
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
