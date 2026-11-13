#!/usr/bin/env python3
"""Historical Radix8K workload adapted to the QUASAR tokenizer/model path."""

import argparse, concurrent.futures, hashlib, json, os, statistics, threading, time, urllib.request
from pathlib import Path

CONCURRENCIES = (1, 2, 4, 8, 16, 24, 32)
ROUNDS = 4
PREFIX, SUFFIX, OUTPUT = 7168, 1024, 256
HTTP_TIMEOUT = 7200
OUT = Path(os.environ.get("RADIX8K_OUT", "/tmp/radix8k"))
URL = os.environ.get("RADIX8K_URL", "http://127.0.0.1:31381/generate")


def sha(b):
    return hashlib.sha256(b).hexdigest()


def post(ids, rid, n=OUTPUT):
    body = {
        "rid": rid,
        "input_ids": [ids],
        "sampling_params": {
            "temperature": 0,
            "top_p": 1,
            "max_new_tokens": n,
            "min_new_tokens": n,
            "logit_bias": {"1": -100.0, "105": -100.0, "106": -100.0},
            "ignore_eos": False,
            "stop": [],
            "stop_strs": [],
            "stop_token_ids": [],
        },
        "return_token_ids": True,
    }
    req = urllib.request.Request(
        URL,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    t = time.perf_counter()
    obj = json.loads(urllib.request.urlopen(req, timeout=HTTP_TIMEOUT).read())
    wall = time.perf_counter() - t
    if isinstance(obj, list):
        if len(obj) != 1 or not isinstance(obj[0], dict):
            raise RuntimeError(f"{rid}: invalid response envelope")
        obj = obj[0]
    m = obj.get("meta_info", {})
    outs = obj.get("output_ids", m.get("output_token_ids", []))
    count = int(m.get("completion_tokens", len(outs)))
    if count != n or len(outs) != n:
        raise RuntimeError(f"{rid}: output count {count}/{len(outs)} != {n}")
    if n == OUTPUT and m.get("cached_tokens") != PREFIX:
        raise RuntimeError(f"{rid}: cached_tokens={m.get('cached_tokens')} != {PREFIX}")
    return {
        "rid": m.get("id", rid),
        "wall_s": wall,
        "output_tokens": len(outs),
        "output_ids_sha256": sha(json.dumps(outs, separators=(",", ":")).encode()),
        "server_decode_throughput_tps": m.get("decode_throughput"),
        "tpot_s": 1 / float(m["decode_throughput"])
        if m.get("decode_throughput")
        else None,
        "e2e_s": m.get("e2e_latency"),
        "ttft_s": m.get("first_token_ts", 0) - m.get("request_received_ts", 0)
        if m.get("first_token_ts") and m.get("request_received_ts")
        else None,
        "cached_tokens": m.get("cached_tokens"),
        "meta": m,
    }


def run(selected):
    f = json.loads((OUT / "fixture.json").read_text())
    records = []
    for c in selected:
        for r in range(ROUNDS):
            started = time.perf_counter()
            gate = threading.Event()
            keys = [f"c{c}-r{r}-i{i}" for i in range(c)]
            with concurrent.futures.ThreadPoolExecutor(max_workers=c) as pool:
                futures = [
                    pool.submit(
                        lambda k=k: (
                            gate.wait(),
                            post(f["prompts"][k], "radix8k-perf-" + k),
                        )[1]
                    )
                    for k in keys
                ]
                gate.set()
                reqs = [x.result() for x in futures]
            if any(x["cached_tokens"] != PREFIX for x in reqs):
                raise RuntimeError(f"c{c}r{r}: cache miss")
            wall = time.perf_counter() - started
            rec = {
                "concurrency": c,
                "round": r,
                "warmup": r == 0,
                "wall_s": wall,
                "aggregate_output_tps": sum(x["output_tokens"] for x in reqs) / wall,
                "requests": reqs,
            }
            records.append(rec)
            with (OUT / "raw.jsonl").open("a") as o:
                o.write(json.dumps(rec) + "\n")
            print(
                json.dumps({k: v for k, v in rec.items() if k != "requests"}),
                flush=True,
            )
    (OUT / "records.json").write_text(json.dumps(records, indent=2) + "\n")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--run", action="store_true")
    p.add_argument("--accepted-validation", action="store_true")
    p.add_argument(
        "--concurrency",
        type=int,
        nargs="+",
        choices=CONCURRENCIES,
        default=list(CONCURRENCIES),
    )
    p.add_argument("--c1-only", action="store_true")
    a = p.parse_args()
    if not a.run or not a.accepted_validation:
        p.error("--run --accepted-validation required")
    if a.c1_only and a.concurrency != list(CONCURRENCIES):
        p.error("--c1-only cannot be combined with --concurrency")
    if (OUT / "raw.jsonl").exists():
        raise FileExistsError(OUT / "raw.jsonl")
    run((1,) if a.c1_only else a.concurrency)


if __name__ == "__main__":
    main()
