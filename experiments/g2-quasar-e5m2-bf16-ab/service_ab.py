#!/usr/bin/env python3
"""Matched BF16/E5M2 KV service throughput A/B using a frozen synthetic fixture."""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import math
import os
import random
import statistics
import threading
import time
import urllib.request
from pathlib import Path

CONCURRENCIES = (1, 4, 16)
FIXTURE_CONCURRENCIES = (1, 4, 8, 16)
TRIALS = 3
WARMUPS = 1
INPUT_TOKENS = 64
OUTPUT_TOKENS = 32
SEED = 20261110


def canonical_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_fixture() -> dict:
    rng = random.Random(SEED)
    return {
        f"c{c}-t{trial}-i{i}": [rng.randrange(1, 260000) for _ in range(INPUT_TOKENS)]
        for c in FIXTURE_CONCURRENCIES
        for trial in range(TRIALS + WARMUPS)
        for i in range(c)
    }


def request(url: str, ids: list[int], rid: str) -> dict:
    body = {
        "input_ids": ids,
        "sampling_params": {
            "temperature": 0.0,
            "top_p": 1.0,
            "top_k": 1,
            "min_new_tokens": OUTPUT_TOKENS,
            "max_new_tokens": OUTPUT_TOKENS,
            "ignore_eos": True,
            "sampling_seed": 1234,
        },
        "return_token_ids": True,
        "rid": rid,
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    start = time.perf_counter()
    with urllib.request.urlopen(req, timeout=900) as response:
        data = json.loads(response.read())
    wall = time.perf_counter() - start
    meta = data.get("meta_info", {})
    output_ids = data.get("output_ids", meta.get("output_token_ids", []))
    count = int(meta.get("completion_tokens", len(output_ids)))
    if count != OUTPUT_TOKENS or len(output_ids) != OUTPUT_TOKENS:
        raise RuntimeError(
            f"{rid}: expected {OUTPUT_TOKENS}, got completion={count}, ids={len(output_ids)}"
        )
    return {
        "rid": rid,
        "input_tokens": len(ids),
        "output_tokens": count,
        "wall_s": wall,
        "server_e2e_s": meta.get("e2e_latency"),
        "output_ids_sha256": hashlib.sha256(
            json.dumps(output_ids, separators=(",", ":")).encode()
        ).hexdigest(),
    }


def wave(url: str, ids: list[list[int]], rids: list[str]) -> tuple[list[dict], float]:
    gate = threading.Event()
    start = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(ids)) as pool:
        futures = [
            pool.submit(
                lambda token_ids=token_ids, rid=rid: (
                    gate.wait(),
                    request(url, token_ids, rid),
                )[1]
            )
            for token_ids, rid in zip(ids, rids)
        ]
        gate.set()
        results = [future.result() for future in futures]
    return results, time.perf_counter() - start


def percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, max(0, math.ceil(q * len(ordered)) - 1))]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--arm", choices=("bf16", "fp8_e5m2"), required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--fixture", type=Path)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    fixture = make_fixture()
    fixture_path = args.fixture or args.out / "fixture.json"
    if args.fixture:
        saved = json.loads(args.fixture.read_text())
        expected_meta = {
            "seed": SEED,
            "input_tokens": INPUT_TOKENS,
            "output_tokens": OUTPUT_TOKENS,
            "trials": TRIALS,
            "warmups": WARMUPS,
        }
        if any(saved.get(key) != value for key, value in expected_meta.items()):
            raise RuntimeError("provided fixture metadata differs from the frozen workload")
        saved_ids = saved.get("ids", {})
        required = {
            f"c{c}-t{trial}-i{i}"
            for c in CONCURRENCIES
            for trial in range(TRIALS + WARMUPS)
            for i in range(c)
        }
        if not required.issubset(saved_ids):
            raise RuntimeError("provided fixture does not contain all c1/c4/c16 request IDs")
        fixture = saved_ids
    else:
        fixture_path.write_text(
            json.dumps(
                {
                    "seed": SEED,
                    "input_tokens": INPUT_TOKENS,
                    "output_tokens": OUTPUT_TOKENS,
                    "concurrency": list(CONCURRENCIES),
                    "trials": TRIALS,
                    "warmups": WARMUPS,
                    "ids": fixture,
                },
                separators=(",", ":"),
            )
            + "\n"
        )

    raw_path = args.out / "raw.jsonl"
    if raw_path.exists():
        raise FileExistsError(f"refusing to overwrite {raw_path}")
    records = []
    for concurrency in CONCURRENCIES:
        for trial in range(TRIALS + WARMUPS):
            request_ids = [
                f"g2-ab-{args.arm}-c{concurrency}-t{trial}-i{i}"
                for i in range(concurrency)
            ]
            prompts = [
                fixture[f"c{concurrency}-t{trial}-i{i}"] for i in range(concurrency)
            ]
            results, wall = wave(args.url, prompts, request_ids)
            record = {
                "arm": args.arm,
                "concurrency": concurrency,
                "trial": trial,
                "warmup": trial < WARMUPS,
                "requests": results,
                "wall_s": wall,
                "completed_tokens": sum(row["output_tokens"] for row in results),
                "aggregate_output_tps": sum(row["output_tokens"] for row in results)
                / wall,
                "successful_requests": len(results),
            }
            records.append(record)
            with raw_path.open("a") as stream:
                stream.write(json.dumps(record) + "\n")
            print(
                json.dumps({k: v for k, v in record.items() if k != "requests"}),
                flush=True,
            )

    summary = []
    for concurrency in CONCURRENCIES:
        measured = [
            r for r in records if r["concurrency"] == concurrency and not r["warmup"]
        ]
        rates = [r["aggregate_output_tps"] for r in measured]
        request_wall = [q["wall_s"] for r in measured for q in r["requests"]]
        summary.append(
            {
                "concurrency": concurrency,
                "trial_aggregate_output_tps": rates,
                "mean_aggregate_output_tps": statistics.mean(rates),
                "sample_sd_tps": statistics.stdev(rates),
                "request_wall_p50_p95_s": [
                    percentile(request_wall, 0.5),
                    percentile(request_wall, 0.95),
                ],
                "measured_waves": len(measured),
                "successful_requests": sum(r["successful_requests"] for r in measured),
                "all_requests_completed_exactly_32_tokens": all(
                    q["output_tokens"] == OUTPUT_TOKENS
                    for r in measured
                    for q in r["requests"]
                ),
            }
        )
    result = {
        "arm": args.arm,
        "fixture_sha256": canonical_sha(fixture_path),
        "fixture_path": str(fixture_path),
        "runtime_workload": {
            "input_tokens": INPUT_TOKENS,
            "output_tokens": OUTPUT_TOKENS,
            "concurrency": list(CONCURRENCIES),
            "warmups": WARMUPS,
            "measured_waves_per_concurrency": TRIALS,
        },
        "summary": summary,
        "raw_sha256": canonical_sha(raw_path),
    }
    (args.out / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
