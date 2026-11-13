#!/usr/bin/env python3
"""Independent random-token C32 capacity sweep with real 256-token decode."""

import concurrent.futures, json, os, random, statistics, threading, time, urllib.request
from pathlib import Path

OUT = Path(os.environ["GSM_PERF_OUT"])
URL = os.environ.get("W4A16_URL", "http://127.0.0.1:31372/generate")
SEED = 20261114
ROUNDS = int(os.environ.get("W4A16_CAPACITY_ROUNDS", "1"))
LENGTHS = [
    int(x)
    for x in os.environ.get("W4A16_CONTEXT_LENGTHS", "4096,8192,16384,32767").split(",")
]
METRICS_URL = URL.rsplit("/generate", 1)[0] + "/metrics"
rng = random.Random(SEED)
event_lock = threading.Lock()
events = []


def snapshot(kind, tag):
    try:
        txt = urllib.request.urlopen(METRICS_URL, timeout=10).read().decode()
        keys = (
            "num_running_reqs",
            "running_requests",
            "token_usage",
            "kv_token_usage",
            "max_total_num_tokens",
            "max_total_num_tokens_swa",
            "kv_used_tokens",
            "kv_used_tokens_swa",
            "retracted",
        )
        vals = [
            line
            for line in txt.splitlines()
            if line and not line.startswith("#") and any(k in line for k in keys)
        ]
    except Exception as e:
        vals = [f"metrics_error {e!r}"]
    with event_lock:
        events.append(
            {"monotonic": time.monotonic(), "kind": kind, "tag": tag, "metrics": vals}
        )


def send(ids, tag, gate):
    gate.wait()
    body = {
        "rid": tag,
        "input_ids": [ids],
        "sampling_params": {
            "temperature": 0,
            "top_p": 1,
            "max_new_tokens": 256,
            "min_new_tokens": 256,
            "ignore_eos": True,
        },
        "return_token_ids": True,
    }
    req = urllib.request.Request(
        URL,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    snapshot("submit", tag)
    t = time.perf_counter()
    try:
        obj = json.loads(urllib.request.urlopen(req, timeout=3600).read())
        if isinstance(obj, list) and len(obj) == 1:
            obj = obj[0]
        meta = obj.get("meta_info", {})
        out = obj.get("output_ids", meta.get("output_token_ids", []))
        n = int(meta.get("completion_tokens", len(out)))
        row = {
            "rid": meta.get("id", tag),
            "ok": n >= 256 and (not out or len(out) >= 256),
            "prompt_tokens": len(ids),
            "output_tokens": n,
            "elapsed_s": time.perf_counter() - t,
            "meta": meta,
        }
        snapshot("complete", tag)
        if not row["ok"]:
            row["error"] = "fewer than 256 generated tokens"
        return row
    except Exception as e:
        return {
            "rid": tag,
            "ok": False,
            "prompt_tokens": len(ids),
            "output_tokens": 0,
            "elapsed_s": time.perf_counter() - t,
            "error": repr(e),
        }


def main():
    results = []
    for length in LENGTHS:
        for rnd in range(ROUNDS):
            prompts = [
                [rng.randrange(1, 261000) for _ in range(length)] for _ in range(32)
            ]
            (OUT / f"c32-fixture-{length}-r{rnd}.json").write_text(
                json.dumps(
                    {"seed": SEED, "length": length, "round": rnd, "prompts": prompts},
                    separators=(",", ":"),
                )
                + "\n"
            )
            gate = threading.Event()
            t = time.perf_counter()
            with concurrent.futures.ThreadPoolExecutor(max_workers=32) as pool:
                fut = [
                    pool.submit(
                        send, prompts[i], f"c32-l{length}-r{rnd}-i{i:02d}", gate
                    )
                    for i in range(32)
                ]
                gate.set()
                rows = [f.result() for f in fut]
            wall = time.perf_counter() - t
            good = [r for r in rows if r["ok"]]
            rec = {
                "concurrency": 32,
                "length": length,
                "round": rnd,
                "successful_requests": len(good),
                "all_32_succeeded": len(good) == 32,
                "all_real_prefill": all(r["prompt_tokens"] == length for r in rows),
                "all_decode_ge_256": len(good) == 32
                and all(r["output_tokens"] >= 256 for r in good),
                "aggregate_active_kv_tokens_at_full_admission": 32 * length,
                "burst_wall_s": wall,
                "request_latency_p50_s": statistics.median(
                    r["elapsed_s"] for r in rows
                ),
                "request_latency_p95_s": sorted(r["elapsed_s"] for r in rows)[30],
                "requests": rows,
            }
            rec["status"] = (
                "PASS"
                if rec["all_32_succeeded"]
                and rec["all_real_prefill"]
                and rec["all_decode_ge_256"]
                else "FAIL"
            )
            results.append(rec)
            (OUT / f"c32-capacity-{length}-r{rnd}.json").write_text(
                json.dumps(rec, indent=2) + "\n"
            )
            print(
                json.dumps({k: v for k, v in rec.items() if k != "requests"}),
                flush=True,
            )
            if rec["status"] != "PASS":
                break
    (OUT / "c32-runtime-metrics.json").write_text(json.dumps(events, indent=2) + "\n")
    (OUT / "c32-capacity-summary.json").write_text(
        json.dumps(
            {
                "status": "MEASURED",
                "model": "W4A16 safetensors",
                "kv_dtype": "bf16",
                "concurrency": 32,
                "context_lengths": LENGTHS,
                "rounds_per_length": ROUNDS,
                "results": [
                    {k: v for k, v in x.items() if k != "requests"} for x in results
                ],
            },
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
