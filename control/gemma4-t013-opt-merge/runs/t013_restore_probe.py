#!/usr/bin/env python3
"""T013 real L3 restore probe.

For one served combination:

1. cold greedy request of a fixed long prompt (records ids and cached tokens);
2. pressure requests to push that prompt's KV out of the device and host tiers;
3. ``/flush_cache`` so the next request must come back from the extent tier;
4. the identical request again — record the restored token count, the extent
   read activity and whether the greedy ids still match the cold run.

Only the server under test is touched; the numbers land in ``<out>/<arm>.json``.
"""

import json
import os
import sys
import threading
import time

import requests

FILLER = (
    "The cache hierarchy keeps a token sequence on the device, then in host DRAM, "
    "then in the durable extent tier. Restoring it must reproduce the same logits. "
)
#: Empirical token count of one FILLER repeat with this tokenizer (~62).
FILLER_TOKENS = 62


def filler_text(target_tokens: int, suffix: str = "") -> str:
    reps = max(1, target_tokens // FILLER_TOKENS)
    return FILLER * reps + suffix


def client(port):
    session = requests.Session()
    session.trust_env = False
    return session, f"http://127.0.0.1:{port}"


def wait_health(port, timeout=900):
    session, base = client(port)
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if session.get(base + "/health", timeout=2).status_code == 200:
                return session, base
        except requests.RequestException:
            pass
        time.sleep(2)
    raise SystemExit("server did not become healthy")


def generate(session, base, text, max_new_tokens, timeout=1200):
    payload = {
        "text": text,
        "sampling_params": {
            "temperature": 0.0,
            "max_new_tokens": max_new_tokens,
            "ignore_eos": True,
        },
    }
    response = session.post(base + "/generate", json=payload, timeout=timeout)
    if response.status_code != 200:
        raise RuntimeError(f"generate failed {response.status_code}: {response.text[:300]}")
    body = response.json()
    meta = body.get("meta_info", {})
    return {
        "output_ids": meta.get("output_ids"),
        "prompt_tokens": meta.get("prompt_tokens"),
        "completion_tokens": meta.get("completion_tokens"),
        "cached_tokens": meta.get("cached_tokens"),
        "text_head": body.get("text", "")[:40],
    }


def extent_lines(port):
    path = os.environ.get("T013_SERVER_LOG")
    if not path or not os.path.exists(path):
        return None
    text = open(path, errors="ignore").read()
    return {
        "extent_read": text.count("extent_read"),
        "extent_hit": text.count("storage_hit") + text.count("disposition=RESTORE"),
        "restore_disposition": text.count("disposition=RESTORE"),
    }


def main():
    port = int(sys.argv[1])
    out_dir = sys.argv[2]
    arm = sys.argv[3]
    target_tokens = int(os.environ.get("T013_TARGET_TOKENS", "20000"))
    pressure = int(os.environ.get("T013_PRESSURE", "16"))

    session, base = wait_health(port)
    target = filler_text(target_tokens)

    before = extent_lines(port)
    cold = generate(session, base, target, 8)
    warm = generate(session, base, target, 8)

    def press(index):
        body = (
            FILLER * (target_tokens * 4 // len(FILLER.split()) + 40)
            + f"\npressure {index}"
        )
        try:
            generate(session, base, body, 1)
        except Exception as error:  # pressure failures are recorded, not fatal
            return f"{type(error).__name__}: {error}"
        return None

    threads = [threading.Thread(target=press, args=(i,)) for i in range(pressure)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    flush = session.post(base + "/flush_cache", json={}, timeout=120)
    flush.raise_for_status()
    try:
        flush_body = flush.json()
    except ValueError:
        flush_body = {"status_code": flush.status_code, "body": flush.text[:200]}
    time.sleep(2)
    after_flush = extent_lines(port)
    restored = generate(session, base, target, 8)
    after = extent_lines(port)

    short = {}
    for index in range(4):
        text = filler_text(400 + 200 * index)
        short[f"short-{index}"] = generate(session, base, text, 32)["output_ids"]

    result = {
        "arm": arm,
        "short_greedy": short,
        "cold": cold,
        "warm": warm,
        "restored": restored,
        "flush": flush_body,
        "extent": {"before": before, "after_flush": after_flush, "after": after},
        "pressure_requests": pressure,
        "ids_match_cold": cold.get("output_ids") == restored.get("output_ids"),
        "ids_match_warm": warm.get("output_ids") == restored.get("output_ids"),
        "restored_tokens": (restored.get("cached_tokens") or 0),
        "warm_cached_tokens": (warm.get("cached_tokens") or 0),
    }
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, f"{arm}.json"), "w") as handle:
        json.dump(result, handle, indent=2)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
