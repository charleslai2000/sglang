#!/usr/bin/env python3
"""Reuse the bounded T003 L2 driver at fresh port 30131 with >1 greedy token checks."""
import importlib.util, json, sys
from pathlib import Path
source = Path(__file__).with_name("ack_driver.py")
spec = importlib.util.spec_from_file_location("base_l2_driver", source)
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
base.BASE = "http://127.0.0.1:30131"
base.OUT = Path(__file__).parent
base.TARGET_SESSION = "falcon-t003-target-radix-session-9014"
base.RUN_ID = "falcon-t003-l2-membership-fix-20261014T154154Z"
base.PROBE_PREFIX = "falcon-t003-l2-membership-fix-"
base.PROBE_PATH = base.OUT / "membership-fix-probe.jsonl"
base.rows = lambda: [
    json.loads(line) for line in base.PROBE_PATH.read_text().splitlines()
    if line.strip() and json.loads(line).get("run_id", "").startswith(base.PROBE_PREFIX)
]
base.metrics = lambda tag: base.S.get(base.BASE + "/metrics", timeout=20).text

def request(ids, tag, sid=None):
    base.metrics("unused")
    import time, requests
    started = time.perf_counter()
    r = base.S.post(base.BASE + "/generate", json={
        "input_ids": ids,
        "sampling_params": {"temperature": 0, "max_new_tokens": 32, "ignore_eos": True},
        "return_cached_tokens_details": True,
        "return_token_ids": True,
        "rid": "e98c7b700ab94bd98bcf8d9e4d84f975" if tag == "target_seed" else f"t003-{tag}",
        **({"session_id": sid} if sid else {}),
    }, timeout=600)
    r.raise_for_status(); data = r.json()
    out = data.get("output_ids") or (data.get("choices", [{}])[0].get("token_ids") if data.get("choices") else None)
    row = {"tag": tag, "output_ids": out, "meta_info": data.get("meta_info"), "elapsed_s": time.perf_counter()-started}
    with (base.OUT / "membership-fix-requests.jsonl").open("a") as f: f.write(json.dumps(row)+"\n")
    print(json.dumps(row), flush=True)
    return row
base.request = request
if __name__ == "__main__":
    base.main()
