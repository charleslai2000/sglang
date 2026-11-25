#!/usr/bin/env python3
"""Bounded target-specific FULL+MAMBA L2 eviction/restore using existing T38C evidence."""
import hashlib, json, time, os
from pathlib import Path
import requests
from transformers import AutoTokenizer
BASE="http://127.0.0.1:30130"; OUT=Path(__file__).resolve().parent
MODEL="/data/models/Falcon-H1-7B-Instruct-GPTQ-Int4"; TOK=AutoTokenizer.from_pretrained(MODEL,trust_remote_code=True); S=requests.Session()
TARGET_SESSION="falcon-t003-target-radix-session-9001"

def target_ids():
    ids=TOK.encode("R5 session-9001 unique sentinel: "+"blue copper river lantern meadow "*1000,add_special_tokens=False)[:1920]
    if len(ids)!=1920: raise RuntimeError(f"bad target length {len(ids)}")
    return ids

def competitor_ids(i):
    text=f"R7C competitor {i:04d} unique: " + "cedar quartz meadow orbit azure "*500
    ids=TOK.encode(text,add_special_tokens=False)[:1920]
    if len(ids)!=1920: raise RuntimeError(f"competitor {i} prompt length invalid: {len(ids)}")
    return ids

PROBE_PATH=Path(__file__).with_name("t38c-probe.jsonl")
PROBE_PREFIX="falcon-t003-l2-"

def rows():
    p=PROBE_PATH
    return [json.loads(x) for x in p.read_text().splitlines() if x.strip() and json.loads(x).get("run_id","").startswith(PROBE_PREFIX) and json.loads(x).get("evt")=="backup_host_commit"]

def metrics(tag):
    text=S.get(BASE+"/metrics",timeout=20).text
    (OUT/f"{tag}.metrics").write_text("\n".join(x for x in text.splitlines() if not x.startswith("#") and any(k in x for k in ("hicache_host_used_tokens","hicache_host_total_tokens","hicache_mamba_host_usable_tokens","hicache_kv_host_usable_tokens","mamba_available_tokens","mamba_evictable_tokens","mamba_used_tokens","evicted_tokens_total","load_back_tokens_total","load_back_bytes_total")))+"\n")
    return text

def request(ids,tag,sid=None):
    before=metrics("_scratch");t=time.perf_counter()
    r=S.post(BASE+"/generate",json={"input_ids":ids,"sampling_params":{"temperature":0,"max_new_tokens":32,"ignore_eos":True},"return_cached_tokens_details":True,"return_token_ids":True,"rid":("e98c7b700ab94bd98bcf8d9e4d84f975" if tag=="target_pre_pressure" else f"e98c7b700ab94bd98bcf8d9e4d84f975-{tag}"),**({"session_id":sid} if sid else {})},timeout=600);r.raise_for_status();d=r.json()
    if "error" in d: raise RuntimeError(d)
    out=d.get("output_ids") or (d.get("choices",[{}])[0].get("token_ids") if d.get("choices") else None)
    result={"tag":tag,"output_ids":out,"meta_info":d.get("meta_info"),"elapsed_s":time.perf_counter()-t}
    with (OUT/"l2_requests.jsonl").open("a") as f:f.write(json.dumps(result)+"\n")
    print(json.dumps(result),flush=True);return result

