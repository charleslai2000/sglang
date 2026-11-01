#!/usr/bin/env python3
"""Summarize per-request Prefill CUDA Event time and GPU-memory sampling."""

import json, pathlib, re, statistics, sys

run = pathlib.Path(sys.argv[1])
data = json.load(open(run / "prefill-sizes.json"))
log = (run / "nsys-launch.log").read_text(errors="replace")
samples = []
for line in (run / "gpu-samples.csv").read_text().splitlines()[1:]:
    try:
        samples.append(int(line.split(",")[1].strip().split()[0]))
    except (IndexError, ValueError):
        pass
peak = max(samples) if samples else None
for rec in data:
    rid = rec["meta"]["id"]
    line = next(
        x
        for x in log.splitlines()
        if f"RADIX8K_GPU_FORWARD rids={rid} category=extend" in x
    )
    match = re.search(r"gpu_s=([0-9.]+)", line)
    if match is None:
        raise ValueError(f"missing GPU Event duration for {rid}: {line}")
    event_s = float(match.group(1))
    throughput = rec["tokens"] / event_s
    result = {
        "tokens": rec["tokens"],
        "rid": rid,
        "cached_tokens": rec["meta"].get("cached_tokens"),
        "prefill_cuda_event_ms": event_s * 1000,
        "cuda_event_input_tps": throughput,
        "scheduler_forward_wall_ms": (
            rec["meta"]["prefill_finished_time"] - rec["meta"]["forward_entry_time"]
        )
        * 1000,
        "client_wall_ms": rec["wall_s"] * 1000,
        "sampled_gpu_peak_mib_including_model_and_KV": peak,
        "gpu_sample_count": len(samples),
        "gpu_memory_sample_interval_ms": 100,
    }
    print(json.dumps(result))
