#!/usr/bin/env python3
"""Generate/analyze shared-prefix E5M2 fixtures and real HTTP requests."""

import argparse, hashlib, json, os, statistics, time, urllib.request
from pathlib import Path
from transformers import AutoTokenizer

p = argparse.ArgumentParser()
p.add_argument(
    "--action", choices=["fixture", "warm", "batch", "analyze", "evict"], required=True
)
p.add_argument("--url", default="http://127.0.0.1:31401")
p.add_argument("--fixture", required=True)
p.add_argument("--out", required=True)
p.add_argument("--count", type=int, default=32)
p.add_argument("--prefix-tokens", type=int, default=63488)
p.add_argument("--total-tokens", type=int, default=65536)
p.add_argument("--new-tokens", type=int, default=64)
a = p.parse_args()
F = Path(a.fixture)
O = Path(a.out)
O.mkdir(parents=True, exist_ok=True)


def post(obj, timeout=3600):
    r = urllib.request.Request(
        a.url + "/generate",
        data=json.dumps(obj).encode(),
        headers={"Content-Type": "application/json"},
    )
    return json.loads(urllib.request.urlopen(r, timeout=timeout).read())


def prompt(ids, rid, n=None):
    return {
        "rid": rid,
        "input_ids": [ids],
        "sampling_params": {
            "temperature": 0,
            "top_p": 1,
            "max_new_tokens": n or a.new_tokens,
            "min_new_tokens": n or a.new_tokens,
            "ignore_eos": True,
        },
        "return_token_ids": True,
    }


def observe():
    for endpoint in ("/metrics", "/get_server_info"):
        try:
            return urllib.request.urlopen(a.url + endpoint, timeout=10).read().decode()
        except Exception:
            pass
    return ""


def one(ids, rid, n=None):
    t = time.perf_counter()
    x = post(prompt(ids, rid, n))
    x = x[0] if isinstance(x, list) and len(x) == 1 else x
    m = x.get("meta_info", {})
    return {
        "rid": m.get("id", rid),
        "elapsed_s": time.perf_counter() - t,
        "output_ids": x.get("output_ids", []),
        "output_text": x.get("text", ""),
        "meta": m,
        "ttft_s": (m.get("first_token_ts", 0) - m.get("request_received_ts", 0)) or None,
        "tpot_s": ((m.get("request_finished_ts", 0) - m.get("first_token_ts", 0)) / max(1, m.get("completion_tokens", len(x.get("output_ids", []))) - 1)) if m.get("first_token_ts") and m.get("request_finished_ts") else None,
        "ok": m.get("completion_tokens", len(x.get("output_ids", [])))
        >= (n or a.new_tokens),
    }


if a.action == "fixture":
    tok = AutoTokenizer.from_pretrained(
        "/data/sglang-hicache/gemma4/model", trust_remote_code=True
    )
    prefix_text = "G1 production readiness deterministic shared KV prefix. This text is repeated verbatim so all requests share precisely the same token IDs.\n"
    unit = tok.encode(prefix_text, add_special_tokens=False)
    base = (unit * ((a.prefix_tokens + len(unit) - 1) // len(unit)))[: a.prefix_tokens]
    assert len(base) == a.prefix_tokens
    rows = []
    for i in range(a.count):
        suffix_text = f"\nIndependent request identifier: client-{i:02d}. Continue this distinct context accurately."
        s = tok.encode(suffix_text, add_special_tokens=False)
        ids = base + s
        if len(ids) < a.total_tokens:
            filler = tok.encode(
                f"Client-{i:02d} private continuation block. ", add_special_tokens=False
            )
            ids += (
                filler * ((a.total_tokens - len(ids) + len(filler) - 1) // len(filler))
            )[: a.total_tokens - len(ids)]
        ids = ids[: a.total_tokens]
        assert ids[: len(base)] == base and len(ids) == a.total_tokens
        rows.append(
            {
                "rid": f"g1sp-{i:02d}",
                "input_ids": ids,
                "prefix_tokens": len(base),
                "suffix_tokens": len(ids) - len(base),
                "prefix_sha256": hashlib.sha256(
                    json.dumps(base, separators=(",", ":")).encode()
                ).hexdigest(),
            }
        )
    d = {
        "fixture_kind": "E5M2_SHARED_PREFIX_64K",
        "tokenizer": "/data/sglang-hicache/gemma4/model",
        "count": len(rows),
        "prefix_tokens": len(base),
        "total_tokens": a.total_tokens,
        "distinct_suffixes": len({tuple(r["input_ids"][len(base) :]) for r in rows}),
        "prefix_sha256": rows[0]["prefix_sha256"],
        "requests": rows,
    }
    assert d["distinct_suffixes"] == a.count
    F.write_text(json.dumps(d, separators=(",", ":")) + "\n")
    print(json.dumps({k: v for k, v in d.items() if k != "requests"}))
elif a.action == "warm":
    d = json.load(open(F))
    r = one(d["requests"][0]["input_ids"], "g1sp-prefix-warm", a.new_tokens)
    (O / "warm.json").write_text(json.dumps(r, indent=2) + "\n")
    (O / "warm-metrics.txt").write_text(observe())
    print(json.dumps({"ok": r["ok"], "elapsed_s": r["elapsed_s"], "meta": r["meta"]}))
elif a.action == "batch":
    d = json.load(open(F))
    import concurrent.futures, threading

    gate = threading.Event()

    def f(x):
        gate.wait()
        return one(x["input_ids"], x["rid"], a.new_tokens)

    t = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=a.count) as ex:
        fs = [ex.submit(f, x) for x in d["requests"]]
        gate.set()
        rs = [z.result() for z in fs]
    wall = time.perf_counter() - t
    good = [r for r in rs if r["ok"]]
    lat = [r["elapsed_s"] for r in rs]
    json.dump(
        {
            "count": len(rs),
            "success": len(good),
            "errors": len(rs) - len(good),
            "wall_s": wall,
            "aggregate_output_tps": sum(len(r["output_ids"]) for r in good) / wall,
            "latency_p50_s": statistics.median(lat),
            "latency_p95_s": sorted(lat)[int(0.95 * (len(lat) - 1))],
            "ttft_p50_s": statistics.median([r["ttft_s"] for r in good if r.get("ttft_s") is not None]) if good else None,
            "ttft_p95_s": sorted([r["ttft_s"] for r in good if r.get("ttft_s") is not None])[int(0.95 * (len(good) - 1))] if good else None,
            "tpot_p50_s": statistics.median([r["tpot_s"] for r in good if r.get("tpot_s") is not None]) if good else None,
            "requests": rs,
        },
        open(O / "batch.json", "w"),
        indent=2,
    )
    print(
        json.dumps(
            {
                "count": len(rs),
                "success": len(good),
                "wall_s": wall,
                "aggregate_output_tps": sum(len(r["output_ids"]) for r in good) / wall,
            }
        )
    )
elif a.action == "analyze":
    d = json.load(open(O / "batch.json"))
    logs = Path(a.url).name if False else None
    print(
        json.dumps(
            {
                "success": d["success"],
                "wall_s": d["wall_s"],
                "aggregate_output_tps": d["aggregate_output_tps"],
                "latency_p50_s": d["latency_p50_s"],
                "latency_p95_s": d["latency_p95_s"],
            }
        )
    )
