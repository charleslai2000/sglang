#!/usr/bin/env python3
"""Run one exact-hit QUASAR cohort and persist IDs for same-run verification."""

import argparse, concurrent.futures, json, pathlib, threading, time, urllib.request, os, signal

p = argparse.ArgumentParser()
p.add_argument("--concurrency", type=int, choices=(1, 8, 32), required=True)
p.add_argument("--kind", choices=("prefill", "decode"), required=True)
p.add_argument("--run-dir", type=pathlib.Path, required=True)
p.add_argument("--profile-seconds", type=float, default=24)
a = p.parse_args()
d = a.run_dir
f = json.load(open(d / "fixture.json"))
url = f"http://127.0.0.1:{os.environ['QUASAR_PROFILE_PORT']}/generate"
sched = int((d / "scheduler.pid").read_text())
items = []
if a.kind == "decode":
    items = [("quasar-decode-c32-i" + str(i), f["prompts"][f"c32-r1-i{i}"]) for i in range(a.concurrency)]
else:
    items = [(f"quasar-{a.kind}-c{a.concurrency}-i{i}", f["prompts"][f"c{a.concurrency}-r1-i{i}"]) for i in range(a.concurrency)]
bar = threading.Barrier(a.concurrency + 1)
gate = threading.Event()


def send(item):
    rid, ids = item
    body = {
        "rid": rid,
        "input_ids": [ids],
        "sampling_params": {
            "temperature": 0,
            "top_p": 1,
            "max_new_tokens": 256,
            "min_new_tokens": 256,
            "logit_bias": {"1": -100, "105": -100, "106": -100},
            "ignore_eos": False,
            "stop": [],
            "stop_strs": [],
            "stop_token_ids": [],
        },
        "return_token_ids": True,
    }
    bar.wait()
    gate.wait()
    q = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    obj = json.load(urllib.request.urlopen(q, timeout=7200))
    obj = obj[0] if isinstance(obj, list) and len(obj) == 1 else obj
    meta = obj.get("meta_info", {})
    idsout = obj.get("output_ids", [])
    if (
        len(idsout) != 256
        or meta.get("cached_tokens") != 7168
        or meta.get("cached_tokens_details", {}).get("device") != 7168
        or meta.get("cached_tokens_details", {}).get("host") != 0
    ):
        raise RuntimeError(f"{rid}: invalid hit/output {meta}")
    return {
        "rid": rid,
        "output_ids_sha256": __import__("hashlib")
        .sha256(json.dumps(idsout, separators=(",", ":")).encode())
        .hexdigest(),
        "output_tokens": len(idsout),
        "meta": meta,
    }


if a.kind == "decode":
    # Primer has already inserted the exact 7,168-token shared prefix. Do not
    # send 8K prompts concurrently before capture; only the 1,024-token tails
    # are placed in the profile cohort.
    items = [(rid, ids[-1024:]) for rid, ids in items]
    # Verify split preserves intended 1,024-token extend and exact shared prefix.
    assert len(items) == 32 and all(len(ids) == 1024 for _, ids in items)
with concurrent.futures.ThreadPoolExecutor(max_workers=a.concurrency) as ex:
    fs = [ex.submit(send, x) for x in items]
    bar.wait()
    time.sleep(3)
    os.kill(sched, signal.SIGUSR1)
    t = time.time()
    gate.set()
    rs = [x.result() for x in fs]
    time.sleep(a.profile_seconds)
    os.kill(sched, signal.SIGUSR2)
(d / f"profile-{a.kind}-c{a.concurrency}.json").write_text(
    json.dumps(
        {
            "kind": a.kind,
            "concurrency": a.concurrency,
            "profile_window_wall_start_unix_s": t,
            "profile_window_wall_end_unix_s": time.time(),
            "requests": rs,
        },
        indent=2,
    )
    + "\n"
)
print(
    json.dumps(
        {
            "kind": a.kind,
            "c": a.concurrency,
            "requests": len(rs),
            "output_ok": all(x["output_tokens"] == 256 for x in rs),
            "prefix_device_hit": all(
                x["meta"]["cached_tokens_details"]["device"] == 7168
                and x["meta"]["cached_tokens_details"]["host"] == 0
                for x in rs
            ),
        }
    )
)
