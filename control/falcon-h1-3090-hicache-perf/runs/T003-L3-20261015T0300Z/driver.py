#!/usr/bin/env python3
"""Bounded controlled-capacity FULL+MAMBA Storage->Host->GPU check."""
import hashlib, json, time
from pathlib import Path
import requests
from transformers import AutoTokenizer

BASE = "http://127.0.0.1:30128"
OUT = Path(__file__).resolve().parent
MODEL = "/data/models/Falcon-H1-7B-Instruct-GPTQ-Int4"
T = AutoTokenizer.from_pretrained(MODEL, trust_remote_code=True)
S = requests.Session()
TARGET_SESSION = "t003-l3-target-20261015-storage"
RUN_PREFIX = "falcon-t003-l3-20261015T072642Z"
TARGET_HASH = "721e82b98783b54519c46e4be90f5363be52d20bcbba82a614d022a61eafe09c"


def events():
    p = OUT / "t38c-probe.jsonl"
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text().splitlines()
            if line.strip() and json.loads(line).get("run_id", "").startswith(RUN_PREFIX)]


def make_target():
    x = T.encode("R5 session-9001 unique sentinel: " + "blue copper river lantern meadow " * 1000,
                 add_special_tokens=False)[:1920]
    assert len(x) == 1920
    return x


def gen(ids, tag, sid):
    start = time.perf_counter()
    r = S.post(BASE + "/generate", json={
        "input_ids": ids,
        "sampling_params": {"temperature": 0, "max_new_tokens": 1, "ignore_eos": True},
        "return_cached_tokens_details": True,
        "return_token_ids": True,
        "session_id": sid,
    }, timeout=300)
    r.raise_for_status()
    data = r.json()
    if "error" in data:
        raise RuntimeError(data)
    result = {"tag": tag, "session_id": sid, "output_ids": data.get("output_ids"),
              "meta": data.get("meta_info"), "elapsed_s": time.perf_counter() - start,
              "prompt_sha256": hashlib.sha256(json.dumps(ids, separators=(",", ":")).encode()).hexdigest()}
    with (OUT / "requests.jsonl").open("a") as f:
        f.write(json.dumps(result) + "\n")
    print("REQUEST", json.dumps(result), flush=True)
    return result


def main():
    x = make_target()
    # Reuse the exact R11 target identity and established one-token greedy output.
    baseline = [10553]
    e0 = events()
    builds = [e for e in e0 if e.get("evt") == "build_complete"
              and e.get("session_id") == TARGET_SESSION and e.get("result")]
    if builds:
        raise RuntimeError("target session already exists in this run; refusing ambiguous reuse")
    target = gen(x, "target_seed", TARGET_SESSION)
    if target["output_ids"] != baseline:
        raise RuntimeError(f"target output differs from historical baseline: {target['output_ids']}")
    # Exact target identity and durable FULL+MAMBA write/ACK are prerequisites.
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        es = events()
        builds = [e for e in es if e.get("evt") == "build_complete"
                  and e.get("session_id") == TARGET_SESSION and e.get("result")]
        if builds:
            break
        time.sleep(1)
    if len(builds) != 1:
        raise RuntimeError(f"target build identity missing/ambiguous: {len(builds)}")
    b = builds[0]
    nid, h = str(b["node_id"]), b["final_kv_hash"]
    if h != TARGET_HASH:
        raise RuntimeError(f"target hash mismatch: {h}")
    host_acks = [e for e in events() if e.get("evt") == "backup_host_ack_batch"
                 and e.get("finish_event_synchronized") is True
                 and [nid, 0] in e.get("node_operation_ids", [])]
    if not host_acks:
        raise RuntimeError("fresh target FULL+MAMBA Host ACK missing")
    print("TARGET_HOST_ACK", json.dumps({"node_id": nid, "hash": h, "acks": host_acks}), flush=True)
    target_submit = gen(x, "target_pre_pressure_storage", TARGET_SESSION)
    if target_submit["output_ids"] != baseline:
        raise RuntimeError("target output changed on storage pre-pressure request")
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        es = events()
        rows = [e for e in es if str(e.get("node_id")) == nid and e.get("final_kv_hash") == h]
        storage_acks = [e for e in rows if e.get("evt") == "backup_ack_drain"
                        and e.get("result") == "complete" and e.get("kv_durable") is True
                        and e.get("mamba_durable") is True]
        if storage_acks:
            break
        time.sleep(1)
    if not storage_acks:
        raise RuntimeError("same-target FULL+MAMBA Storage durable ACK missing after ordinary request")
    print("TARGET_STORAGE_DURABLE", json.dumps({"node_id": nid, "hash": h, "acks": storage_acks}), flush=True)
    S.post(BASE + "/close_session", json={"session_id": TARGET_SESSION}, timeout=30).raise_for_status()

    # Six deterministic, distinct 1920-token prefixes. Stop immediately when the
    # exact target has a Host residency-detach event; no retry/pressure loop.
    for i in range(1, 7):
        text = f"T003 unique capacity competitor {i:02d} seed {i * 7919}: " + \
               (f"distinct material {i:02d} sequence " * 1000)
        z = T.encode(text, add_special_tokens=False)[:1920]
        if len(z) < 1792:
            z = (z * ((1792 + len(z) - 1) // len(z)))[:1920]
        sid = f"t003-l3-competitor-{i:02d}"
        gen(z, f"competitor_{i:02d}", sid)
        S.post(BASE + "/close_session", json={"session_id": sid}, timeout=30).raise_for_status()
        es = events()
        rows = [e for e in es if str(e.get("node_id")) == nid and e.get("final_kv_hash") == h]
        detached = [e for e in rows if e.get("evt") == "residency_detach"
                    and e.get("pool") == "kv" and e.get("tier") == "host"]
        print("CAPACITY_CHECK", json.dumps({"competitors": i, "target_detach_events": detached}), flush=True)
        if detached:
            break
    else:
        raise RuntimeError("bounded 6-prefix capacity competition did not evict target Host copy")

    # Same input identity queries storage after exact Host detach; require Storage hit.
    restored = gen(x, "target_storage_restore", "t003-l3-restore-20261015")
    if restored["output_ids"] != baseline:
        raise RuntimeError(f"greedy mismatch: {restored['output_ids']} != {baseline}")
    details = (restored.get("meta") or {}).get("cached_tokens_details") or {}
    if details.get("storage", 0) <= 0:
        raise RuntimeError(f"restore did not report Storage source: {details}")
    es = events()
    rows = [e for e in es if str(e.get("node_id")) == nid and e.get("final_kv_hash") == h]
    print("L3_RESTORE_PASS", json.dumps({
        "node_id": nid, "hash": h, "target_output": target["output_ids"],
        "restored_output": restored["output_ids"], "source": details,
        "events": [e for e in rows if e.get("evt") in (
            "backup_submit", "backup_ack_drain", "storage_persisted", "extent_read",
            "pc_get_v2", "residency_detach", "load_back_registered", "load_back_ack_batch")]
    }), flush=True)


if __name__ == "__main__":
    main()
