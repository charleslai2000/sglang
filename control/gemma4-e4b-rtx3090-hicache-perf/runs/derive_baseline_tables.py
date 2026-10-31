#!/usr/bin/env python3
"""Emit concise service and real-Graph Forward tables from immutable raw artifacts."""

import glob, json, math, pathlib, sys

base = pathlib.Path(sys.argv[1])
raw = [json.loads(l) for l in (base / "service-raw.jsonl").read_text().splitlines()]


def pct(x, p):
    return sorted(x)[max(0, math.ceil(len(x) * p) - 1)]


print(
    "| Client C | requests | service tok/s mean ± SD | prefill-complete minus dispatch P50/P95 ms* | TPOT P50/P95 ms | server E2E P50/P95 s | client wall P50/P95 s |"
)
print("|---:|---:|---:|---:|---:|---:|---:|")
for c in sorted({r["concurrency"] for r in raw}):
    runs = [r for r in raw if r["concurrency"] == c and not r["warmup"]]
    q = [x for r in runs for x in r["requests"]]
    pre = [
        1000
        * (
            x["meta"]["prefill_finished_time"]
            - x["meta"]["api_server_dispatch_finish_ts"]
        )
        for x in q
    ]
    tp = [1000 / x["meta"]["decode_throughput"] for x in q]
    e = [1000 * x["meta"]["e2e_latency"] for x in q]
    w = [1000 * x["wall_s"] for x in q]
    print(
        f"| {c} | {len(q)} | {sum(r['aggregate_output_tps'] for r in runs) / len(runs):.2f} ± {__import__('statistics').stdev(r['aggregate_output_tps'] for r in runs):.2f} | {pct(pre, 0.5):.1f}/{pct(pre, 0.95):.1f} | {pct(tp, 0.5):.2f}/{pct(tp, 0.95):.2f} | {pct(e, 0.5) / 1000:.3f}/{pct(e, 0.95) / 1000:.3f} | {pct(w, 0.5) / 1000:.3f}/{pct(w, 0.95) / 1000:.3f} |"
    )
print(
    "\n| Decode batch | graph replay | CUDA event P50/P95/mean ms | Aggregate tok/s at mean |"
)
print("|---:|:---:|---:|---:|")
for f in sorted(
    glob.glob(str(base.parent / "20261031T-gemma4-offline-decode-batches" / "b*.json")),
    key=lambda p: int(pathlib.Path(p).stem[1:]),
):
    x = json.load(open(f))
    v = x["cuda_event_ms"]
    print(
        f"| {x['batch']} | {x['graph_replay']} {x['graph_identity']} | {pct(v, 0.5):.3f}/{pct(v, 0.95):.3f}/{sum(v) / len(v):.3f} | {x['theoretical_aggregate_decode_tps']:.1f} |"
    )
