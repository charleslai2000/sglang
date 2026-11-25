#!/usr/bin/env python3
"""Cold-start real FULL+MAMBA Storage->Host->GPU restore against an existing Extent store."""
import hashlib, json, time
from pathlib import Path
import requests
from transformers import AutoTokenizer

BASE = "http://127.0.0.1:30129"
OUT = Path(__file__).resolve().parent
RUN_PREFIX = "falcon-t003-l3r-"
MODEL = "/data/models/Falcon-H1-7B-Instruct-GPTQ-Int4"
TARGET_HASH = "721e82b98783b54519c46e4be90f5363be52d20bcbba82a614d022a61eafe09c"
T = AutoTokenizer.from_pretrained(MODEL, trust_remote_code=True)
S = requests.Session()


def target_ids():
    x = T.encode("R5 session-9001 unique sentinel: " + "blue copper river lantern meadow " * 1000,
                 add_special_tokens=False)[:1920]
    assert len(x) == 1920
    return x


def metrics(tag):
    text = S.get(BASE + "/metrics", timeout=20).text
    keep = ("load_back_tokens_total", "load_back_bytes_total",
            "prefill_effective_tokens_total", "hicache_host_used_tokens",
            "hicache_host_total_tokens")
    rows = [ln for ln in text.splitlines()
            if not ln.startswith("#") and any(k in ln for k in keep)]
    (OUT / f"{tag}.metrics").write_text("\n".join(rows) + "\n")
    return rows


def diskstats():
    out = {}
    for ln in Path("/proc/diskstats").read_text().splitlines():
        f = ln.split()
        if len(f) > 13 and f[2] in ("sda", "sda1", "nvme0n1", "dm-0"):
            # sectors read = field index 5 (0-based: major minor name reads_completed reads_merged sectors_read ...)
            out[f[2]] = {"reads": int(f[3]), "sectors_read": int(f[5])}
    return out


def main():
    x = target_ids()
    sha = hashlib.sha256(json.dumps(x, separators=(",", ":")).encode()).hexdigest()
    print("TARGET_SHA256", sha, flush=True)
    metrics("before_restore")
    ds0 = diskstats()
    # Force the Extent pread to reach the physical device instead of the OS page cache.
    import subprocess
    subprocess.run(["sync"], check=True)
    subprocess.run(["sudo", "-n", "sh", "-c", "echo 3 > /proc/sys/vm/drop_caches"], check=True)
    ds1 = diskstats()
    t0 = time.perf_counter()
    r = S.post(BASE + "/generate", json={
        "input_ids": x,
        "sampling_params": {"temperature": 0, "max_new_tokens": 1, "ignore_eos": True},
        "return_cached_tokens_details": True,
        "return_token_ids": True,
    }, timeout=600)
    r.raise_for_status()
    data = r.json()
    elapsed = time.perf_counter() - t0
    if "error" in data:
        raise RuntimeError(data)
    ds2 = diskstats()
    meta = data.get("meta_info") or {}
    details = meta.get("cached_tokens_details") or {}
    delta = {k: {kk: ds2[k][kk] - ds1[k][kk] for kk in ds1[k]} for k in ds1}
    result = {
        "output_ids": data.get("output_ids"),
        "cached_tokens": meta.get("cached_tokens"),
        "cached_tokens_details": details,
        "prompt_tokens": meta.get("prompt_tokens"),
        "e2e_latency": meta.get("e2e_latency"),
        "queue_time": meta.get("queue_time"),
        "elapsed_s": elapsed,
        "diskstats_delta": delta,
    }
    (OUT / "requests.jsonl").open("a").write(json.dumps(result) + "\n")
    (OUT / "after_restore.metrics").write_text("\n".join(metrics("after_restore")) + "\n")
    print("RESTORE_RESULT", json.dumps(result), flush=True)
    assert data.get("output_ids") == [10553], f"greedy mismatch: {data.get('output_ids')}"
    assert int(details.get("storage", 0)) > 0, f"not a Storage-source restore: {details}"
    print("L3_COLD_START_RESTORE_PASS", flush=True)


if __name__ == "__main__":
    main()
