#!/usr/bin/env python3
"""Target-level FULL+MAMBA Extent write/evict/read/restore using existing T38C events."""
import json, time, hashlib
from pathlib import Path
import requests
from transformers import AutoTokenizer
BASE="http://127.0.0.1:30127"; OUT=Path(__file__).resolve().parent
MODEL="/data/models/Falcon-H1-7B-Instruct-GPTQ-Int4"; T=AutoTokenizer.from_pretrained(MODEL,trust_remote_code=True); S=requests.Session()
TARGET_HASH="721e82b98783b54519c46e4be90f5363be52d20bcbba82a614d022a61eafe09c"
SID="falcon-r12-target-radix-session-9001"
NODE_ID=None

def ids():
 x=T.encode("R5 session-9001 unique sentinel: "+"blue copper river lantern meadow "*1000,add_special_tokens=False)[:1920]
 assert len(x)==1920
 return x

def events():
 p=OUT/"t38c-probe.jsonl"
 return [json.loads(s) for s in p.read_text().splitlines() if s.strip() and json.loads(s).get("run_id","").startswith("falcon-r12-l3-")]

def gen(x,tag,sid=None,max_new=1):
 d=S.post(BASE+"/generate",json={"input_ids":x,"sampling_params":{"temperature":0,"max_new_tokens":max_new,"ignore_eos":True},"return_cached_tokens_details":True,"return_token_ids":True,**({"session_id":sid} if sid else {})},timeout=300);d.raise_for_status();r=d.json()
 if "error" in r: raise RuntimeError(r)
 out={"tag":tag,"ids":r.get("output_ids"),"meta":r.get("meta_info")}
 with (OUT/"l3_requests.jsonl").open("a") as f:f.write(json.dumps(out)+"\n")
 print(json.dumps(out),flush=True);return out

def main():
 x=ids(); initial={"ids":[10553]}
 es=events(); builds=[e for e in es if e.get("evt")=="build_complete" and e.get("session_id")==SID and e.get("result")]
 if len(builds)!=1:raise RuntimeError(f"expected one identity-driver build, got {len(builds)}")
 b=builds[0]; nid=str(b["node_id"]); h=b["final_kv_hash"]
 if h!=TARGET_HASH:raise RuntimeError(f"unexpected target hash {h}")
 global NODE_ID
 NODE_ID=nid
 submits=[e for e in es if e.get("evt")=="backup_submit" and str(e.get("node_id"))==nid and e.get("final_kv_hash")==h and e.get("mamba_transfer")]
 acks=[e for e in es if e.get("evt")=="backup_ack_drain" and str(e.get("node_id"))==nid and e.get("final_kv_hash")==h and e.get("result")=="complete" and e.get("kv_durable") is True and e.get("mamba_durable") is True]
 if not submits or not acks:raise RuntimeError(f"same-target FULL+MAMBA storage submit/ACK missing: {len(submits)}/{len(acks)}")
 print("TARGET_STORAGE_ACK",json.dumps({"submits":submits,"acks":acks}),flush=True)
 # Further workload must not destroy both Host and L3; L3 host eviction only after durable chain.
 for i in range(1,56):
  z=T.encode(f"R7C competitor {i:04d} unique: "+"cedar quartz meadow orbit azure "*500,add_special_tokens=False)[:1920]
  gen(z,f"l3_pressure_{i:04d}",f"falcon-r12-storage-pressure-{i:04d}")
  S.post(BASE+"/close_session",json={"session_id":f"falcon-r12-storage-pressure-{i:04d}"},timeout=30).raise_for_status()
  es=events(); rows=[e for e in es if str(e.get("node_id"))==nid and e.get("final_kv_hash")==h]
  if any(e.get("evt")=="residency_detach" and e.get("pool")=="kv" and e.get("tier")=="host" for e in rows):break
 else:raise RuntimeError("target KV Host eviction not observed within 55 unique competitors")
 prefetch=gen(x,"target_extent_restore")
 if prefetch["ids"]!=initial["ids"]:raise RuntimeError("greedy mismatch after Extent restore")
 details=prefetch.get("meta",{}).get("cached_tokens_details") or {}
 if details.get("storage",0)<=0:raise RuntimeError(f"no Storage source observed: {details}")
 es=events(); rows=[e for e in es if str(e.get("node_id"))==nid and e.get("final_kv_hash")==h]
 print("L3_EXTENT_RESTORE_PASS",json.dumps({"node_id":nid,"hash":h,"initial":initial["ids"],"restored":prefetch["ids"],"source":details,"target_events":[{k:e.get(k) for k in ("evt","pool","tier","operation_id","mamba_transfer","kv_transfer","result","storage_key","extent_id","extent_generation","requested_pages","succeeded_pages","bytes_read","bytes_written")} for e in rows if e.get("evt") in ("backup_submit","backup_ack_enqueue","backup_ack_drain","storage_persisted","extent_commit","extent_write","extent_read","pc_get_v2","residency_detach")]}),flush=True)

if __name__=="__main__":main()
