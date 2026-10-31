#!/usr/bin/env python3
"""Recompute latency percentiles and CUDA-event step summaries from archived run."""

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path


def percentile(values, q):
    values = sorted(values)
    if not values:
        raise ValueError("empty sample")
    position = (len(values) - 1) * q
    low = int(position)
    high = min(low + 1, len(values) - 1)
    return values[low] + (values[high] - values[low]) * (position - low)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    args = parser.parse_args()
    records = json.loads((args.run / "records.json").read_text())
    log = (args.run / "server.log").read_text(errors="replace")
    event_re = re.compile(
        r"RADIX8K_GPU_FORWARD rids=(\S+) category=(\S+) batch=(\d+) gpu_s=([0-9.]+)"
    )
    scheduler_re = re.compile(
        r"Decode batch, #running-req: (\d+),.*cuda graph: (True|False)"
    )
    decode_seconds = defaultdict(lambda: defaultdict(float))
    event_batches = defaultdict(Counter)
    for rids, category, batch, elapsed in event_re.findall(log):
        if category != "decode":
            continue
        match = re.search(r"radix8k-perf-c(16|24|32)-r(\d+)-", rids)
        if not match:
            continue
        concurrency, round_id = map(int, match.groups())
        if round_id == 0:
            continue
        decode_seconds[concurrency][round_id] += float(elapsed)
        event_batches[concurrency][int(batch)] += 1

    scheduler_batches = Counter()
    for batch, graph in scheduler_re.findall(log):
        batch = int(batch)
        if batch in (16, 24, 32):
            scheduler_batches[(batch, graph)] += 1

    for concurrency in (16, 24, 32):
        requests = [
            request
            for row in records
            if row["concurrency"] == concurrency and not row["warmup"]
            for request in row["requests"]
        ]
        print(f"c={concurrency} requests={len(requests)}")
        for label, values in (
            ("TPOT_ms", [request["tpot_s"] * 1000 for request in requests]),
            ("TTFT_s", [request["ttft_s"] for request in requests]),
            ("E2E_s", [request["e2e_s"] for request in requests]),
        ):
            print(
                f"  {label} n={len(values)} p50={percentile(values, 0.5):.6f} "
                f"p95={percentile(values, 0.95):.6f}"
            )
        step_ms = [
            seconds / 256 * 1000 for seconds in decode_seconds[concurrency].values()
        ]
        print(
            f"  Decode-CUDA-Event round-mean step ms n={len(step_ms)} "
            f"p50={percentile(step_ms, 0.5):.6f} p95={percentile(step_ms, 0.95):.6f} "
            f"rounds={step_ms}"
        )
        print(
            f"  Decode-CUDA-Event batches={dict(event_batches[concurrency])}; "
            f"Scheduler graph batches="
            f"{ {batch: count for (batch, graph), count in scheduler_batches.items() if graph == 'True'} }; "
            f"non_graph_batches={ {batch: count for (batch, graph), count in scheduler_batches.items() if graph == 'False'} }"
        )


if __name__ == "__main__":
    main()
