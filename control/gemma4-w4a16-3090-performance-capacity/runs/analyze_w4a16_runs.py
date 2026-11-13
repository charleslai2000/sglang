#!/usr/bin/env python3
"""Summarize archived W4A16 run with truthful dispatch-batch/runtime evidence."""

import json, re, statistics, sys
from pathlib import Path

out = Path(sys.argv[1])
summary = json.loads((out / "service-summary.json").read_text())
rows = []
for x in summary:
    rows.append(
        {
            "client_concurrency": x["concurrency"],
            "mean_tps": round(x["mean_tps"], 2),
            "sd_tps": round(x["sd_tps"], 2),
            "requests": x["successful_requests"],
            "server_e2e_p50_p95_s": x["server_e2e_s"],
            "api_tpot_p50_p95_s": x["tpot_s"],
        }
    )
log = (out / "server.log").read_text(errors="replace")
counts = {
    int(b): len(re.findall(rf"ScheduleBatch.*?batch_size={b}(?:[, )]|$)", log))
    for b in [1, 2, 4, 8, 12, 16, 24, 32]
}
# Parse common SGLang scheduler log variants, retaining raw matching lines too.
lines = [
    x
    for x in log.splitlines()
    if "ScheduleBatch" in x and ("batch_size" in x or "bs=" in x)
]
(out / "scheduler-decode-evidence.txt").write_text("\n".join(lines) + "\n")
manifest = (out / "manifest.txt").read_text()
result = {
    "run": str(out),
    "mode": "W4A16-real-service-performance",
    "online_matrix": rows,
    "scheduler_decode_log_lines": len(lines),
    "scheduler_batch_size_pattern_counts": counts,
    "model_info": json.loads((out / "model-info.json").read_text()),
    "manifest": manifest,
}
(out / "measured-summary.json").write_text(json.dumps(result, indent=2) + "\n")
print(
    json.dumps(
        {
            "run": str(out),
            "matrix": rows,
            "scheduler_lines": len(lines),
            "batch_pattern_counts": counts,
        },
        indent=2,
    )
)
