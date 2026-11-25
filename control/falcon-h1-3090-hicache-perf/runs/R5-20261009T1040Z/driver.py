#!/usr/bin/env python3
"""Deterministic Falcon target L2 lifecycle driver. All API traffic is loopback."""
import hashlib, json, time
from pathlib import Path
import requests
from transformers import AutoTokenizer

BASE = "http://127.0.0.1:30127"
OUT = Path(__file__).resolve().parent
TARGET_SESSION = "falcon-r5-target-session-9001"
COMPETITOR_SESSION_PREFIX = "falcon-r5-competitor-"
MODEL = "/data/models/Falcon-H1-7B-Instruct-GPTQ-Int4"
TOK = AutoTokenizer.from_pretrained(MODEL, trust_remote_code=True)
S = requests.Session()

def tokenize(text, length):
    ids = TOK.encode(text, add_special_tokens=False)
    if len(ids) < length: raise RuntimeError(f"need {length}, got {len(ids)}")
    return ids[:length]

# Target prefix is unique and exactly 1920 tokens (< 2048 chunk threshold).
TARGET = tokenize("R5 session-9001 unique sentinel: " + "blue copper river lantern meadow " * 1000, 1920)
assert len(TARGET) == 1920

def metric_values():
    text=S.get(BASE+"/metrics",timeout=20).text
    result={}
    for line in text.splitlines():
        if line.startswith("#") or "falcon-h1-r5" not in line: continue
        try:
            name_labels,value=line.split(None,1); value=float(value)
        except Exception: continue
        if name_labels.startswith("sglang:prefill_effective_tokens_total"):
            mode=name_labels.split('mode="',1)[1].split('"',1)[0] if 'mode="' in name_labels else "unknown"
            result[f"prefill_{mode}"]=value
        elif name_labels.startswith("sglang:load_back_tokens_total"):
            pool=name_labels.split('pool="',1)[1].split('"',1)[0] if 'pool="' in name_labels else "unknown"
            result[f"load_back_{pool}"]=value
        elif name_labels.startswith("sglang:backuped_tokens_total"):
            result["l3_backup"]=value
        elif name_labels.startswith("sglang:prefetched_tokens_total"):
            result["l3_prefetch"]=value
    return result

def request(ids, tag, new_tokens=24, session_id=None):
    before=metric_values()
    started=time.perf_counter()
    payload={"input_ids":ids,
        "sampling_params":{"temperature":0,"max_new_tokens":new_tokens,"ignore_eos":True},
        "return_cached_tokens_details":True}
    if session_id is not None: payload["session_id"]=session_id
    r=S.post(BASE+"/generate",json=payload,timeout=300)
    r.raise_for_status(); data=r.json()
    if "error" in data: raise RuntimeError(data)
    meta=data.get("meta_info",{})
    row={"tag":tag,"session_id":session_id,"prompt_tokens":meta.get("prompt_tokens"),"completion_tokens":meta.get("completion_tokens"),
         "cached_tokens":meta.get("cached_tokens"),"cached_tokens_details":meta.get("cached_tokens_details"),
         "output_ids":data.get("output_ids"),"elapsed_s":time.perf_counter()-started,
         "metrics_before":before,"metrics_after":metric_values(),
         "prompt_sha256":hashlib.sha256(json.dumps(ids).encode()).hexdigest()}
    with (OUT/"requests.jsonl").open("a") as f:f.write(json.dumps(row)+"\n")
    print(json.dumps({k:v for k,v in row.items() if k!="output_ids"}),flush=True)
    return row

def target_trace_state():
    trace=OUT/"t38c-probe.jsonl"
    if not trace.exists(): return None, []
    target_node=None; rows=[]
    with trace.open() as f:
        for line in f:
            try: row=json.loads(line)
            except Exception: continue
            if row.get("session_id")==TARGET_SESSION:
                rows.append(row)
                if row.get("evt")=="build_complete" and row.get("result") is True:
                    target_node=str(row.get("node_id"))
    return target_node,rows

def metrics(tag):
    text=S.get(BASE+"/metrics",timeout=20).text
    names=("prefill_effective_tokens_total","hicache_host_used_tokens","hicache_host_total_tokens",
           "hicache_mamba_host_usable_tokens","hicache_backup_tokens_total","load_back_tokens_total",
           "load_back_bytes_total","evicted_tokens_total","hicache_dropped_tokens_total",
           "backuped_tokens_total","prefetched_tokens_total")
    lines=[x for x in text.splitlines() if not x.startswith("#") and any(n in x for n in names)]
    (OUT/f"{tag}.metrics").write_text("\n".join(lines)+"\n")
    print(f"SNAPSHOT {tag}\n"+"\n".join(lines),flush=True)

