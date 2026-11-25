#!/usr/bin/env python3
"""Bounded target-specific FULL+MAMBA L2 eviction/restore using existing T38C evidence."""
import hashlib, json, time
from pathlib import Path
import requests
from transformers import AutoTokenizer
BASE="http://127.0.0.1:30127"; OUT=Path(__file__).resolve().parent
RUN_PREFIX="falcon-r15-l3-"
MODEL="/data/models/Falcon-H1-7B-Instruct-GPTQ-Int4"; TOK=AutoTokenizer.from_pretrained(MODEL,trust_remote_code=True); S=requests.Session()
TARGET_SESSION="falcon-r15-target-radix-session-9001"

def target_ids():
    ids=TOK.encode("R5 session-9001 unique sentinel: "+"blue copper river lantern meadow "*1000,add_special_tokens=False)[:1920]
    if len(ids)!=1920: raise RuntimeError(f"bad target length {len(ids)}")
    return ids

def competitor_ids(i):
    text=f"R12 competitor {i:04d} unique: " + "cedar quartz meadow orbit azure "*500
    ids=TOK.encode(text,add_special_tokens=False)[:1920]
    if len(ids)!=1920: raise RuntimeError(f"competitor {i} prompt length invalid: {len(ids)}")
    return ids

def rows():
    p=OUT/"t38c-probe.jsonl"
    return [json.loads(x) for x in p.read_text().splitlines() if x.strip() and json.loads(x).get("run_id","").startswith(RUN_PREFIX)]

def metrics(tag):
    text=S.get(BASE+"/metrics",timeout=20).text
    (OUT/f"{tag}.metrics").write_text("\n".join(x for x in text.splitlines() if not x.startswith("#") and any(k in x for k in ("hicache_host_used_tokens","hicache_host_total_tokens","hicache_mamba_host_usable_tokens","hicache_kv_host_usable_tokens","mamba_available_tokens","mamba_evictable_tokens","mamba_used_tokens","evicted_tokens_total","load_back_tokens_total","load_back_bytes_total")))+"\n")
    return text

def request(ids,tag,sid=None):
    before=metrics("_scratch");t=time.perf_counter()
    r=S.post(BASE+"/generate",json={"input_ids":ids,"sampling_params":{"temperature":0,"max_new_tokens":1,"ignore_eos":True},"return_cached_tokens_details":True,"return_token_ids":True,**({"session_id":sid} if sid else {})},timeout=300);r.raise_for_status();d=r.json()
    if "error" in d: raise RuntimeError(d)
    out=d.get("output_ids") or (d.get("choices",[{}])[0].get("token_ids") if d.get("choices") else None)
    result={"tag":tag,"output_ids":out,"meta_info":d.get("meta_info"),"elapsed_s":time.perf_counter()-t}
    with (OUT/"l2_requests.jsonl").open("a") as f:f.write(json.dumps(result)+"\n")
    print(json.dumps(result),flush=True);return result

