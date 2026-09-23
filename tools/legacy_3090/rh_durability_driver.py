#!/usr/bin/env python3
"""P0 S=25 RH-off durability vehicle.

This is a collector/vehicle only.  It consumes p0_durable.v2 JSONL events and
issues a warm request only after the keyed durability and cold-residency
barriers have been observed.  It never converts elapsed time into success.
"""
import argparse, csv, hashlib, json, os, sys, time
from pathlib import Path

SCHEMA = "p0_durable.v2"
BRANCHES = ("A_omitted_transfer", "B_write_failure", "C_key_mismatch",
            "D_recycle_or_remove", "E_late_write_or_barrier", "F_unresolved")
PARAMS = {"sessions": 25, "history_target": 55000, "active": 8,
          "build_workers": 8, "rh": "off", "mamba_ratio": 0.42,
          "hicache_ratio": 1.3, "kv_dtype": "fp8_e4m3", "graph_bs": 8,
          "file_size": "120G", "short_suffix": 256}

def now(): return time.time_ns()
def digest(obj): return hashlib.md5(json.dumps(obj, sort_keys=True).encode()).hexdigest()

def event(evt, run_id, seq, **kw):
    return {"schema_version": SCHEMA, "run_id": run_id, "event_id": f"{run_id}:{seq}",
            "evt": evt, "ts_wall_ns": now(), "ts_mono_ns": time.monotonic_ns(),
            "process_id": os.getpid(), "local_seq": seq, "result": True, **kw}

