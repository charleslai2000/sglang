#!/usr/bin/env python3
"""Controlled-capacity functional check: normal Host eviction of the exact
FULL+MAMBA target (write_back), then a real Storage->Host->GPU restore."""
import hashlib, json, subprocess, time
from pathlib import Path
import requests
from transformers import AutoTokenizer

BASE = "http://127.0.0.1:30130"
OUT = Path(__file__).resolve().parent
MODEL = "/data/models/Falcon-H1-7B-Instruct-GPTQ-Int4"
TARGET_HASH = "721e82b98783b54519c46e4be90f5363be52d20bcbba82a614d022a61eafe09c"
T = AutoTokenizer.from_pretrained(MODEL, trust_remote_code=True)
S = requests.Session()
BASE_IDS = T.encode("R5 session-9001 unique sentinel: " + "blue copper river lantern meadow " * 1000,
                    add_special_tokens=False)[:1920]
assert len(BASE_IDS) == 1920


def gen(ids, tag):
    t0 = time.perf_counter()
    r = S.post(BASE + "/generate", json={
        "input_ids": ids,
        "sampling_params": {"temperature": 0, "max_new_tokens": 1, "ignore_eos": True},
        "return_cached_tokens_details": True,
        "return_token_ids": True,
    }, timeout=600)
    r.raise_for_status()
    d = r.json()
    if "error" in d:
        raise RuntimeError(d)
    meta = d.get("meta_info") or {}
    rec = {"tag": tag, "output_ids": d.get("output_ids"),
           "cached_tokens": meta.get("cached_tokens"),
           "cached_tokens_details": meta.get("cached_tokens_details"),
           "e2e_latency": meta.get("e2e_latency"),
           "elapsed_s": time.perf_counter() - t0}
    (OUT / "requests.jsonl").open("a").write(json.dumps(rec) + "\n")
    print("REQUEST", json.dumps(rec), flush=True)
    return rec


def comp_ids(i):
    txt = f"T003 evict competitor {i:02d} unique seed {i * 7919}: " + (f"material-{i:02d} " * 1200)
    x = T.encode(txt, add_special_tokens=False)[:1920]
    return x


def probe_events():
    p = OUT / "t38c-probe.jsonl"
    if not p.exists():
        return []
    return [json.loads(ln) for ln in p.read_text().splitlines() if ln.strip()]


def main():
    first = gen(BASE_IDS, "target_cold_restore")
    if first["output_ids"] != [10553]:
        raise RuntimeError(f"cold restore greedy mismatch: {first['output_ids']}")
    print("COLD_RESTORE_SOURCE", json.dumps(first["cached_tokens_details"]), flush=True)

    detached = None
    for i in range(1, 9):
        gen(comp_ids(i), f"competitor_{i:02d}")
        ev = probe_events()
        rows = [e for e in ev if str(e.get("node_id")) == "26"
                and e.get("final_kv_hash") == TARGET_HASH]
        host_det = [e for e in rows if e.get("evt") == "residency_detach"
                    and e.get("tier") == "host"]
        dev_det = [e for e in rows if e.get("evt") == "residency_detach"
                   and e.get("tier") == "device"]
        print("EVICT_CHECK", i, "host_detach", [(e.get("pool"), e.get("slot_count")) for e in host_det],
              "device_detach", [(e.get("pool"), e.get("slot_count")) for e in dev_det], flush=True)
        if host_det:
            detached = i
            break

    # Drop the OS page cache so the restore's pread must reach the device.
    subprocess.run(["sync"], check=True)
    subprocess.run(["sudo", "-n", "sh", "-c", "echo 3 > /proc/sys/vm/drop_caches"], check=True)
    ds0 = Path("/proc/diskstats").read_text()

    again = gen(BASE_IDS, "target_after_eviction")
    ds1 = Path("/proc/diskstats").read_text()

    def sectors(text, name):
        for ln in text.splitlines():
            f = ln.split()
            if len(f) > 13 and f[2] == name:
                return int(f[5])
        return None

    delta = sectors(ds1, "sda") - sectors(ds0, "sda")
    result = {
        "eviction_competitor_count": detached,
        "after_eviction_source": again["cached_tokens_details"],
        "output_ids": again["output_ids"],
        "disk_sectors_read_delta": delta,
        "disk_bytes_read_delta": delta * 512,
        "e2e_latency": again["e2e_latency"],
    }
    (OUT / "evict_result.json").write_text(json.dumps(result, indent=2) + "\n")
    print("EVICT_RESULT", json.dumps(result), flush=True)
    assert again["output_ids"] == [10553], f"post-eviction greedy mismatch: {again['output_ids']}"
    assert int((again["cached_tokens_details"] or {}).get("storage", 0)) > 0, \
        f"post-eviction restore was not Storage-sourced: {again['cached_tokens_details']}"
    print("L3_EVICTION_THEN_STORAGE_RESTORE_PASS", flush=True)


if __name__ == "__main__":
    main()
