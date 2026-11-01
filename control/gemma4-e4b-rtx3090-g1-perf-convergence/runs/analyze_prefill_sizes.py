#!/usr/bin/env python3
"""Join request-scoped device timer records to individual Prefill RIDs."""

import json, pathlib, sqlite3, sys

run = pathlib.Path(sys.argv[1])
data = json.load(open(run / "prefill-sizes.json"))
c = sqlite3.connect(run / "profile.sqlite")
# This project Nsight version exports CUDA activity to CUDA_GRAPH_EVENTS rather
# than CUPTI_ACTIVITY_KIND_KERNEL for graph replays. Eager prefills are located
# by the request-linked RADIX8K_GPU_FORWARD host log plus CUDA Event timing.
for rec in data:
    rid = rec["meta"]["id"].removesuffix("_0")
    rows = c.execute(
        "select start,end,category from NVTX_EVENTS where text like ? and end>start",
        (f"%{rid}%",),
    ).fetchall()
    print(json.dumps({"rid": rid, "tokens": rec["tokens"], "nvtx": rows}))
