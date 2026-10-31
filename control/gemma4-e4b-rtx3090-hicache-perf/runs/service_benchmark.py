#!/usr/bin/env python3
"""Run ordered c1..c32 64/256 Gemma service benchmark against SGLang /generate."""

import argparse
import concurrent.futures
import hashlib
import json
import math
import os
import pathlib
import random
import statistics
import threading
import time
import urllib.request

OUT = pathlib.Path(os.environ.get("GSM_PERF_OUT", "/tmp/gemma4-bench"))
URL = "http://127.0.0.1:31371/generate"
CONCURRENCIES = (1, 2, 4, 8, 16, 24, 32)
TRIALS = 3
WARMUP = 1


def sha(data):
    return hashlib.sha256(data).hexdigest()


def percentile(values, q):
    values = sorted(values)
    return values[min(len(values) - 1, max(0, math.ceil(q * len(values)) - 1))]


def request(ids, output=256):
    body = {
        "input_ids": ids,
        "sampling_params": {
            "temperature": 0.0,
            "top_p": 1.0,
            "max_new_tokens": output,
            "min_new_tokens": output,
            "ignore_eos": True,
        },
        "return_token_ids": True,
    }
    req = urllib.request.Request(
        URL,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    start = time.perf_counter()
    response = json.loads(urllib.request.urlopen(req, timeout=1800).read())
    latency = time.perf_counter() - start
    meta = response.get("meta_info", {})
    output_ids = response.get("output_ids", meta.get("output_token_ids", []))
    count = meta.get("completion_tokens", len(output_ids))
    if int(count) != output or (output_ids and len(output_ids) != output):
        raise RuntimeError(
            f"expected exactly {output} generated tokens, got {count}/{len(output_ids)}"
        )
    dispatch_done = meta.get("api_server_dispatch_finish_ts")
    prefill_done = meta.get("prefill_finished_time")
    # No first-token timestamp is returned; this is the server-side
    # dispatch-to-prefill-complete proxy, not exact TTFT.
    prefill_latency = (
        float(prefill_done) - float(dispatch_done)
        if dispatch_done is not None and prefill_done is not None
        else None
    )
    return {
        "wall_s": latency,
        "prefill_done_minus_dispatch_s": prefill_latency,
        "decode_throughput_tps": meta.get("decode_throughput"),
        "tpot_s": (1.0 / float(meta["decode_throughput"])) if meta.get("decode_throughput") else None,
        "request_received_ts": meta.get("request_received_ts"),
        "request_finished_ts": meta.get("request_finished_ts"),
        "meta": meta,
        "text": response.get("text", ""),
        "output_ids": output_ids,
        "output_tokens": int(count),
        "rid": meta.get("id"),
    }


def run_batch(inputs):
    gate = threading.Event()
    start = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(inputs)) as pool:
        futures = [
            pool.submit(lambda ids=ids: (gate.wait(), request(ids))[1])
            for ids in inputs
        ]
        gate.set()
        rows = [future.result() for future in futures]
    return rows, time.perf_counter() - start


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args()
    if args.prepare_only:
        rng = random.Random(20261101)
        fixture = {
            "seed": 20261101,
            "input_tokens": 64,
            "output_tokens": 256,
            "concurrency": CONCURRENCIES,
            "trials": TRIALS,
            "warmups": WARMUP,
            "prompts": {},
        }
        for concurrency in CONCURRENCIES:
            for trial in range(TRIALS + WARMUP):
                for index in range(concurrency):
                    fixture["prompts"][f"c{concurrency}-r{trial}-i{index}"] = [
                        rng.randrange(1, 260000) for _ in range(64)
                    ]
        raw = json.dumps(fixture, separators=(",", ":")).encode()
        (OUT / "fixture.json").write_bytes(raw)
        fixture_sha = sha(raw)
        (OUT / "fixture.sha256").write_text(fixture_sha + "\n")
        manifest = {
            "source_sha": os.environ["GSM_PERF_SOURCE_SHA"],
            "model_revision": "6cd26aaa2357fb2bad8c51699a7558a4d1a965bb",
            "model_sha256": "19d89d2a4b3e401a3eae75ec08ab112810421a036c91d8c8226b686be7fe0c5d",
            "fixture_sha256": fixture_sha,
            "kv": "bf16",
            "tp": 1,
            "attention": "triton",
            "decode_cuda_graph_max_bs": 16,
            "radix_cache": False,
            "workload": "64 input / 256 generated tokens; 4 unique requests per concurrency including warmup",
        }
        (OUT / "benchmark-manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n"
        )
        return
    if not args.run:
        raise SystemExit("choose --prepare-only or --run")

    fixture = json.loads((OUT / "fixture.json").read_text())
    records = []
    for concurrency in CONCURRENCIES:
        for trial in range(TRIALS + WARMUP):
            ids = [
                fixture["prompts"][f"c{concurrency}-r{trial}-i{i}"]
                for i in range(concurrency)
            ]
            rows, wall = run_batch(ids)
            record = {
                "concurrency": concurrency,
                "trial": trial,
                "warmup": trial == 0,
                "wall_s": wall,
                "output_tokens": sum(row["output_tokens"] for row in rows),
                "aggregate_output_tps": sum(row["output_tokens"] for row in rows)
                / wall,
                "requests": rows,
            }
            records.append(record)
            print(
                json.dumps({k: v for k, v in record.items() if k != "requests"}),
                flush=True,
            )
            with (OUT / "service-raw.jsonl").open("a") as stream:
                stream.write(json.dumps(record) + "\n")

    summary = []
    for concurrency in CONCURRENCIES:
        measured = [
            r for r in records if r["concurrency"] == concurrency and not r["warmup"]
        ]
        rates = [r["aggregate_output_tps"] for r in measured]
        requests = [req for r in measured for req in r["requests"]]
        prefill_latency = [
            float(req["prefill_done_minus_dispatch_s"])
            for req in requests
            if req["prefill_done_minus_dispatch_s"] is not None
        ]
        tpot = [float(req["tpot_s"]) for req in requests if req["tpot_s"] is not None]
        summary.append(
            {
                "concurrency": concurrency,
                "trials_tps": rates,
                "mean_tps": statistics.mean(rates),
                "sd_tps": statistics.stdev(rates),
                "prefill_done_minus_dispatch_s": {
                    "p50": percentile(prefill_latency, 0.50),
                    "p95": percentile(prefill_latency, 0.95),
                }
                if prefill_latency
                else None,
                "tpot_s": {"p50": percentile(tpot, 0.50), "p95": percentile(tpot, 0.95)}
                if tpot
                else None,
                "server_e2e_s": {
                    "p50": percentile([x["meta"]["e2e_latency"] for x in requests], 0.50),
                    "p95": percentile([x["meta"]["e2e_latency"] for x in requests], 0.95),
                },
                "client_request_latency_s": {
                    "p50": percentile([x["wall_s"] for x in requests], 0.50),
                    "p95": percentile([x["wall_s"] for x in requests], 0.95),
                },
                "successful_requests": len(requests),
                "all_output_tokens_256": all(
                    x["output_tokens"] == 256 for x in requests
                ),
            }
        )
    (OUT / "service-summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
