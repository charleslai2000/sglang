#!/usr/bin/env python3
from pathlib import Path
import json, re, statistics, sys

p = Path(sys.argv[1])
lines = (p / "server.log").read_text(errors="replace").splitlines()
dec = []
pre = []
rx = re.compile(
    r"Decode batch, #running-req: (\d+), #full token: (\d+), full token usage: ([0-9.]+), #swa token: (\d+), swa token usage: ([0-9.]+).*gen throughput \(token/s\): ([0-9.]+), #queue-req: (\d+)"
)
for i, l in enumerate(lines):
    if "Decode batch" in l:
        m = rx.search(l)
        if m:
            dec.append(
                {
                    "line": i + 1,
                    "running": int(m.group(1)),
                    "full_tokens": int(m.group(2)),
                    "full_usage": float(m.group(3)),
                    "swa_tokens": int(m.group(4)),
                    "swa_usage": float(m.group(5)),
                    "decode_tps": float(m.group(6)),
                    "queue": int(m.group(7)),
                    "log": l,
                }
            )
    if "Prefill batch" in l:
        m = re.search(
            r"Prefill batch, #new-seq: (\d+), #new-token: (\d+), #cached-token: (\d+).*#running-req: (\d+), #queue-req: (\d+).*input throughput \(token/s\): ([0-9.]+)",
            l,
        )
        if m:
            pre.append(
                {
                    "line": i + 1,
                    "new_seq": int(m.group(1)),
                    "new_tokens": int(m.group(2)),
                    "cached_tokens": int(m.group(3)),
                    "running": int(m.group(4)),
                    "queue": int(m.group(5)),
                    "input_tps": float(m.group(6)),
                    "log": l,
                }
            )
(p / "decode-batches.json").write_text(json.dumps(dec, indent=2) + "\n")
(p / "prefill-batches.json").write_text(json.dumps(pre, indent=2) + "\n")
result = {
    "decode_batch_count": len(dec),
    "peak_running_decode": max((x["running"] for x in dec), default=0),
    "decode_rows_running32": sum(x["running"] == 32 for x in dec),
    "decode_tps_max": max((x["decode_tps"] for x in dec), default=None),
    "decode_tps_median": statistics.median([x["decode_tps"] for x in dec])
    if dec
    else None,
    "peak_prefill_running": max((x["running"] for x in pre), default=0),
    "prefill_rows_cached_tokens_zero": sum(x["cached_tokens"] == 0 for x in pre),
    "prefill_batches": len(pre),
}
(p / "server-analysis.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps(result, indent=2))
