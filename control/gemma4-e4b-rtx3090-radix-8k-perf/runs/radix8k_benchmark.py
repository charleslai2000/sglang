#!/usr/bin/env python3
"""Deterministic long-prefix Radix-cache online benchmark client."""

import concurrent.futures
import hashlib
import os
import subprocess
import hashlib
import json
import math
import os
import pathlib
import threading
import time
import urllib.request

OUT = pathlib.Path(os.environ.get("RADIX8K_OUT", "/tmp/radix8k"))
URL = os.environ.get("RADIX8K_URL", "http://127.0.0.1:31371/generate")
CONCURRENCIES = (1, 2, 4, 8, 16, 24, 32)
ROUNDS = 4
PREFIX, SUFFIX, OUTPUT = 7168, 1024, 256


def sha(b):
    return hashlib.sha256(b).hexdigest()


def prepare(tokenizer_path):
    from transformers import AutoTokenizer

    tok = AutoTokenizer.from_pretrained(tokenizer_path, trust_remote_code=True)
    ids = tok.encode(
        "Radix cache prefix benchmark. The shared context is fixed and deterministic. "
        * 5000,
        add_special_tokens=False,
    )
    prefix = ids[:PREFIX]
    # This fixture is generated once per fresh server, avoiding prior-run cache reuse.
    if len(prefix) != PREFIX:
        raise RuntimeError("could not construct the exact shared prefix")
    prompts, suffixes = {}, {}
    prompts["primer"] = prefix
    suffixes["primer"] = []
    for c in CONCURRENCIES:
        for r in range(ROUNDS):
            for i in range(c):
                key = f"c{c}-r{r}-i{i}"
                suffix = tok.encode(
                    f" Unique request suffix {key} ", add_special_tokens=False
                )
                k = 0
                while len(suffix) < SUFFIX:
                    suffix.extend(
                        tok.encode(f" {key} payload{k} ", add_special_tokens=False)
                    )
                    k += 1
                suffix = suffix[:SUFFIX]
                # Keep suffix IDs in the tokenizer's natural text domain.
                suffixes[key] = suffix
                prompts[key] = prefix + suffix
    if len({tuple(v) for v in suffixes.values()}) != len(suffixes):
        raise RuntimeError("duplicate suffix")
    if any(len(v) != PREFIX + SUFFIX for k, v in prompts.items() if k != "validation"):
        raise RuntimeError("prompt length error")
    validation_suffix = list(suffixes["c1-r0-i0"])
    # Guarantee the clean-service probe diverges exactly at the cache boundary.
    # Token 50 is a valid ordinary Gemma text token and not a configured stop ID.
    validation_suffix[0] = 50
    prompts["validation"] = prefix + validation_suffix
    suffixes["validation"] = validation_suffix
    OUT.mkdir(parents=True, exist_ok=True)
    fixture = {
        "prefix_tokens": PREFIX,
        "suffix_tokens": SUFFIX,
        "input_tokens": PREFIX + SUFFIX,
        "output_tokens": OUTPUT,
        "prefix_ids": prefix,
        "prompts": prompts,
        "suffixes": suffixes,
    }
    raw = json.dumps(fixture, separators=(",", ":")).encode()
    (OUT / "fixture.json").write_bytes(raw)
    (OUT / "fixture.sha256").write_text(sha(raw) + "\n")


