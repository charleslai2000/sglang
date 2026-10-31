#!/usr/bin/env python3
"""Recompute frozen service baseline tables from original request-level data."""

import json, math, pathlib, statistics, sys

root = pathlib.Path(sys.argv[1])
raw = [json.loads(x) for x in (root / "service-raw.jsonl").read_text().splitlines()]


def pct(xs, q):
    return sorted(xs)[max(0, math.ceil(len(xs) * q) - 1)]


summary = []
for c in sorted({r["concurrency"] for r in raw}):
    runs = [r for r in raw if r["concurrency"] == c and not r["warmup"]]
    req = [q for r in runs for q in r["requests"]]
    # SGLang doesn't expose first-token time in the response. Prefill completion minus dispatch-finished
    # is the closest server-side first-token proxy; label it explicitly, not as exact TTFT.
    prefill = [
        1000
        * (
            q["meta"]["prefill_finished_time"]
            - q["meta"]["api_server_dispatch_finish_ts"]
        )
        for q in req
    ]
    tpot = [1000 / q["meta"]["decode_throughput"] for q in req]
    e2e = [1000 * q["meta"]["e2e_latency"] for q in req]
    wall = [1000 * q["wall_s"] for q in req]
    summary.append(
        {
            "concurrency": c,
            "successful_requests": len(req),
            "requests_all_256": all(q["output_tokens"] == 256 for q in req),
            "trial_aggregate_output_tps": [r["aggregate_output_tps"] for r in runs],
            "mean_aggregate_output_tps": statistics.mean(
                r["aggregate_output_tps"] for r in runs
            ),
            "sample_sd_tps": statistics.stdev(r["aggregate_output_tps"] for r in runs),
            "prefill_done_minus_dispatch_ms_p50_p95": [
                pct(prefill, 0.5),
                pct(prefill, 0.95),
            ],
            "decode_tpot_ms_p50_p95": [pct(tpot, 0.5), pct(tpot, 0.95)],
            "server_e2e_ms_p50_p95": [pct(e2e, 0.5), pct(e2e, 0.95)],
            "client_wall_ms_p50_p95": [pct(wall, 0.5), pct(wall, 0.95)],
        }
    )
(root / "service-summary-recomputed.json").write_text(
    json.dumps(summary, indent=2) + "\n"
)
print(json.dumps(summary, indent=2))
