#!/usr/bin/env python3
"""Summarize actual CUDA Event forward durations by request wave and category."""

import argparse, collections, re, statistics
from pathlib import Path

EVENT = re.compile(
    r"RADIX8K_GPU_FORWARD rids=(\S+) category=(\S+) batch=(\d+) gpu_s=([0-9.]+)"
)
RID = re.compile(r"radix8k-perf-c(\d+)-r(\d+)-")
p = argparse.ArgumentParser()
p.add_argument("log", type=Path)
p.add_argument("--measured-only", action="store_true")
a = p.parse_args()
pref = collections.defaultdict(list)
dec = collections.defaultdict(
    lambda: {"sec": 0.0, "tokens": 0, "events": 0, "batches": collections.Counter()}
)
for line in a.log.open(errors="replace"):
    m = EVENT.search(line)
    if not m:
        continue
    ids = m[1].split(",")
    parsed = [RID.search(x) for x in ids]
    if not all(parsed):
        continue
    keys = {(int(x[1]), int(x[2])) for x in parsed}
    if len(keys) != 1:
        raise RuntimeError(f"cross-wave event {m[1]}")
    c, r = next(iter(keys))
    if a.measured_only and r == 0:
        continue
    cat, bs, sec = m[2], int(m[3]), float(m[4])
    if cat == "extend":
        pref[(c, r, bs, len(ids))].append(sec)
    elif cat in ("decode", "decode_graph"):
        d = dec[(c, r)]
        d["sec"] += sec
        d["events"] += 1
        d["tokens"] += bs
        d["batches"][bs] += 1
print("Prefill Extend CUDA Event per wave (joint actual batch duration; milliseconds)")
for (c, r, bs, n), v in sorted(pref.items()):
    print(
        f"c={c} round={r} actual_batch={bs} joined_rids={n} events={len(v)} mean_ms={statistics.mean(v) * 1000:.3f}"
    )
print("Decode CUDA Event TPS per wave = batch token steps / summed CUDA Event duration")
for (c, r), d in sorted(dec.items()):
    print(
        f"c={c} round={r} events={d['events']} batch_hist={dict(d['batches'])} token_steps={d['tokens']} event_s={d['sec']:.6f} tps={d['tokens'] / d['sec']:.3f}"
    )
