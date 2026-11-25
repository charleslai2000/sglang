#!/usr/bin/env python3
"""R6 loopback-only Falcon L2 target proof using existing T38C traces."""
import hashlib, json, time
from pathlib import Path
import requests
from transformers import AutoTokenizer

BASE="http://127.0.0.1:30127"; OUT=Path(__file__).resolve().parent
TARGET_SESSION="falcon-r6-target-radix-session-9001"
MODEL="/data/models/Falcon-H1-7B-Instruct-GPTQ-Int4"
TOK=AutoTokenizer.from_pretrained(MODEL,trust_remote_code=True); S=requests.Session()
TARGET=TOK.encode("R5 session-9001 unique sentinel: "+"blue copper river lantern meadow "*1000,add_special_tokens=False)[:1920]
assert len(TARGET)==1920
PREFIX_SHA=hashlib.sha256(json.dumps(TARGET,separators=(",",":")).encode()).hexdigest()

def metrics(tag=None):
    text=S.get(BASE+"/metrics",timeout=20).text
    keys=("prefill_effective_tokens_total","hicache_host_used_tokens","hicache_host_total_tokens","hicache_mamba_host_usable_tokens","hicache_backup_tokens_total","load_back_tokens_total","load_back_bytes_total","evicted_tokens_total")
    rows=[x for x in text.splitlines() if not x.startswith("#") and any(k in x for k in keys)]
    if tag:(OUT/f"{tag}.metrics").write_text("\n".join(rows)+"\n")
    return text,rows

def trace_rows():
    p=OUT/"t38c-probe.jsonl"; out=[]
    if p.exists():
        for line in p.read_text().splitlines():
            try:out.append(json.loads(line))
            except Exception:pass
    return out

def gen(ids,tag,*,session_id=None,new_tokens=1):
    before,_=metrics(); t0=time.perf_counter()
    payload={"input_ids":ids,"sampling_params":{"temperature":0,"max_new_tokens":new_tokens,"ignore_eos":True},"return_cached_tokens_details":True,"return_token_ids":True}
    if session_id is not None:payload["session_id"]=session_id
    r=S.post(BASE+"/generate",json=payload,timeout=300);r.raise_for_status();d=r.json()
    if "error" in d:raise RuntimeError(d)
    after,_=metrics();m=d.get("meta_info",{})
    output_ids=d.get("output_ids") or (d.get("choices",[{}])[0].get("token_ids") if d.get("choices") else None)
    row={"tag":tag,"prompt_token_sha256":hashlib.sha256(json.dumps(ids,separators=(",",":")).encode()).hexdigest(),"prompt_tokens":m.get("prompt_tokens"),"completion_tokens":m.get("completion_tokens"),"output_ids":output_ids,"cached_tokens":m.get("cached_tokens"),"cached_tokens_details":m.get("cached_tokens_details"),"metrics_before":before,"metrics_after":after,"elapsed_s":time.perf_counter()-t0}
    with (OUT/"requests.jsonl").open("a") as f:f.write(json.dumps(row)+"\n")
    print(json.dumps({k:v for k,v in row.items() if k!="output_ids"}),flush=True);return row

def main():
    print("target_tokens",len(TARGET),"prefix_sha256",PREFIX_SHA,"checkpoint_grid",256,flush=True);metrics("baseline")
    ref=gen(TARGET,"target_A",session_id=TARGET_SESSION)
    again=gen(TARGET,"target_A_repeat",session_id=TARGET_SESSION)
    if ref["output_ids"]!=again["output_ids"] or len(ref["output_ids"] or [])!=1:raise RuntimeError("greedy target A/A-repeat mismatch")
    if not again["cached_tokens_details"] or again["cached_tokens_details"].get("device",0)<=0:raise RuntimeError("repeat did not prove device-source prefix hit")
    rows=trace_rows()
    builds=[e for e in rows if e.get("evt")=="build_complete" and e.get("result") is True and e.get("session_id")==TARGET_SESSION]
    if len(builds)!=1:raise RuntimeError(f"expected one target build_complete, got {len(builds)}; inspect T38C debug suppression in server.log")
    b=builds[0]; nid=str(b["node_id"]); h=b.get("final_kv_hash")
    if not h:raise RuntimeError("target final hash empty")
    print("TARGET_BUILD",json.dumps({k:b.get(k) for k in ("event_id","session_id","session_generation","build_rid","node_id","final_kv_hash")}|{"prefix_sha256":PREFIX_SHA,"prefix_tokens":len(TARGET)}),flush=True)
    commits=[e for e in rows if e.get("evt")=="backup_host_commit" and str(e.get("node_id"))==nid and e.get("final_kv_hash")==h and e.get("kv_transfer") and e.get("mamba_transfer")]
    if not commits:raise RuntimeError("no target-bound FULL+MAMBA backup commit; fail closed")
    c=commits[0]; operation_id=c.get("operation_id")
    acks=[e for e in rows if e.get("evt")=="backup_host_ack" and e.get("operation_id")==operation_id and str(e.get("node_id"))==nid and e.get("final_kv_hash")==h and e.get("finish_event_synchronized") is True]
    if not acks:raise RuntimeError("no exact target backup ACK after finish_event synchronization")
    print("TARGET_BACKUP_COMMIT_ACK",json.dumps({k:c.get(k) for k in ("event_id","operation_id","node_id","final_kv_hash","kv_transfer","mamba_transfer","host_tokens")}|{"ack_event_id":acks[0].get("event_id"),"ack_node_ids":acks[0].get("ack_node_ids")}),flush=True)
    # Preserve output reference and close session refs so target can become evictable.
    close=S.post(BASE+"/close_session",json={"session_id":TARGET_SESSION},timeout=30);close.raise_for_status()
    metrics("target_commit")
    print("GATE1_IDENTITY_PASS; pressure/restoration not yet run",flush=True)

if __name__=="__main__":main()
