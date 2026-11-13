#!/usr/bin/env python3
"""Send one deterministic Radix request cohort and archive per-request evidence."""

import argparse
import concurrent.futures
import json
import pathlib
import threading
import time
import urllib.request
import ctypes

parser = argparse.ArgumentParser()
parser.add_argument("--concurrency", type=int, choices=(16, 24, 32), required=True)
parser.add_argument("--kind", choices=("prefill", "decode"), required=True)
parser.add_argument("--run-dir", type=pathlib.Path, required=True)
parser.add_argument("--profile-seconds", type=float, default=24)
parser.add_argument("--profile-trigger", action="store_true")
parser.add_argument("--control-session", default=None)
parser.add_argument("--post-window-hold", type=float, default=0)
args = parser.parse_args()
fixture = json.loads((args.run_dir / "fixture.json").read_text())
url = "http://127.0.0.1:31371/generate"
requests = []
for i in range(args.concurrency):
    rid = f"radix8k-prof-{args.kind}-c{args.concurrency}-i{i}"
    prompt_key = f"c{args.concurrency}-r0-i{i}"
    requests.append((rid, fixture["prompts"][prompt_key]))
barrier = threading.Barrier(args.concurrency + 1)
window_start = threading.Event()
prof_end = threading.Event()
trigger = threading.Event()


def post(item):
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
    barrier.wait()
    window_start.wait()
    if args.profile_trigger:
        trigger.wait(timeout=120)
    t0 = time.perf_counter()
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    response = json.load(urllib.request.urlopen(req, timeout=1800))
    elapsed = time.perf_counter() - t0
    obj = response[0] if isinstance(response, list) and len(response) == 1 else response
    if not isinstance(obj, dict):
        raise RuntimeError(f"{rid}: unexpected response")
    meta = obj.get("meta_info", {})
    if len(obj.get("output_ids", [])) != 256:
        raise RuntimeError(f"{rid}: invalid output length: {meta}")
    if meta.get("cached_tokens") != 7168:
        raise RuntimeError(f"{rid}: invalid cached prefix (expected 7168): {meta}")
    return {
        "rid": rid,
        "wall_s": elapsed,
        "output_tokens": len(obj["output_ids"]),
        "meta": meta,
    }


with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as pool:
    futures = [pool.submit(post, item) for item in requests]
    barrier.wait()
    start = time.time()
    print("profile client armed", flush=True)
    window_start.set()
    trigger_ts = None
    if args.profile_trigger:
        import os
        import signal

        time.sleep(3)
        scheduler_pid = int((args.run_dir / "scheduler.pid").read_text())
        os.kill(scheduler_pid, signal.SIGUSR1)
        trigger.set()
        trigger_ts = time.time()
    records = [future.result() for future in futures]
    if args.profile_trigger:
        os.kill(scheduler_pid, signal.SIGUSR2)
    end = time.time()
    if args.post_window_hold:
        time.sleep(args.post_window_hold)
result = {
    "kind": args.kind,
    "concurrency": args.concurrency,
    "profile_window_wall_start_unix_s": start,
    "profile_trigger_wall_unix_s": trigger_ts,
    "profile_window_wall_end_unix_s": end,
    "profile_requested_seconds": args.profile_seconds,
    "client_wall_s": end - start,
    "requests": records,
}
(args.run_dir / f"profile-{args.kind}-c{args.concurrency}.json").write_text(
    json.dumps(result, indent=2) + "\n"
)
print(
    json.dumps({k: v for k, v in result.items() if k != "requests"}, indent=2),
    flush=True,
)
