#!/usr/bin/env python3
"""Reusable E5M2-only real-service load/caching driver for G1-PROD."""

import argparse, concurrent.futures, json, random, statistics, threading, time, urllib.request
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument("--url", required=True)
p.add_argument("--fixture", required=True)
p.add_argument("--out", required=True)
p.add_argument("--concurrency", type=int, required=True)
p.add_argument("--rounds", type=int, default=1)
p.add_argument("--new-tokens", type=int, default=128)
p.add_argument("--prefix-len", type=int, default=0)
p.add_argument("--mode", default="distinct")
p.add_argument("--prompt-len", type=int, default=64)
p.add_argument("--stream", action="store_true")
a = p.parse_args()
f = json.loads(Path(a.fixture).read_text())
prefix = f["prefix_ids"]
suffix_obj = f.get("suffixes") or []
prompt_obj = f.get("prompts") or []
suffix = list(suffix_obj.values()) if isinstance(suffix_obj, dict) else suffix_obj
ids_pool = list(prompt_obj.values()) if isinstance(prompt_obj, dict) else prompt_obj
rng = random.Random(2026111505)
rows = []
gate = threading.Event()
lock = threading.Lock()


def run(i, rnd):
    if a.mode == "shared-prefix":
        ids = prefix + suffix[i % len(suffix)] if suffix else ids_pool[i % len(ids_pool)]
    elif a.mode == "partial-hit":
        ids = prefix[: a.prefix_len] + (
            suffix[i % len(suffix)]
            if suffix
            else [rng.randrange(3, 262143) for _ in range(max(0, a.prompt_len - a.prefix_len))]
        )
    elif a.mode == "repeat":
        ids = ids_pool[i % len(ids_pool)] if ids_pool else prefix
    elif a.mode == "distinct":
        ids = (
            ids_pool[(rnd * a.concurrency + i) % len(ids_pool)]
            if ids_pool
            else [
                rng.randrange(3, 262143)
                for _ in range(a.prompt_len)
            ]
        )
    else:
        raise ValueError(a.mode)
    tag = f"g1p-{a.mode}-c{a.concurrency}-r{rnd}-i{i}"
    body = {
        "rid": tag,
        "input_ids": [ids],
        "sampling_params": {
            "temperature": 0,
            "top_p": 1,
            "max_new_tokens": a.new_tokens,
            "min_new_tokens": a.new_tokens,
            "ignore_eos": True,
        },
        "return_token_ids": True,
    }
    gate.wait()
    start = time.perf_counter()
    if a.stream:
        body["stream"] = True
    req = urllib.request.Request(
        a.url + ("/v1/completions" if a.stream else "/generate"),
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        response = urllib.request.urlopen(req, timeout=3600)
        first_token_s = None
        if a.stream:
            chunks = []
            for raw in response:
                if raw.startswith(b"data: ") and raw.strip() != b"data: [DONE]":
                    event = json.loads(raw[6:])
                    if first_token_s is None and event.get("choices"):
                        first_token_s = time.perf_counter() - start
                    chunks.append(event)
            final = chunks[-1] if chunks else {}
            out = [token for event in chunks for token in (event.get("choices", [{}])[0].get("token_ids") or [])]
            m = final.get("meta_info", {})
        else:
            x = json.loads(response.read())
            x = x[0] if isinstance(x, list) and len(x) == 1 else x
            m = x.get("meta_info", {})
            out = x.get("output_ids", m.get("output_token_ids", []))
        row = {
            "rid": m.get("id", tag),
            "ok": len(out) >= a.new_tokens
            and int(m.get("completion_tokens", len(out))) >= a.new_tokens,
            "elapsed_s": time.perf_counter() - start,
            "input_len": len(ids),
            "ttft_s": first_token_s,
            "output_len": len(out),
            "output_ids": out,
            "meta": m,
        }
    except Exception as e:
        row = {
            "rid": tag,
            "ok": False,
            "elapsed_s": time.perf_counter() - start,
            "input_len": len(ids),
            "output_len": 0,
            "error": repr(e),
        }
    with lock:
        rows.append(row)


for rnd in range(a.rounds):
    rows = []
    gate.clear()
    t = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=a.concurrency) as ex:
        futures = [ex.submit(run, i, rnd) for i in range(a.concurrency)]
        gate.set()
        batch = [q.result() for q in futures]
    wall = time.perf_counter() - t
    ok = [x for x in batch if x["ok"]]
    lat = [x["elapsed_s"] for x in batch]
    row = {
        "mode": a.mode,
        "concurrency": a.concurrency,
        "round": rnd,
        "requests": batch,
        "success": len(ok),
        "errors": len(batch) - len(ok),
        "wall_s": wall,
        "aggregate_output_tps": sum(x["output_len"] for x in ok) / wall if wall else 0,
        "latency_p50_s": statistics.median(lat),
        "latency_p95_s": sorted(lat)[min(len(lat) - 1, int(0.95 * len(lat)))],
        "latency_max_s": max(lat),
    }
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(row, indent=2) + "\n")
    print(json.dumps({k: v for k, v in row.items() if k != "requests"}), flush=True)