def main():
    ids=target_ids(); sha=hashlib.sha256(json.dumps(ids,separators=(",",":")).encode()).hexdigest()
    run_id=os.environ.get("T38C_RUN_ID")
    events=rows()
    if run_id is None:
        run_ids={e.get("run_id") for e in events if e.get("evt")=="build_complete" and e.get("session_id")==TARGET_SESSION and e.get("result") is True}
        if len(run_ids)!=1:raise RuntimeError(f"expected one target build run id, got {sorted(str(x) for x in run_ids)}")
        run_id=next(iter(run_ids))
    builds=[e for e in events if e.get("evt")=="build_complete" and e.get("session_id")==TARGET_SESSION and e.get("run_id")==run_id and e.get("result") is True]
    if not builds:
        builds=[e for e in events if e.get("evt")=="build_complete" and e.get("session_id")==TARGET_SESSION and e.get("result") is True]
    if len(builds)!=1:raise RuntimeError(f"expected one build in run {run_id}, got {len(builds)}")
    b=builds[0]; nid=str(b["node_id"]); h=b["final_kv_hash"]
    commits=[e for e in events if e.get("evt")=="backup_host_commit" and str(e.get("node_id"))==nid and e.get("final_kv_hash")==h and e.get("kv_transfer") and e.get("mamba_transfer")]
    if not commits:
        raise RuntimeError("target FULL+MAMBA durable ACK not observed yet; request lock may release before ACK");
    run_id = commits[-1].get("run_id", run_id)
    events = [e for e in events if e.get("run_id") == run_id]
    if len(commits)!=1:raise RuntimeError("FULL+MAMBA target commit missing/ambiguous")
    c=commits[0]
    # The marker-gated synchronized residency snapshot is the exact ACK evidence.
    acks=[e for e in events if e.get("evt")=="backup_host_ack_residency_snapshot" and str(e.get("node_id"))==nid and e.get("final_kv_hash")==h and e.get("finish_event_synchronized") is True]
    if not acks:
        # A single bounded competitor advances the normal scheduler/cache
        # drain; this is a completion trigger, not capacity pressure evidence.
        trigger_sid="falcon-t003-ack-trigger-0001"
        request(competitor_ids(1),"ack_drain_trigger",trigger_sid)
        S.post(BASE+"/close_session",json={"session_id":trigger_sid},timeout=30).raise_for_status()
        deadline=time.monotonic()+15
        while time.monotonic()<deadline:
            time.sleep(.1)
            events=rows()
            acks=[e for e in events if e.get("evt")=="backup_host_ack_residency_snapshot" and str(e.get("node_id"))==nid and e.get("final_kv_hash")==h and e.get("finish_event_synchronized") is True]
            if acks:break
    if len(acks)!=1:raise RuntimeError("target synchronized ACK missing/ambiguous after bounded scheduler drain trigger")
    ack=acks[0]
    if c.get("operation_id") is not None and ack.get("operation_id")!=c["operation_id"]:raise RuntimeError("commit/ACK operation identity mismatch")
    if len(acks)!=1:raise RuntimeError("target ACK missing/ambiguous")
    ack=acks[0]
    residency=ack.get("component_residency") or {}
    if set(residency)!={"FULL","MAMBA"} or any(not row.get("device_present") or not row.get("host_present") for row in residency.values()):
        raise RuntimeError(f"post-ACK joint KV+MAMBA residency missing before pressure: {residency}")
    if any(row.get("host_lock_ref") != 0 for row in residency.values()):
        raise RuntimeError(f"target Host ownership is pinned before close/pressure: {residency}")
    # A request may still hold a legitimate device lock when the D->H ACK is
    # observed. Host-leaf eligibility is gated on the later request/slot release,
    # never inferred from ACK alone.
    ref=request(ids,"target_pre_pressure",TARGET_SESSION)
    if not ref.get("output_ids") or len(ref["output_ids"]) < 32:
        raise RuntimeError(f"long greedy reference missing: {ref.get('output_ids')}")
    close=S.post(BASE+"/close_session",json={"session_id":TARGET_SESSION},timeout=30);close.raise_for_status()
    target_rows=[e for e in rows() if e.get("evt")=="request_lock_lifecycle" and e.get("node_id")==int(nid) and e.get("phase")=="after_request_release"]
    if not target_rows:
        raise RuntimeError("normal request release did not emit target post-release snapshot")
    post_release=target_rows[-1]
    if post_release.get("mamba_lock_ref") != 0 or any(ref.get("lock_ref") != 0 for ref in post_release.get("full_path_refs", [])):
        raise RuntimeError(f"target request lock remains after legitimate release: {post_release}")
    if not post_release.get("host_leaf_expected") or not post_release.get("host_leaf_indexed"):
        raise RuntimeError(f"post-release Host leaf/LRU membership missing: {post_release}")
    target_rows=[e for e in rows() if str(e.get("node_id"))==nid and e.get("final_kv_hash")==h]
    # Device state has 45 Mamba slots, while the independent Host Mamba pool
    # exposes 91 usable slots. Use just enough unique, session-released
    # requests to force L1 eviction, then check target identity before revisiting.
    # Do not use FULL Host aggregate utilization as a proxy for Mamba capacity.
    # Device Mamba capacity is 45 states and host capacity is 91 states in
    # the frozen ratio=2 server. Bound pressure to one measured device pool,
    # sampling target identity after each 4 unique released sessions; never
    # infer target eviction from aggregate request counts.
    max_competitors=48
    for i in range(1,max_competitors+1):
        sid=f"falcon-t003-competitor-{i:04d}"
        request(competitor_ids(i),f"competitor_{i:04d}",sid)
        cr=S.post(BASE+"/close_session",json={"session_id":sid},timeout=30);cr.raise_for_status()
        if i%4==0 or i==max_competitors:
            text=metrics(f"pressure_{i:03d}")
            target_events=[e for e in rows() if str(e.get("node_id"))==nid and e.get("final_kv_hash")==h]
            detaches=[e for e in target_events if e.get("evt")=="residency_detach" and e.get("pool") in ("kv","mamba") and e.get("tier")=="device"]
            cold_pools={e.get("pool") for e in detaches}
            if cold_pools=={"kv","mamba"}:
                print("TARGET_DEVICE_DETACH",json.dumps({"competitors":i,"node_id":nid,"hash":h,"detach_events":[e.get("event_id") for e in detaches]}),flush=True);break
            match=__import__("re").search(r'sglang:hicache_mamba_host_usable_tokens\\{[^}]*model_name="falcon-h1-r7c"[^}]*\\} ([0-9.]+)',text)
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
    print("L2_RESTORE_PASS",json.dumps({"node_id":nid,"hash":h,"prefix_sha256":sha,"reference":ref["output_ids"],"restored":restored["output_ids"],"source":details,"device_detach_pools":sorted({e.get("pool") for e in cold})}),flush=True)
    print("R7B L2 PASS; L3 not run",flush=True)

if __name__=="__main__":main()
