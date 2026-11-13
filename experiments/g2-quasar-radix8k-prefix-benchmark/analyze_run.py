#!/usr/bin/env python3
"""Summarize client rounds against per-request Scheduler evidence."""

import argparse, json, re, statistics
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument("run_dir", type=Path)
p.add_argument("--records", nargs="+", type=Path, required=True)
a = p.parse_args()
d = a.run_dir
records = [r for f in a.records for r in json.loads(f.read_text())]
lines = (d / "server.log").read_text(errors="replace").splitlines()
bad = []
summary = []
for c in sorted({r["concurrency"] for r in records}):
    rr = [r for r in records if r["concurrency"] == c and not r["warmup"]]
    req = [x for r in rr for x in r["requests"]]
    summary.append(
        {
            "concurrency": c,
            "mean_total_output_tps": statistics.mean(
                r["aggregate_output_tps"] for r in rr
            ),
            "sd_total_output_tps": statistics.stdev(
                r["aggregate_output_tps"] for r in rr
            ),
            "ttft_mean_s": statistics.mean(
                x["ttft_s"] for x in req if x["ttft_s"] is not None
            ),
            "request_e2e_p50_s": statistics.median(
                x["e2e_s"] for x in req if x["e2e_s"] is not None
            ),
            "requests": len(req),
        }
    )
for r in records:
    for x in r["requests"]:
        if x["cached_tokens"] != 7168 or x["output_tokens"] != 256:
            bad.append([x["rid"], "client cache/output mismatch"])
# Parse IDs robustly despite server-side tokenizer RID suffixes such as _0.
stats = {}
for s in lines:
    if "ReqTimeStats" not in s:
        continue
    m = re.search(r"rid=(radix8k-perf-c\d+-r\d+-i\d+)(?:_\d+)?", s)
    if m:
        stats[m.group(1)] = s
for r in records:
    for x in r["requests"]:
        base_rid = re.sub(r"_\d+$", "", x["rid"])
        s = stats.get(base_rid)
        if not s:
            bad.append([x["rid"], "missing server ReqTimeStats"])
            continue
        for pat in (r"input_len=8192", r"cached_input_len=7168", r"output_len=256"):
            if not re.search(pat, s):
                bad.append([x["rid"], "missing " + pat])
        if not re.search(r"ReqTimeStats\(rid=" + re.escape(x["rid"]) + r",", s):
            bad.append([x["rid"], "server ReqTimeStats RID normalization mismatch"])
# Link scheduler sample timestamps to each client wave, and verify actual concurrency + CUDA Graph.
batchlines = []
for s in lines:
    if "Decode batch, #running-req:" not in s:
        continue
    m = re.search(r"#running-req: (\d+).*?cuda graph: (True|False)", s)
    t = re.search(r"\[(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)\]", s)
    if m and t:
        batchlines.append((t.group(1), int(m[1]), m[2] == "True"))
checks = {}
for r in records:
    c, idx = r["concurrency"], r["round"]
    members = [x for x in r["requests"]]
    if not members:
        continue
    # A wave lasts roughly its client wall time; server lines in that interval must exhibit exact running batch and Graph.
    start = min(x["meta"]["request_received_ts"] for x in members)
    end = max(x["meta"]["request_finished_ts"] for x in members)
    from datetime import datetime, timezone

    def ts(x):
        return datetime.fromtimestamp(x, timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    lo, hi = ts(start), ts(end)
    samples = [(n, g) for t, n, g in batchlines if lo <= t <= hi]
    exact = sum(n == c for n, g in samples)
    graph = sum(n == c and g for n, g in samples)
    key = f"c{c}-r{idx}"
    checks[key] = {
        "running_batch_samples": exact,
        "graph_true_samples": graph,
        "samples_in_wave": len(samples),
    }
    if not exact:
        bad.append([key, "no exact Scheduler running batch in timestamp window"])
    if graph != exact:
        bad.append(
            [key, "Decode CUDA Graph not true for every exact-batch scheduler sample"]
        )
# Only requests from included records are relevant; excluded/incomplete runs never enter records.
result = {
    "client_summary": summary,
    "verified_scheduler_reqtime_rids": len(stats),
    "decode_samples_in_log": len(batchlines),
    "batch_graph_by_wave": checks,
    "validation_errors": bad,
    "all_included_waves_pass": not bad,
}
(d / "online-summary.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps(result, indent=2))
