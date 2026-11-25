#!/usr/bin/env python3
"""T007: summarize DeviceTimer forward time, duty, batches and cache counters.

Reads only the run's sampled /metrics JSONL and scheduler log.
"""

from __future__ import annotations

import json
import re
import statistics
import sys
from pathlib import Path


def load_series(path: Path):
    rows = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def main() -> int:
    run = Path(sys.argv[1])
    series = load_series(run / "pool-series.jsonl")
    valid = [r for r in series if "error" not in r and "t" in r]
    print(
        f"samples={len(valid)}/{len(series)} first_t={valid[0]['t'] if valid else None} last_t={valid[-1]['t'] if valid else None}"
    )
    keys = sorted(
        {k for r in series for k in r if "forward_execution_seconds_total" in k}
    )
    print("forward_execution keys:", keys)
    for k in keys:
        vals = [(r["t"], r[k]) for r in valid if k in r]
        if len(vals) < 2:
            continue
        total = vals[-1][1] - vals[0][1]
        span = vals[-1][0] - vals[0][0]
        print(
            f"  {k}: total={total:.1f}s span={span:.1f}s duty={100 * total / span if span else 0:.2f}%"
        )
    if keys:
        # Duty over the whole sampled run, plus the max wall-adjacent slope.
        first, last = valid[0], valid[-1]
        span = last["t"] - first["t"]
        grand = sum(last.get(k, 0) - first.get(k, 0) for k in keys)
        print(
            f"all_categories_total={grand:.1f}s wall={span:.1f}s duty={100 * grand / span if span else 0:.2f}%"
        )

    gauge = [(r["t"], r["fwd_occupancy"]) for r in valid if "fwd_occupancy" in r and r["fwd_occupancy"] == r["fwd_occupancy"]]
    if gauge:
        vals = sorted(v for _, v in gauge)
        print(
            f"fwd_occupancy samples={len(vals)} p50={statistics.median(vals):.2f} p90={vals[int(0.9 * len(vals))]:.2f} max={vals[-1]:.2f}"
        )

    for key in (
        "max_total_num_tokens",
        "kv_used_tokens",
        "swa_used_tokens",
        "swa_available_tokens",
        "hicache_host_used_tokens",
        "num_running_reqs",
        "num_queue_reqs",
    ):
        vals = [r[key] for r in valid if key in r]
        if vals:
            print(f"{key}: min={min(vals):.0f} max={max(vals):.0f}")
    for key in sorted(
        {k for r in valid for k in r if k.startswith("hicache_prompt_tokens_total")}
    ):
        vals = [r[key] for r in valid if key in r]
        if vals:
            print(f"{key}: delta={vals[-1] - vals[0]:.0f}")

    log = run / "server.log"
    if log.exists():
        texts = log.read_text(errors="replace").splitlines()
        prefill = re.findall(
            r"Prefill batch.*?#new-seq: (\d+), #new-token: (\d+)", "\n".join(texts)
        )
        decode = re.findall(
            r"Decode batch, #running-req: (\d+), #full token: (\d+)", "\n".join(texts)
        )
        if prefill:
            seqs = [int(a) for a, _ in prefill]
            toks = [int(b) for _, b in prefill]
            print(
                f"prefill_batches={len(prefill)} seq_mean={statistics.mean(seqs):.2f} seq_hist={ {i: seqs.count(i) for i in sorted(set(seqs))} }"
            )
            print(
                f"prefill_new_tokens={sum(toks)} tokens_per_batch_mean={statistics.mean(toks):.1f} max={max(toks)}"
            )
        if decode:
            bs = [int(a) for a, _ in decode]
            print(
                f"decode_log_lines={len(decode)} running_req_mean={statistics.mean(bs):.1f} hist={ {i: bs.count(i) for i in sorted(set(bs))} }"
            )
        cfg = re.search(
            r"max_total_num_tokens=(\d+), chunked_prefill_size=(\d+), max_prefill_tokens=(\d+), max_running_requests=(\d+)",
            "\n".join(texts),
        )
        if cfg:
            print("runtime_config pool/chunk/maxprefill/maxrunning =", cfg.groups())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
