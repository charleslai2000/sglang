#!/usr/bin/env python3
"""Bounded target-eviction follow-up using the existing R11 prompt generator."""
import json, time
from pathlib import Path
import requests
from transformers import AutoTokenizer

BASE="http://127.0.0.1:30131"; OUT=Path(__file__).resolve().parent
MODEL="/data/models/Falcon-H1-7B-Instruct-GPTQ-Int4"; TOK=AutoTokenizer.from_pretrained(MODEL,trust_remote_code=True); S=requests.Session()
TARGET_HASH="721e82b98783b54519c46e4be90f5363be52d20bcbba82a614d022a61eafe09c"
TARGET_SESSION="t003-l3s-target"

def target_ids():
 x=TOK.encode("R5 session-9001 unique sentinel: "+"blue copper river lantern meadow "*1000,add_special_tokens=False)[:1920]
 assert len(x)==1920; return x

def competitor_ids(i):
 x=TOK.encode(f"R11 competitor {i:04d} unique: "+"cedar quartz meadow orbit azure "*500,add_special_tokens=False)[:1920]
 assert len(x)==1920; return x

def events():
 p=OUT/"t38c-probe.jsonl"
 return [json.loads(x) for x in p.read_text().splitlines() if x.strip()]

def gen(x,tag,sid=None):
 t0=time.perf_counter(); payload={"input_ids":x,"sampling_params":{"temperature":0,"max_new_tokens":1,"ignore_eos":True},"return_cached_tokens_details":True,"return_token_ids":True}
 if sid:payload["session_id"]=sid
 r=S.post(BASE+"/generate",json=payload,timeout=600);r.raise_for_status();d=r.json()
 if "error" in d:raise RuntimeError(d)
 m=d.get("meta_info") or {};z={"tag":tag,"output_ids":d.get("output_ids"),"details":m.get("cached_tokens_details"),"cached":m.get("cached_tokens"),"e2e":m.get("e2e_latency"),"elapsed":time.perf_counter()-t0}
 with (OUT/"requests.jsonl").open("a") as f:f.write(json.dumps(z)+"\n")
 print("REQUEST",json.dumps(z),flush=True);return z

def main():
 x=target_ids(); ref=gen(x,"target_storage_seed",TARGET_SESSION)
 if ref["output_ids"]!=[10553] or not ref["details"] or ref["details"].get("storage",0)!=1792:raise RuntimeError(f"not initial exact Storage restore: {ref}")
 S.post(BASE+"/close_session",json={"session_id":TARGET_SESSION},timeout=30).raise_for_status()
 es=events(); b=[e for e in es if e.get("evt")=="build_complete" and e.get("session_id")==TARGET_SESSION and e.get("result")]
 if len(b)!=1:raise RuntimeError(f"target identity missing/ambiguous {len(b)}")
 nid=str(b[0]["node_id"]);h=b[0]["final_kv_hash"]
 if h!=TARGET_HASH:raise RuntimeError(f"hash mismatch {h}")
 print("TARGET",json.dumps({"node_id":nid,"hash":h,"build":b[0]}),flush=True)
 for i in range(1,7):
  sid=f"t003-l3s-competitor-{i:02d}";gen(competitor_ids(i),f"competitor_{i:02d}",sid)
  S.post(BASE+"/close_session",json={"session_id":sid},timeout=30).raise_for_status()
  es=events();rows=[e for e in es if str(e.get("node_id"))==nid and e.get("final_kv_hash")==h]
  d=[e for e in rows if e.get("evt")=="residency_detach" and e.get("tier")=="device"]
  he=[e for e in rows if e.get("evt")=="residency_detach" and e.get("tier")=="host"]
  print("TARGET_STATE",i,"device_detach",[(e.get("pool"),e.get("slot_count")) for e in d],"host_detach",[(e.get("pool"),e.get("slot_count")) for e in he],flush=True)
  if he:break
 else:print("TARGET_HOST_EVICTION_NOT_OBSERVED_WITHIN_BOUND",flush=True);return
 restored=gen(x,"target_after_host_detach")
 if restored["output_ids"]!=ref["output_ids"]:raise RuntimeError("greedy mismatch")
 if not restored["details"] or restored["details"].get("storage",0)<=0:raise RuntimeError(f"restore not Storage sourced {restored['details']}")
 print("T003_L3S_SAME_PROCESS_PASS",json.dumps({"node_id":nid,"hash":h,"source":restored["details"],"output":restored["output_ids"]}),flush=True)

if __name__=="__main__":main()