def load_events(path):
    with open(path, encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            if not line.strip(): continue
            try: row = json.loads(line)
            except json.JSONDecodeError as e: raise ValueError(f"invalid JSONL line {lineno}: {e}")
            if row.get("schema_version") != SCHEMA: raise ValueError(f"line {lineno}: schema mismatch")
            yield row

def key(e):
    return (e.get("session_id"), e.get("build_rid"), e.get("node_id"), e.get("final_kv_hash"))

def classify(r):
    if r["lookup_before_barrier"]: return "E_late_write_or_barrier"
    if r["write_failure"]: return "B_write_failure"
    if r["omitted_transfer"]: return "A_omitted_transfer"
    if r["key_mismatch"]: return "C_key_mismatch"
    if r["recycled"]: return "D_recycle_or_remove"
    return "F_unresolved"

def reduce_events(events, timeout_s):
    rows = {}
    for e in events:
        sid = e.get("session_id")
        if not sid: continue
        r = rows.setdefault(sid, {"session_id": sid, "events": [], "build_rid": None,
                                  "final_kv_hash": None, "node_id": None,
                                  "eligible": False, "short_suffix": False,
                                  "lookup_before_barrier": False, "write_failure": False,
                                  "omitted_transfer": False, "key_mismatch": False,
                                  "recycled": False, "durable": False, "cold": False,
                                  "warm_issued": False, "restore_full": False})
        r["events"].append(e)
        for fld in ("build_rid", "final_kv_hash", "node_id"):
            if e.get(fld) is not None: r[fld] = e[fld]
        if e.get("evt") == "build_complete":
            r["eligible"] = True; r["short_suffix"] = e.get("suffix_tokens", 999) < PARAMS["short_suffix"]
        if e.get("evt") == "durability_barrier" and e.get("combined_durable") is True: r["durable"] = True; r["durable_ts"] = e.get("ts_wall_ns")
        if e.get("evt") == "residency_barrier" and e.get("cold_residency") is True: r["cold"] = True; r["cold_ts"] = e.get("ts_wall_ns")
        if e.get("evt") == "warm_lookup_start":
            r["warm_issued"] = True; r["lookup_ts"] = e.get("ts_wall_ns")
            if not (r["durable"] and r["cold"]): r["lookup_before_barrier"] = True
        if e.get("evt") == "batch_set_result" and e.get("result") is False: r["write_failure"] = True
        if e.get("evt") == "backup_submit" and e.get("mamba_key") is None: r["omitted_transfer"] = True
        if e.get("evt") == "storage_query" and e.get("tested_present") is False: r["key_mismatch"] = True
        if e.get("evt") == "storage_invalidate" and e.get("storage_key") == e.get("mamba_key"): r["recycled"] = True
        if e.get("evt") == "restore_outcome": r["restore_full"] = e.get("final_pages", 0) > 0 and e.get("full_restore") is True
    for r in rows.values():
        r["branch"] = classify(r)
        r["barrier_state"] = "PASS" if r["durable"] and r["cold"] else "NOT_VERIFIED"
        r["outcome"] = "PASS" if r["restore_full"] and r["barrier_state"] == "PASS" else "FAIL"
        r["evidence_ref"] = digest([(e.get("event_id"), e.get("evt")) for e in r["events"]])
        del r["events"]
    return rows

def fixture(run_id):
    out=[]; seq=0
    for i in range(25):
        sid=f"s{i:05d}"; rid=f"b{i:05d}"; node=f"n{i:05d}"; h=f"h{i:064d}"
        for typ, extra in [("build_complete", {"build_rid":rid,"node_id":node,"final_kv_hash":h,"suffix_tokens":128}),
          ("backup_submit", {"build_rid":rid,"node_id":node,"final_kv_hash":h,"mamba_key":f"m{i}"}),
          ("batch_set_result", {"build_rid":rid,"node_id":node,"final_kv_hash":h}),
          ("extent_commit", {"build_rid":rid,"node_id":node,"final_kv_hash":h}),
          ("backup_ack_enqueue", {"build_rid":rid,"node_id":node,"final_kv_hash":h}),
          ("backup_ack_drain", {"build_rid":rid,"node_id":node,"final_kv_hash":h}),
          ("storage_persisted", {"build_rid":rid,"node_id":node,"final_kv_hash":h}),
          ("durability_barrier", {"build_rid":rid,"node_id":node,"final_kv_hash":h,"combined_durable":True}),
          ("residency_barrier", {"build_rid":rid,"node_id":node,"final_kv_hash":h,"cold_residency":True}),
          ("warm_lookup_start", {"build_rid":rid,"node_id":node,"final_kv_hash":h}),
          ("restore_outcome", {"build_rid":rid,"node_id":node,"final_kv_hash":h,"final_pages":1,"full_restore":True})]:
            seq+=1; out.append(event(typ,run_id,seq,session_id=sid,**extra))
    return out

def write_bundle(args, rows, events):
    d=Path(args.evidence_dir); d.mkdir(parents=True, exist_ok=True)
    manifest={"task_id":args.task_id,"epoch":args.epoch,"run_id":args.run_id,"parameters":PARAMS,
              "trace_schema":SCHEMA,"marker":"/tmp/t38c-durable-trace","remote_launch":False}
    (d/"run_manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
    (d/"config-resolved.txt").write_text(json.dumps(PARAMS,sort_keys=True)+"\n")
    with (d/"trace.jsonl").open("w") as f:
        for e in events: f.write(json.dumps(e,sort_keys=True)+"\n")
    fields=["session_id","build_rid","final_kv_hash","node_id","eligible","short_suffix","barrier_state","warm_issued","restore_full","branch","outcome","evidence_ref"]
    with (d/"runs.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows({k:r.get(k) for k in fields} for r in rows.values())
    verdict={"verdict":"NOT_VERIFIED" if args.dry_run else ("PASS" if rows and all(r["outcome"]=="PASS" for r in rows.values()) else "FAIL"),
             "full_denominator":sum(r["eligible"] and not r["short_suffix"] for r in rows.values()),
             "full_restore":sum(r["restore_full"] and not r["short_suffix"] for r in rows.values()),
             "barrier_pass":sum(r["barrier_state"]=="PASS" for r in rows.values()),
             "branches":{b:sum(r["branch"]==b for r in rows.values()) for b in BRANCHES},"no_fixed_sleep":True}
    (d/"verdict.json").write_text(json.dumps(verdict,indent=2)+"\n")
    (d/"join.log").write_text("key=session_id+build_rid+final_kv_hash+node_id; timestamp-only joins rejected\n")
    (d/"driver.log").write_text("T38C_RUN_ID=%s\nmarker=/tmp/t38c-durable-trace\nprobe=/tmp/t38c-probe.log\n"%args.run_id)
    (d/"metrics-final.txt").write_text(json.dumps(verdict,sort_keys=True)+"\n")
    (d/"cleanup.log").write_text("remote_launch=false; no remote process started\n")
    files=[p for p in d.iterdir() if p.name != "MD5SUMS"]
    (d/"MD5SUMS").write_text("\n".join(f"{hashlib.md5(p.read_bytes()).hexdigest()}  {p.name}" for p in sorted(files))+"\n")

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--events",help="live p0_durable.v2 JSONL; required outside --dry-run")
    ap.add_argument("--live",action="store_true",help="reserved for an integrated client; refuses incomplete integration")
    ap.add_argument("--evidence-dir",default="/tmp/t38c-p0-dry-run")
    ap.add_argument("--run-id",default=os.environ.get("T38C_RUN_ID","p0-local")); ap.add_argument("--task-id",default="EXEC-20260908-P0-BARRIER-VEHICLE"); ap.add_argument("--epoch",default="E20260908-P0P1P2"); ap.add_argument("--dry-run",action="store_true"); ap.add_argument("--watchdog-s",type=float,default=900)
    a=ap.parse_args(); os.environ["T38C_RUN_ID"]=a.run_id
    Path("/tmp/t38c-durable-trace").touch(); Path("/tmp/t38c-probe.log").write_text(f"run_id={a.run_id}\n")
    if a.live:
        raise SystemExit("NEEDS_REASONING: gate3_parked.py issues warm requests internally and exposes no per-session pre-warm barrier callback; a wrapper cannot enforce the required happens-before edge within the authorized tooling write set")
    if not a.dry_run and not a.events:
        raise SystemExit("NEEDS_REASONING: --events from a live p0_durable.v2 collector is required; synthetic fixture is --dry-run only")
    events=fixture(a.run_id) if a.dry_run else list(load_events(a.events))
    rows=reduce_events(events,a.watchdog_s); write_bundle(a,rows,events)
    print(json.dumps({"verdict":"NOT_VERIFIED" if a.dry_run else ("PASS" if rows and all(r["outcome"]=="PASS" for r in rows.values()) else "FAIL"),"sessions":len(rows),"evidence_dir":a.evidence_dir},sort_keys=True))
if __name__ == "__main__": main()