def post(ids, rid, output_tokens=OUTPUT):
    body = {
        "rid": rid,
        "input_ids": [ids],
        "sampling_params": {
            "temperature": 0,
            "top_p": 1,
            "max_new_tokens": output_tokens,
            "min_new_tokens": output_tokens,
            "logit_bias": {str(t): -100.0 for t in [1, 105, 106]},
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
    t0 = time.perf_counter()
    obj = json.loads(urllib.request.urlopen(req, timeout=1800).read())
    wall = time.perf_counter() - t0
    if isinstance(obj, list):
        if len(obj) != 1 or not isinstance(obj[0], dict):
            raise RuntimeError(f"{rid}: unexpected batch response envelope")
        obj = obj[0]
    meta = obj.get("meta_info", {})
    outs = obj.get("output_ids", meta.get("output_token_ids", []))
    if len(outs) != output_tokens or int(meta.get("completion_tokens", len(outs))) != output_tokens:
        raise RuntimeError(f"{rid}: expected {output_tokens} outputs, got {len(outs)}")
    return {
        "rid": meta.get("id", rid),
        "wall_s": wall,
        "output_tokens": len(outs),
        "output_ids_sha256": sha(json.dumps(outs, separators=(",", ":")).encode()),
        "decode_throughput_tps": meta.get("decode_throughput"),
        "tpot_s": 1 / float(meta["decode_throughput"])
        if meta.get("decode_throughput")
        else None,
        "e2e_s": meta.get("e2e_latency"),
        "ttft_s": (meta["first_token_ts"] - meta["request_received_ts"])
        if meta.get("first_token_ts") and meta.get("request_received_ts")
        else None,
        "meta": meta,
    }


def run(concurrency_only=None, selected_concurrencies=None):
    fixture = json.loads((OUT / "fixture.json").read_text())
    records = []
    concurrencies = (
        (concurrency_only,)
        if concurrency_only
        else tuple(selected_concurrencies)
        if selected_concurrencies
        else tuple(c for c in CONCURRENCIES if c != 1)
    )
    for c in concurrencies:
        if c == 1:
            continue
        for r in range(ROUNDS):
            gate = threading.Event()
            started = time.perf_counter()
            keys = [f"c{c}-r{r}-i{i}" for i in range(c)]
            cpu_start = time.process_time()
            with concurrent.futures.ThreadPoolExecutor(max_workers=c) as pool:
                futures = [
                    pool.submit(
                        lambda k=k: (
                            gate.wait(),
                            post(fixture["prompts"][k], "radix8k-perf-" + k),
                        )[1]
                    )
                    for k in keys
                ]
                gate.set()
                requests = [future.result() for future in futures]
            for request in requests:
                if request["meta"].get("cached_tokens") != PREFIX:
                    raise RuntimeError(f"{request['rid']}: expected cache hit {PREFIX}, got {request['meta'].get('cached_tokens')}")
            wall = time.perf_counter() - started
            record = {
                "concurrency": c,
                "round": r,
                "warmup": r == 0,
                "wall_s": wall,
                "aggregate_output_tps": sum(x["output_tokens"] for x in requests)
                / wall,
                "requests": requests,
                "cpu_s": time.process_time() - cpu_start,
            }
            records.append(record)
            print(
                json.dumps({k: v for k, v in record.items() if k != "requests"}),
                flush=True,
            )
            with (OUT / "raw.jsonl").open("a") as stream:
                stream.write(json.dumps(record) + "\n")
    (OUT / "records.json").write_text(json.dumps(records, indent=2) + "\n")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--tokenizer", default="/data/sglang-hicache/gemma4/model")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--c1-only", action="store_true")
    parser.add_argument("--prime", action="store_true")
    parser.add_argument("--validate", action="store_true")
    parser.add_argument("--accepted-validation", action="store_true")
    parser.add_argument("--concurrency", type=int, nargs="+", choices=CONCURRENCIES)
    args = parser.parse_args()
    if args.prepare:
        prepare(args.tokenizer)
    elif args.run:
        if not args.accepted_validation:
            parser.error("--run requires --accepted-validation after a separate 7168/1024+256 verification")
        if args.c1_only and args.concurrency:
            parser.error("--c1-only and --concurrency are mutually exclusive")
        run(
            concurrency_only=1 if args.c1_only else None,
            selected_concurrencies=args.concurrency,
        )
    elif args.prime or args.validate:
        fixture = json.loads((OUT / "fixture.json").read_text())
        name = "primer" if args.prime else "validation"
        result = post(fixture["prompts"][name], "radix8k-perf-" + name, output_tokens=1 if args.prime else OUTPUT)
        (OUT / (name + "-response.json")).write_text(json.dumps(result, indent=2) + "\n")
        if args.validate and result["meta"].get("cached_tokens") != PREFIX:
            raise RuntimeError(f"validation expected {PREFIX} cached tokens, got {result['meta'].get('cached_tokens')}")
        print(json.dumps(result, default=str), flush=True)
    else:
        parser.error("use --prepare, --run, --prime, or --validate")
