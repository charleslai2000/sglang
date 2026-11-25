#!/usr/bin/env python3
"""F1-R7 target-gated FULL+MAMBA D->H evidence."""
import hashlib, json, time
from pathlib import Path
import requests
from transformers import AutoTokenizer

BASE = "http://127.0.0.1:30127"
OUT = Path(__file__).resolve().parent
TARGET_SESSION = "falcon-r7-target-radix-session-9001"
MODEL = "/data/models/Falcon-H1-7B-Instruct-GPTQ-Int4"
TOK = AutoTokenizer.from_pretrained(MODEL, trust_remote_code=True)
S = requests.Session()
TARGET = TOK.encode("R5 session-9001 unique sentinel: " + "blue copper river lantern meadow " * 1000, add_special_tokens=False)[:1920]
assert len(TARGET) == 1920
PREFIX_SHA = hashlib.sha256(json.dumps(TARGET, separators=(",", ":")).encode()).hexdigest()

def metrics(tag):
    text = S.get(BASE + "/metrics", timeout=20).text
    keys = ("prefill_effective_tokens_total", "hicache_host_used_tokens", "hicache_host_total_tokens", "hicache_backup_tokens_total", "load_back_tokens_total", "load_back_bytes_total", "evicted_tokens_total")
    rows = [x for x in text.splitlines() if not x.startswith("#") and any(k in x for k in keys)]
    (OUT / f"{tag}.metrics").write_text("\n".join(rows) + "\n")
    return text

def generate(tag, session_id=None):
    start = time.perf_counter()
    payload = {"input_ids": TARGET, "sampling_params": {"temperature": 0, "max_new_tokens": 1, "ignore_eos": True}, "return_cached_tokens_details": True, "return_token_ids": True}
    if session_id:
        payload["session_id"] = session_id
    response = S.post(BASE + "/generate", json=payload, timeout=300)
    response.raise_for_status(); data = response.json()
    if "error" in data: raise RuntimeError(data)
    result = {"tag": tag, "output_ids": data.get("choices", [{}])[0].get("token_ids"), "meta_info": data.get("meta_info"), "elapsed_s": time.perf_counter()-start}
    with (OUT / "requests.jsonl").open("a") as f: f.write(json.dumps(result)+"\n")
    print(json.dumps(result), flush=True); return result

def rows():
    path = OUT / "t38c-probe.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]

def main():
    print("target_tokens", len(TARGET), "prefix_sha256", PREFIX_SHA, "checkpoint_grid", 256, flush=True)
    metrics("baseline")
    reference = generate("target_A", TARGET_SESSION)
    repeat = generate("target_A_repeat", TARGET_SESSION)
    if reference["output_ids"] != repeat["output_ids"]: raise RuntimeError("A/A output mismatch")
    events = rows()
    builds = [r for r in events if r.get("evt") == "build_complete" and r.get("session_id") == TARGET_SESSION and r.get("result") is True]
    if len(builds) != 1: raise RuntimeError(f"expected target build event after fresh R7 boot, got {len(builds)}")
    b = builds[0]; nid = str(b["node_id"]); h = b["final_kv_hash"]
    commits = [r for r in events if r.get("evt") == "backup_host_commit" and str(r.get("node_id")) == nid and r.get("final_kv_hash") == h and r.get("kv_transfer") and r.get("mamba_transfer")]
    if len(commits) != 1 or not isinstance(commits[0].get("operation_id"), int): raise RuntimeError("target commit lacks unique operation ID")
    c = commits[0]
    acks = [r for r in events if r.get("evt") == "backup_host_ack" and r.get("operation_id") == c["operation_id"] and str(r.get("node_id")) == nid and r.get("final_kv_hash") == h and r.get("finish_event_synchronized") is True]
    if len(acks) != 1: raise RuntimeError(f"target exact D->H ACK missing/ambiguous: {len(acks)}")
    print("TARGET_BUILD_COMMIT_ACK", json.dumps({"build_event_id":b.get("event_id"),"build_rid":b.get("build_rid"),"node_id":nid,"final_kv_hash":h,"prefix_sha256":PREFIX_SHA,"operation_id":c["operation_id"],"ack_event_id":acks[0].get("event_id"),"ack_node_ids":acks[0].get("ack_node_ids"),"host_indices_digest":acks[0].get("host_indices_digest"),"host_tokens":acks[0].get("host_tokens")}), flush=True)
    closed = S.post(BASE+"/close_session", json={"session_id":TARGET_SESSION}, timeout=30); closed.raise_for_status()
    metrics("after_target_close")
    print("TARGET_ACK_PASS; L2 pressure/restore and L3/benchmark not run by this gate", flush=True)

if __name__ == "__main__": main()
