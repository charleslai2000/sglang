#!/usr/bin/env python3
"""Join scheduler NVTX forward steps to CUDA Graph launches and GPU replay events."""

import argparse, json, pathlib, sqlite3, statistics

p = argparse.ArgumentParser()
p.add_argument("run_dir", type=pathlib.Path)
p.add_argument("--batch", type=int, required=True)
p.add_argument("--kind", choices=["decode", "prefill"], default="decode")
a = p.parse_args()
r = a.run_dir
db = sqlite3.connect(r / "profile.sqlite")
names = dict(db.execute("select id,value from StringIds"))
labels = db.execute(
    "select n.start,n.end,s.value,n.globalTid from NVTX_EVENTS n join StringIds s on n.textId=s.id where n.end is not null and s.value like 'RADIX8K_FWD step=%'"
).fetchall()
rt = db.execute(
    "select start,end,correlationId,globalTid,nameId from CUPTI_ACTIVITY_KIND_RUNTIME where nameId in (select id from StringIds where value like 'cudaGraphLaunch%')"
).fetchall()
graph = db.execute(
    "select start,end,correlationId,globalPid from CUPTI_ACTIVITY_KIND_GRAPH_TRACE"
).fetchall()
bycorr = {cid: (s, e, pid) for s, e, cid, pid in graph}
mode = "DECODE" if a.kind == "decode" else "EXTEND"
prefix = f"radix8k-prof-{a.kind}-c{a.batch}-"
rows = []
ambiguous = []
for start, end, label, tid in labels:
    if (
        f"mode={mode}" not in label
        or f"batch={a.batch} " not in label
        or prefix not in label
    ):
        continue
    launch = [
        x for x in rt if x[3] == tid and start <= x[0] <= x[1] <= end and x[2] in bycorr
    ]
    if len(launch) != 1:
        ambiguous.append((label, len(launch)))
        continue
    ls, le, cid, _, _ = launch[0]
    gs, ge, gpid = bycorr[cid]
    # Scheduler NVTX is a host-side scope; graph execution is asynchronous. Keep both intervals separate.
    rows.append(
        {
            "step": int(label.split("step=")[1].split()[0]),
            "rids": [rid.removesuffix("_0") for rid in label.split("rids=", 1)[1].split(",")],
            "batch": a.batch,
            "graph_bucket": int(label.split("bucket=")[1].split()[0]),
            "nvtx_start_ns": start,
            "nvtx_end_ns": end,
            "launch_start_ns": ls,
            "launch_end_ns": le,
            "replay_start_ns": gs,
            "replay_end_ns": ge,
            "graph_correlation_id": cid,
            "scheduler_prelaunch_ms": (ls - start) / 1e6,
            "cuda_graph_api_ms": (le - ls) / 1e6,
            "api_to_replay_start_ms": (gs - le) / 1e6,
            "gpu_replay_ms": (ge - gs) / 1e6,
            "nvtx_end_minus_launch_end_ms": (end - le) / 1e6,
        }
    )
rows.sort(key=lambda x: x["step"])
if not rows:
    raise SystemExit(f"No unambiguous {mode} graph joins; ambiguous={len(ambiguous)}")
req = json.load(open(r / f"profile-{a.kind}-c{a.batch}.json"))
reqmap = {x["rid"]: x for x in req["requests"]}
for row in rows:
    row["request_count"] = len(row["rids"])
    row["request_records_present"] = sum(x in reqmap for x in row["rids"])
    if row["request_count"] != a.batch or row["request_records_present"] != a.batch:
        raise ValueError(f"RID evidence mismatch in step {row['step']}: {row['rids']}")
all_step_rids=[rid for row in rows for rid in row["rids"]]
if a.kind == "prefill":
    expected={rid for rid in reqmap}
    if set(all_step_rids) != expected or len(all_step_rids) != len(expected):
        raise ValueError("Prefill cohort RIDs are not a duplicate-free partition")
else:
    expected=set(reqmap)
    counts={rid:all_step_rids.count(rid) for rid in expected}
    if set(all_step_rids) != expected or len(counts)!=len(expected):
        raise ValueError("Decode step RIDs do not match response cohort")
    out_steps=len(next(iter(reqmap.values()))["meta"].get("completion_tokens",[]) if isinstance(next(iter(reqmap.values()))["meta"].get("completion_tokens"),list) else [])
    # Every sequence may legitimately appear at each decode step; 256 graph replays × batch is expected.
    if len(rows) != 256 or len(all_step_rids) != 256*a.batch:
        raise ValueError(f"Decode timeline is incomplete: {len(rows)} steps, {len(all_step_rids)} RID-step pairs")
# Aggregate same-run request intervals. Response fields are scheduler timestamps and leave queue/e2e gaps observable.
request_summary={}
for rid,record in reqmap.items():
    m=record["meta"]
    prefill=(m["prefill_finished_time"]-m["forward_entry_time"])*1000
    decode=(m["request_finished_ts"]-m["prefill_finished_time"])*1000
    request_summary[rid]={"queue_ms":m["queue_time"]*1000,"prefill_forward_ms":prefill,"post_prefill_to_finish_ms":decode,"decode_throughput_tps":m.get("decode_throughput"),"e2e_ms":m["e2e_latency"]*1000,"request_received_ts":m["request_received_ts"],"forward_entry_time":m["forward_entry_time"],"prefill_finished_time":m["prefill_finished_time"],"request_finished_ts":m["request_finished_ts"]}
# Preserve per-request and per-step records; do not assign batch graph time to individual RIDs.
out = {
    "run": str(r),
    "kind": a.kind,
    "batch": a.batch,
    "matched_steps": len(rows),
    "ambiguous_steps": ambiguous,
    "requests": len(reqmap),
    "step_request_pairs": sum(x["request_count"] for x in rows),
    "step_rows": rows,
    "request_summary": request_summary,
    "summary": {},
}
for k in [
    "scheduler_prelaunch_ms",
    "cuda_graph_api_ms",
    "api_to_replay_start_ms",
    "gpu_replay_ms",
    "nvtx_end_minus_launch_end_ms",
]:
    v = [x[k] for x in rows]
    out["summary"][k] = {
        "p50": statistics.median(v),
        "p95": sorted(v)[int(0.95 * (len(v) - 1))],
        "mean": statistics.mean(v),
    }
path = r / f"same-run-{a.kind}-timeline-b{a.batch}.json"
path.write_text(json.dumps(out, indent=2) + "\n")
print(
    json.dumps(
        {"output": str(path), "steps": len(rows), "summary": out["summary"]}, indent=2
    )
)
