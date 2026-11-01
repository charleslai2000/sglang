#!/usr/bin/env python3
"""Issue unique, uncached single-request Prefill sizes against local service."""

import json, os, pathlib, time, urllib.request

out = pathlib.Path(os.environ["RADIX8K_OUT"])
fixture = json.load(open(out / "fixture.json"))
source = fixture["prompts"]["c16-r0-i0"]
rows = []
for n in (1024, 4096, 8192):
    rid = f"radix8k-perf-g1-prefill-n{n}-{os.getpid()}"
    body = {
        "rid": rid,
        "input_ids": [source[:n]],
        "sampling_params": {
            "temperature": 0,
            "top_p": 1,
            "max_new_tokens": 1,
            "min_new_tokens": 1,
            "ignore_eos": True,
        },
        "return_token_ids": True,
    }
    req = urllib.request.Request(
        "http://127.0.0.1:31371/generate",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    start = time.perf_counter()
    obj = json.load(urllib.request.urlopen(req, timeout=900))
    obj = obj[0] if isinstance(obj, list) and len(obj) == 1 else obj
    wall = time.perf_counter() - start
    if not isinstance(obj, dict):
        raise TypeError(f"unexpected response type: {type(obj)}")
    meta = obj.get("meta_info", {})
    row = {
        "rid": rid,
        "tokens": n,
        "wall_s": wall,
        "output_tokens": len(obj.get("output_ids", [])),
        "meta": meta,
    }
    rows.append(row)
    if (
        meta.get("prompt_tokens") != n
        or meta.get("cached_tokens", 0) != 0
        or row["output_tokens"] != 1
    ):
        raise RuntimeError(f"validation failed: {row}")
    print(json.dumps(row), flush=True)
(out / "prefill-sizes.json").write_text(json.dumps(rows, indent=2) + "\n")
