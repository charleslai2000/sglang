#!/usr/bin/env python3
"""Bounded target-specific FULL+MAMBA L2 eviction/restore using existing T38C evidence."""
import hashlib, json, time, os
from pathlib import Path
import requests
from transformers import AutoTokenizer
BASE="http://127.0.0.1:30132"; OUT=Path(__file__).resolve().parent
MODEL="/data/models/Falcon-H1-7B-Instruct-GPTQ-Int4"; TOK=AutoTokenizer.from_pretrained(MODEL,trust_remote_code=True); S=requests.Session()
TARGET_SESSION="falcon-r7c-target-radix-session-9001"

def target_ids():
    ids=TOK.encode("R5 session-9001 unique sentinel: "+"blue copper river lantern meadow "*1000,add_special_tokens=False)[:1920]
    if len(ids)!=1920: raise RuntimeError(f"bad target length {len(ids)}")
    return ids

def competitor_ids(i):
    text=f"R7C competitor {i:04d} unique: " + "cedar quartz meadow orbit azure "*500
    ids=TOK.encode(text,add_special_tokens=False)[:1920]
    if len(ids)!=1920: raise RuntimeError(f"competitor {i} prompt length invalid: {len(ids)}")
    return ids

def current_run_id():
    return (OUT / "current-run-id.txt").read_text().strip()

def rows():
    p=OUT/"t38c-probe.jsonl"
    run_id = current_run_id()
    return [json.loads(x) for x in p.read_text().splitlines() if x.strip() and json.loads(x).get("run_id")==run_id]

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
    # Construct and verify the target in this fresh process before inspecting
    # its build event. Never make a stale/missing build fatal before issuing it.
    ref=request(ids,"target_pre_pressure",TARGET_SESSION)
    if ref["output_ids"] != [10553]: raise RuntimeError("unexpected greedy reference")
    events=rows(); builds=[e for e in events if e.get("evt")=="build_complete" and e.get("run_id")==current_run_id() and e.get("session_id")==TARGET_SESSION and e.get("result") is True]
    if len(builds)!=1:raise RuntimeError(f"expected one build in fresh service, got {len(builds)}")
    b=builds[0]; nid=str(b["node_id"]); h=b["final_kv_hash"]
    commits=[e for e in events if e.get("evt")=="backup_host_commit" and str(e.get("node_id"))==nid and e.get("final_kv_hash")==h and e.get("kv_transfer") and e.get("mamba_transfer")]
    if len(commits)!=1 or not isinstance(commits[0].get("operation_id"),int):raise RuntimeError("FULL+MAMBA target commit operation missing")
    c=commits[0]
    node_acks=[e for e in events if e.get("evt")=="backup_host_ack" and e.get("operation_id")==c["operation_id"] and str(e.get("node_id"))==nid and e.get("final_kv_hash")==h and e.get("finish_event_synchronized") is True]
    batch_acks=[e for e in events if e.get("evt")=="backup_host_ack_batch" and e.get("finish_event_synchronized") is True and [nid, c["operation_id"]] in e.get("node_operation_ids", []) and [nid, 1792] in e.get("node_host_tokens", [])]
    if len(node_acks)+len(batch_acks)!=1:raise RuntimeError("target ACK missing/ambiguous")
    close=S.post(BASE+"/close_session",json={"session_id":TARGET_SESSION},timeout=30);close.raise_for_status()
    # R7C's model device capacity is sized around 45 Mamba path states, while
    # write-through also creates Full D+H duplicates. Each competitor's normal
    # D->H backup may reclaim those duplicates, but on this run trace the
    # target's Full host copy must be reclaimed first before the target's
    # device value can cascade to a genuinely Host-only node. Bound natural
    # pressure to 48 unique completed competitors, sampling target after each
    # request; never mutate cache sets/counters or evict with active locks.
    target_device_reclaimed = False
    max_competitors = 48
    for i in range(1, max_competitors + 1):
        sid = f"falcon-t003-l2-competitor-{i:04d}"
        request(competitor_ids(i), f"competitor_{i:04d}", sid)
        close = S.post(BASE + "/close_session", json={"session_id": sid}, timeout=30)
        close.raise_for_status()
        event_rows = rows()
        target_events = [e for e in event_rows if str(e.get("node_id")) == nid and e.get("final_kv_hash") == h]
        target_device_detached = any(e.get("evt") == "residency_detach" and e.get("tier") == "device" and e.get("pool") in ("kv", "mamba") for e in target_events)
        metrics(f"pressure_{i:03d}")
        if target_device_detached:
            target_device_reclaimed = True
            print("TARGET_DEVICE_RECLAIMED", json.dumps({"competitors": i, "node_id": nid, "hash": h}), flush=True)
            break
        if i % 8 == 0:
            print("PRESSURE_PROGRESS", json.dumps({"competitors": i, "target_device_detached": target_device_detached}), flush=True)
    if not target_device_reclaimed:
        raise RuntimeError(f"bounded {max_competitors}-competitor pressure did not produce target device detach; refuse further pressure")
    # Restore target from Host after natural device eviction; Host detach is not required.
    # The HTTP RID then anchors the existing request/transfer/finish events.
    metrics("before_restore")
    restored = request(ids, "target_host_restore")
    restore_rid = restored.get("meta_info", {}).get("id")
    if not restore_rid:
        raise RuntimeError("restore request did not return a RID")
    append = OUT / "l2_requests.jsonl"
    with append.open("a") as f:
        f.write(json.dumps({"tag":"target_restore_complete","restore_rid":restore_rid,"node_id":nid,"final_kv_hash":h,"http_complete_mono_ns":time.monotonic_ns(),"output_ids":restored["output_ids"]})+"\\n")
    if restored["output_ids"] != ref["output_ids"]:
        raise RuntimeError("greedy mismatch after Host restore")
    details = restored.get("meta_info", {}).get("cached_tokens_details")
    if not details or details.get("host", 0) <= 0:
        raise RuntimeError(f"restore request did not prove Host source: {details}")
    print("L2_RESTORE_PASS", json.dumps({"node_id": nid, "hash": h, "prefix_sha256": sha, "reference": ref["output_ids"], "restored": restored["output_ids"], "source": details}), flush=True)
