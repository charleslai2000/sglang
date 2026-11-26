"""Steady-state C32 load for short contexts (T007 round 4).

The historical harness (`g1_shared_prefix_hicache.py`) sends one batch of N
concurrent requests and stops; that measures a single wave, not the throughput
ceiling. This driver keeps `--clients` requests in flight for `--seconds` by
re-posting immediately on completion, so every client is continuously supplied.

Two variants, both on the same 1024-token prompts:
  rotate - the last `--new-tokens` tokens change every iteration, so each
           request must prefill them (short-context serving with real prefill).
  cached - identical prompt every iteration, so the radix/host tiers serve the
           whole prompt from cache (pure decode ceiling).

Reports aggregate output TPS over the window plus client-observed latency and
mean in-flight requests.
"""

import argparse
import json
import statistics
import threading
import time
import urllib.request
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument("--url", default="http://127.0.0.1:31401")
p.add_argument("--fixture", required=True)
p.add_argument("--out", required=True)
p.add_argument("--clients", type=int, default=32)
p.add_argument("--seconds", type=float, default=90.0)
p.add_argument("--new-tokens", type=int, default=256)
p.add_argument("--variant", choices=("rotate", "cached"), default="rotate")
p.add_argument("--warmup-seconds", type=float, default=10.0)
p.add_argument("--vocab-floor", type=int, default=100)
p.add_argument("--vocab-ceiling", type=int, default=200000)
a = p.parse_args()

rows = json.loads(Path(a.fixture).read_text())
rows = rows if isinstance(rows, list) else rows.get("requests", [])
if len(rows) < a.clients:
    raise SystemExit(f"fixture has {len(rows)} rows, need {a.clients}")

lock = threading.Lock()
samples = []
stop = threading.Event()


def post(ids, rid, timeout=1800):
    body = {
        "rid": rid,
        "input_ids": [ids],
        "sampling_params": {
            "temperature": 0,
            "top_p": 1,
            "max_new_tokens": a.new_tokens,
            "min_new_tokens": a.new_tokens,
            "ignore_eos": True,
        },
        "return_token_ids": True,
    }
    req = urllib.request.Request(
        a.url + "/generate",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read())


def rotated(ids, iteration):
    """Change the first uncached token so the trailing new-tokens are recomputed."""
    head = ids[: len(ids) - a.new_tokens]
    span = max(1, a.vocab_ceiling - a.vocab_floor)
    token = a.vocab_floor + (iteration * 7919) % span
    return list(head) + [token] + list(ids[len(ids) - a.new_tokens + 1 :])


def worker(index):
    base = list(rows[index]["input_ids"])
    iteration = 0
    while not stop.is_set():
        ids = rotated(base, iteration) if a.variant == "rotate" else base
        started = time.perf_counter()
        try:
            body = post(ids, f"steady-{index:02d}-{iteration}")
            body = body[0] if isinstance(body, list) else body
            meta = body.get("meta_info") or {}
            usage = meta.get("usage") or {}
            produced = usage.get("completion_tokens")
            if produced is None:
                produced = meta.get("completion_tokens")
            if produced is None:
                produced = meta.get("completion_tokens_details", {}).get("count")
            if produced is None:
                # SGLang's generate endpoint may return output_ids as token IDs,
                # while `text` is decoded characters and cannot measure tokens.
                output_ids = body.get("output_ids")
                if isinstance(output_ids, list):
                    produced = len(output_ids)
            if produced is None:
                raise ValueError("response lacks an authoritative completion-token count")
            error = None
        except Exception as exc:  # keep the window honest: count, do not hide
            produced, error = 0, repr(exc)[:200]
        finished = time.perf_counter()
        with lock:
            samples.append(
                {
                    "client": index,
                    "iteration": iteration,
                    "start": started,
                    "end": finished,
                    "tokens": produced,
                    "error": error,
                }
            )
        iteration += 1


threads = [
    threading.Thread(target=worker, args=(i,), daemon=True) for i in range(a.clients)
]
for thread in threads:
    thread.start()
time.sleep(a.warmup_seconds)
with lock:
    samples.clear()
window_start = time.perf_counter()
time.sleep(a.seconds)
window_end = time.perf_counter()
stop.set()
for thread in threads:
    thread.join(timeout=120)

with lock:
    window = [
        s for s in samples if s["end"] <= window_end and s["start"] >= window_start
    ]

tokens = sum(s["tokens"] for s in window)
errors = sum(1 for s in window if s["error"])
wall = window_end - window_start
latencies = sorted(s["end"] - s["start"] for s in window)
inflight = sum(latencies) / wall if wall else 0.0


def pct(values, q):
    if not values:
        return None
    index = min(len(values) - 1, max(0, int(round(q * (len(values) - 1)))))
    return values[index]


result = {
    "variant": a.variant,
    "clients": a.clients,
    "window_seconds": round(wall, 3),
    "requests": len(window),
    "errors": errors,
    "output_tokens": tokens,
    "output_tps": round(tokens / wall, 2) if wall else None,
    "requests_per_second": round(len(window) / wall, 3) if wall else None,
    "tokens_per_request": round(tokens / len(window), 2) if window else None,
    "latency_p50_s": pct(latencies, 0.50),
    "latency_p95_s": pct(latencies, 0.95),
    "mean_inflight_requests": round(inflight, 2),
    "new_tokens_per_request": a.new_tokens if a.variant == "rotate" else 0,
    "config": {
        "clients": a.clients,
        "seconds": a.seconds,
        "new_tokens": a.new_tokens,
        "variant": a.variant,
        "fixture": a.fixture,
    },
}
Path(a.out).parent.mkdir(parents=True, exist_ok=True)
Path(a.out).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
print(
    "steady_c32 variant=%s clients=%s window=%.1fs requests=%s errors=%s "
    "out_tokens=%s out_tps=%.2f req_s=%.2f lat_p50=%.3fs lat_p95=%.3fs inflight=%.1f"
    % (
        a.variant,
        a.clients,
        wall,
        len(window),
        errors,
        tokens,
        result["output_tps"] or 0.0,
        result["requests_per_second"] or 0.0,
        result["latency_p50_s"] or 0.0,
        result["latency_p95_s"] or 0.0,
        inflight,
    )
)
