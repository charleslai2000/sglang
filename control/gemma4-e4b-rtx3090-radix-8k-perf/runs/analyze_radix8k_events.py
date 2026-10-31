#!/usr/bin/env python3
"""Summarize existing Radix8K DeviceTimer CUDA-event logs; does not run workloads."""

import collections
import re
import argparse
import statistics
from pathlib import Path

DEFAULT_RUNS = {
    "/data/sglang-hicache/gemma4/runs/20261031T141513Z-radix8k-prefix-benchmark/server.log": {
        1
    },
    "/data/sglang-hicache/gemma4/runs/20261031T142335Z-radix8k-prefix-benchmark/server.log": {
        2,
        4,
        8,
        16,
        24,
        32,
    },
}
EVENT = re.compile(
    r"RADIX8K_GPU_FORWARD rids=(\S+) category=(\S+) batch=(\d+) gpu_s=([0-9.]+)"
)
RID = re.compile(r"radix8k-perf-c(\d+)-r(\d+)-")

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("logs", nargs="*", type=Path)
parser.add_argument("--concurrency", nargs="*", type=int)
parser.add_argument("--measured-only", action="store_true")
args = parser.parse_args()
run_paths = args.logs or [Path(path) for path in DEFAULT_RUNS]
allowed_concurrency = set(args.concurrency or ())
prefill = collections.defaultdict(list)
decode = collections.defaultdict(lambda: {"seconds": 0.0, "events": 0, "tokens": 0})
for filename in run_paths:
    if not filename.is_file():
        raise FileNotFoundError(filename)
    for line in filename.open():
        match = EVENT.search(line)
        if not match:
            continue
        rids, category, batch_text, elapsed_text = match.groups()
        batch, elapsed = int(batch_text), float(elapsed_text)
        members = rids.split(",")
        identities = [RID.search(rid) for rid in members]
        if not all(identities):
            continue
        rounds = {(int(item[1]), int(item[2])) for item in identities}
        if len(rounds) != 1:
            raise RuntimeError(f"CUDA event crosses concurrency/rounds: {rids}")
        concurrency, round_id = next(iter(rounds))
        if allowed_concurrency and concurrency not in allowed_concurrency:
            continue
        if args.measured_only and round_id == 0:
            continue
        if category == "extend":
            prefill[(concurrency, batch, len(members))].append(elapsed)
        elif category == "decode" and (not args.measured_only or round_id > 0):
            item = decode[concurrency]
            item["seconds"] += elapsed
            item["events"] += 1
            item["tokens"] += batch

print("Prefill extend CUDA events (milliseconds)")
for (concurrency, batch, rid_count), samples in sorted(prefill.items()):
    print(
        f"c={concurrency} batch={batch} event_rids={rid_count} n={len(samples)} "
        f"mean_ms={statistics.mean(samples) * 1000:.3f} "
        f"min_ms={min(samples) * 1000:.3f} max_ms={max(samples) * 1000:.3f}"
    )
print(
    "Decode-only aggregate: "
    + ("measured rounds only" if args.measured_only else "all rounds, warmup included")
)
for concurrency, item in sorted(decode.items()):
    print(
        f"c={concurrency} events={item['events']} decode_tokens={item['tokens']} "
        f"cuda_event_seconds={item['seconds']:.9f} "
        f"aggregate_tps={item['tokens'] / item['seconds']:.3f}"
    )