def main():
    print("target_len",len(TARGET),"mamba_checkpoint_grid",256,
          "target_sha256",hashlib.sha256(json.dumps(TARGET).encode()).hexdigest(),flush=True)
    metrics("baseline")
    # Native Session-Aware Radix path (top-level session_id only). This uses
    # scheduler generation and the UnifiedRadixCache-owned prefix lifecycle;
    # no SessionController open_session or session_params reconstruction.
    reference=request(TARGET,"target_A",new_tokens=0,session_id=TARGET_SESSION)
    repeated=request(TARGET,"target_A_repeat",new_tokens=0,session_id=TARGET_SESSION)
    # Prefill-only requests have no generated tail; revisit exactly the same IDs.
    TARGET_CONTEXT=TARGET
    if reference["output_ids"]!=repeated["output_ids"]:raise RuntimeError("target greedy IDs differ")
    if reference["output_ids"] or repeated["output_ids"]:
        raise RuntimeError("prefill-only target must emit no decode tokens")
    close_target=S.post(BASE+"/close_session",json={"session_id":TARGET_SESSION},timeout=30)
    close_target.raise_for_status()
    metrics("after_target_A")
    target_node, trace_rows=target_trace_state()
    target_hash=next((r.get("final_kv_hash") for r in trace_rows
                      if r.get("evt")=="build_complete" and str(r.get("node_id"))==target_node),None)
    if not target_node or not target_hash:
        raise RuntimeError("no target-correlated build_complete node/hash; stop before pressure")
    if not any(r.get("evt")=="backup_host_commit" and str(r.get("node_id"))==target_node
               and r.get("final_kv_hash")==target_hash and r.get("kv_transfer") and r.get("mamba_transfer")
               for r in trace_rows):
        raise RuntimeError("target FULL+MAMBA D2H commit absent; stop before pressure")
    print("TARGET_BUILD_AND_BACKUP_CONFIRMED",target_node,target_hash,flush=True)
    # Target session stays open so T38C can correlate node/hash/residency.
    # Competitor radix sessions are individually released after their request.
    # Distinct unchunked competitors, never revisit/extend target. Stop as soon
    # as marker trace proves both target device layers detached and host layers
    # remain. Occupancy is a bound/corroboration, not node attribution.
    for i in range(256):
        ids=tokenize(f"R5 competitor-{i:04d} unique: "+f"case{i:04d} azure cedar orbit violet meadow "*500,1920)
        competitor_id=f"{COMPETITOR_SESSION_PREFIX}{i:04d}"
        request(ids,f"competitor_{i:03d}",new_tokens=8,session_id=competitor_id)
        close_comp=S.post(BASE+"/close_session",json={"session_id":competitor_id},timeout=30)
        close_comp.raise_for_status()
        if (i+1)%8==0:
            metrics(f"pressure_{i+1:03d}")
            snap=(OUT/f"pressure_{i+1:03d}.metrics").read_text()
            used=total=evicted=0.0
            for line in snap.splitlines():
                if "hicache_host_used_tokens" in line and 'model_name="falcon-h1-r5"' in line:used=float(line.split()[-1])
                elif "hicache_host_total_tokens" in line and 'model_name="falcon-h1-r5"' in line:total=float(line.split()[-1])
                elif "evicted_tokens_total" in line:evicted=max(evicted,float(line.split()[-1]))
            node_now,rows=target_trace_state()
            target_rows=[r for r in rows if str(r.get("node_id"))==target_node
                         and r.get("final_kv_hash")==target_hash]
            cold=any(r.get("evt")=="residency_barrier" and r.get("cold_residency") is True
                     and r.get("snapshot_complete") is True
                     and all(not tier.get("device_present") and tier.get("host_present")
                             for tier in r.get("component_tiers",[])
                             if tier.get("component") in ("FULL","MAMBA"))
                     for r in target_rows)
            if cold:
                print("STOP_TARGET_COLD",i+1,"target_node",target_node,"host_used",used,
                      "host_capacity",total,"evicted",evicted,flush=True)
                break
            if total and used>=0.70*total and evicted>0:
                raise RuntimeError("target not proven cold by 70% measured host occupancy; stop, do not continue pressure")
    node_now,rows=target_trace_state()
    target_rows=[r for r in rows if str(r.get("node_id"))==target_node and r.get("final_kv_hash")==target_hash]
    if not any(r.get("evt")=="residency_barrier" and r.get("cold_residency") is True for r in target_rows):
        raise RuntimeError("bounded pressure ended without target device-absent/host-present proof; do not revisit")
    metrics("before_target_revisit")
    restored=request(TARGET_CONTEXT,"target_B",session_id=None)
    print("GREEDY_EQUAL",reference["output_ids"]==restored["output_ids"],flush=True)
    metrics("after_target_B")
    before=restored["metrics_before"]; after=restored["metrics_after"]
    deltas={key:after.get(key,0)-before.get(key,0) for key in sorted(set(before)|set(after))}
    print("TARGET_REQUEST_COUNTER_DELTAS",json.dumps(deltas,sort_keys=True),flush=True)
    if restored.get("cached_tokens_details") is not None:
        print("TARGET_RESPONSE_CACHE_DETAILS",json.dumps(restored["cached_tokens_details"]),flush=True)
    _,rows=target_trace_state()
    target_rows=[r for r in rows if str(r.get("node_id"))==target_node and r.get("final_kv_hash")==target_hash]
    restored_snapshot=any(r.get("evt")=="residency_snapshot" and
        all(t.get("device_present") and t.get("host_present") for t in r.get("component_tiers",[])
            if t.get("component") in ("FULL","MAMBA")) for r in target_rows)
    print("TARGET_POST_RESTORE_SNAPSHOT",restored_snapshot,"TARGET_NODE",target_node,
          "TARGET_HASH",target_hash,flush=True)
    if reference["output_ids"]!=restored["output_ids"]:
        raise RuntimeError("target greedy outputs differ after restore")

if __name__=="__main__":main()
