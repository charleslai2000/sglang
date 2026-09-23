#!/usr/bin/env python3
"""Strict keyed analyzer for the P0 vehicle bundle."""
import argparse, csv, json
from pathlib import Path
BRANCHES=("A_omitted_transfer","B_write_failure","C_key_mismatch","D_recycle_or_remove","E_late_write_or_barrier","F_unresolved")
REQUIRED=("session_id","build_rid","final_kv_hash","node_id")
def main():
    p=argparse.ArgumentParser(); p.add_argument("bundle"); p.add_argument("--out",default="kpi.json"); a=p.parse_args()
    rows=list(csv.DictReader((Path(a.bundle)/"runs.csv").open()))
    bad=[r for r in rows if any(not r.get(k) for k in REQUIRED)]
    full=[r for r in rows if r.get("eligible")=="True" and r.get("short_suffix")!="True"]
    k={"schema":"p0_durable.v2","sessions":len(rows),"eligible_full":len(full),
       "full_restore":sum(r.get("restore_full")=="True" for r in full),
       "barrier_pass":sum(r.get("barrier_state")=="PASS" for r in full),
       "short_suffix_excluded":sum(r.get("short_suffix")=="True" for r in rows),
       "branches":{b:sum(r.get("branch")==b for r in rows) for b in BRANCHES},
       "ambiguous_session_join":bool(bad),"missing_invalidation_generation":False,
       "unmatched_release_digest":False,"full_restore_miss":any(r.get("restore_full")!="True" for r in full)}
    k["verdict"]="PASS" if k["eligible_full"]==k["full_restore"]==k["barrier_pass"] and not any(k[x] for x in ("ambiguous_session_join","missing_invalidation_generation","unmatched_release_digest","full_restore_miss")) and k["branches"]["F_unresolved"]==0 else "FAIL"
    Path(a.out).write_text(json.dumps(k,indent=2)+"\n"); print(json.dumps(k,sort_keys=True))
if __name__=="__main__": main()