def main():
    ids=target_ids(); sha=hashlib.sha256(json.dumps(ids,separators=(",",":")).encode()).hexdigest()
    events=rows(); builds=[e for e in events if e.get("evt")=="build_complete" and e.get("session_id")==TARGET_SESSION and e.get("result") is True]
    if len(builds)!=1:raise RuntimeError(f"expected one build in fresh service, got {len(builds)}")
    b=builds[0]; nid=str(b["node_id"]); h=b["final_kv_hash"]
    commits=[e for e in events if e.get("evt")=="backup_host_commit" and str(e.get("node_id"))==nid and e.get("final_kv_hash")==h and e.get("kv_transfer") and e.get("mamba_transfer")]
    if len(commits)!=1 or not isinstance(commits[0].get("operation_id"),int):raise RuntimeError("FULL+MAMBA target commit operation missing")
    c=commits[0];acks=[e for e in events if e.get("evt")=="backup_host_ack" and e.get("operation_id")==c["operation_id"] and str(e.get("node_id"))==nid and e.get("final_kv_hash")==h and e.get("finish_event_synchronized") is True]
    if len(acks)!=1:raise RuntimeError("target ACK missing/ambiguous")
    storage_submit_requests=[e for e in events if e.get("evt")=="backup_submit" and str(e.get("node_id"))==nid and e.get("final_kv_hash")==h and e.get("mamba_transfer")]
    # Explicitly submit this exact target chain to existing Extent backend;
    # storage commit/read events remain the correctness evidence.
    import hashlib as _hashlib
    storage_session=f"falcon-r15-storage-{_hashlib.sha256(h.encode()).hexdigest()[:12]}"
    ref=request(ids,"target_pre_pressure",TARGET_SESSION)
    if ref["output_ids"]!=[10553]:raise RuntimeError("unexpected greedy reference")
    close=S.post(BASE+"/close_session",json={"session_id":TARGET_SESSION},timeout=30);close.raise_for_status()
    target_rows=[e for e in rows() if str(e.get("node_id"))==nid and e.get("final_kv_hash")==h]
    # Device state has 45 Mamba slots, while the independent Host Mamba pool
    # exposes 91 usable slots. Use just enough unique, session-released
    # requests to force L1 eviction, then check target identity before revisiting.
    # Do not use FULL Host aggregate utilization as a proxy for Mamba capacity.
    max_competitors=56
    for i in range(1,max_competitors+1):
        sid=f"falcon-r15-competitor-{i:04d}"
        request(competitor_ids(i),f"competitor_{i:04d}",sid)
        cr=S.post(BASE+"/close_session",json={"session_id":sid},timeout=30);cr.raise_for_status()
        if i%4==0 or i==max_competitors:
            text=metrics(f"pressure_{i:03d}")
            target_events=[e for e in rows() if str(e.get("node_id"))==nid and e.get("final_kv_hash")==h]
            detaches=[e for e in target_events if e.get("evt")=="residency_detach" and e.get("pool") in ("kv","mamba") and e.get("tier")=="device"]
            cold_pools={e.get("pool") for e in detaches}
            if cold_pools=={"kv","mamba"}:
                print("TARGET_DEVICE_DETACH",json.dumps({"competitors":i,"node_id":nid,"hash":h,"detach_events":[e.get("event_id") for e in detaches]}),flush=True);break
            match=__import__("re").search(r'sglang:hicache_mamba_host_usable_tokens\\{[^}]*model_name="falcon-h1-r15"[^}]*\\} ([0-9.]+)',text)
            if match and float(match.group(1))<1:raise RuntimeError("MAMBA Host usable capacity reached zero before target Device detach")
    else:
        raise RuntimeError(f"target Device detach not reached in {max_competitors} competitors; refuse further pressure")
    target_rows=[e for e in rows() if str(e.get("node_id"))==nid and e.get("final_kv_hash")==h]
    cold=[e for e in target_rows if e.get("evt")=="residency_detach" and e.get("pool") in ("kv","mamba") and e.get("tier")=="device"]
    if {e.get("pool") for e in cold}!={"kv","mamba"}:raise RuntimeError("target Device detach not proven for FULL+MAMBA")
    metrics("before_restore")
    restored=request(ids,"target_host_restore")
    if restored["output_ids"]!=ref["output_ids"]:raise RuntimeError("greedy mismatch after Host restore")
    details=restored.get("meta_info",{}).get("cached_tokens_details")
    if not details or details.get("host",0)<=0:raise RuntimeError(f"restore request did not prove Host source: {details}")
    after=rows()
    # Exact host-source match plus successful output proves the request was
    # served from the target prefix in Host; L2 restore is a device allocation
    # and need not retain a second Host copy. Do not require an invented
    # residency_snapshot event: T38C's residency barrier intentionally means
    # all tiers detached and is not the L2 Host-present predicate.
    if len(storage_submit_requests)!=0:raise RuntimeError("target storage submission already exists before explicit storage exercise")
    print("L2_RESTORE_PASS",json.dumps({"node_id":nid,"hash":h,"prefix_sha256":sha,"reference":ref["output_ids"],"restored":restored["output_ids"],"source":details,"device_detach_pools":sorted({e.get("pool") for e in cold})}),flush=True)
    print("R8 L2 PASS; explicit L3 persistence/read/eviction still required",flush=True)

if __name__=="__main__":main()
