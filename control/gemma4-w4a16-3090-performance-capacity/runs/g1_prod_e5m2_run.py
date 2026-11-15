#!/usr/bin/env python3
"""E5M2-only online production-readiness workload driver."""

import argparse, concurrent.futures, json, random, statistics, threading, time, urllib.request
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument("--url", required=True)
p.add_argument("--out", required=True)
p.add_argument(
    "--kind", choices=["bench", "cache", "cancel", "mixed", "stress"], required=True
)
p.add_argument("--concurrency", type=int, default=1)
p.add_argument("--seconds", type=int, default=0)
p.add_argument("--prefix-fixture")
p.add_argument("--short-fixture")
p.add_argument("--long-fixture")
p.add_argument("--new-tokens", type=int, default=128)
p.add_argument("--stream", action="store_true")
p.add_argument("--rate", type=float, default=0.0)
p.add_argument("--prompt-len", type=int, default=64)
a = p.parse_args()
O = Path(a.out)
O.mkdir(parents=True, exist_ok=True)
rng = random.Random(2026111515)
rows = []


def body(ids, n, rid):
    return {
        "rid": rid,
        "input_ids": [ids],
        "sampling_params": {
            "temperature": 0,
            "top_p": 1,
            "max_new_tokens": n,
            "min_new_tokens": n,
            "ignore_eos": True,
        },
        "return_token_ids": True,
    }


def post(url, obj, timeout=3600):
    r = urllib.request.Request(
        url, data=json.dumps(obj).encode(), headers={"Content-Type": "application/json"}
    )
    return urllib.request.urlopen(r, timeout=timeout)


def req(ids, n, rid, stream=False):
    t = time.perf_counter()
    first = None
    if stream:
        obj = {
            "model": "gemma4",
            "prompt": ids,
            "max_tokens": n,
            "min_tokens": n,
            "temperature": 0,
            "top_p": 1,
            "stream": True,
            "return_token_ids": True,
            "ignore_eos": True,
            "stop": [],
        }
        resp = post(a.url + "/v1/completions", obj)
        chunks = []
        for line in resp:
            if line.startswith(b"data: ") and line.strip() != b"data: [DONE]":
                c = json.loads(line[6:])
                if first is None and c.get("choices"):
                    first = time.perf_counter() - t
                chunks.append(c)
        x = chunks[-1] if chunks else {}
        out = [
            v
            for c in chunks
            for v in (c.get("choices", [{}])[0].get("token_ids") or [])
        ]
        m = {}
    else:
        x = json.loads(post(a.url + "/generate", body(ids, n, rid)).read())
        x = x[0] if isinstance(x, list) and len(x) == 1 else x
        out = x.get("output_ids", [])
        m = x.get("meta_info", {})
    return {
        "ok": len(out) >= n,
        "elapsed_s": time.perf_counter() - t,
        "ttft_s": first,
        "output_len": len(out),
        "output_ids": out,
        "meta": m,
        "response": x,
    }


def load(path):
    return json.load(open(path))


if a.kind == "bench":
    gate = threading.Event()
    fixture = [rng.randrange(3, 262143) for _ in range(a.prompt_len)]
    for rr in range(a.seconds if a.seconds else 2):
        t = time.perf_counter()

        def f(i):
            gate.wait()
            return req(
                fixture + [i],
                a.new_tokens,
                f"bench-c{a.concurrency}-r{rr}-{i}",
                a.stream,
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=a.concurrency) as ex:
            fs = [ex.submit(f, i) for i in range(a.concurrency)]
            gate.set()
            rs = [z.result() for z in fs]
        wall = time.perf_counter() - t
        good = [x for x in rs if x["ok"]]
        tt = [x["ttft_s"] for x in good if x["ttft_s"] is not None]
        tpot = [
            (x["elapsed_s"] - x["ttft_s"]) / max(1, x["output_len"] - 1)
            for x in good
            if x["ttft_s"] is not None
        ]
        rows.append(
            {
                "concurrency": a.concurrency,
                "round": rr,
                "requests": rs,
                "success": len(good),
                "errors": len(rs) - len(good),
                "wall_s": wall,
                "aggregate_tps": sum(x["output_len"] for x in good) / wall,
                "ttft_p50_s": statistics.median(tt) if tt else None,
                "ttft_p95_s": sorted(tt)[min(len(tt) - 1, int(0.95 * len(tt)))]
                if tt
                else None,
                "tpot_p50_s": statistics.median(tpot) if tpot else None,
            }
        )
elif a.kind == "cache":
    f = load(a.prefix_fixture)
    prefix = f["prefix_ids"]
    ss = f.get("suffixes", {})
    ss = list(ss.values()) if isinstance(ss, dict) else ss
    prom = f.get("prompts", {})
    prom = list(prom.values()) if isinstance(prom, dict) else prom
    stages = [
        ("cold-prefix", prefix + ss[0]),
        ("exact-repeat", prefix + ss[0]),
        ("partial-prefix", prefix[: len(prefix) // 2] + ss[1]),
        ("evict-0", prom[0]),
        ("evict-1", prom[1]),
        ("evict-2", prom[2]),
        ("evict-3", prom[3]),
        ("recompute", prefix + ss[0]),
    ]
    for name, ids in stages:
        rows.append({"stage": name, "request": req(ids, 32, name)})
elif a.kind == "cancel":
    f = load(a.long_fixture)
    prom = f["prompts"]
    ids = next(iter(prom.values())) if isinstance(prom, dict) else prom[0]
    result = {}

    def go():
        obj = {
            "model": "gemma4",
            "prompt": ids,
            "max_tokens": 512,
            "temperature": 0,
            "top_p": 1,
            "stream": True,
            "return_token_ids": True,
            "ignore_eos": True,
            "stop": [],
        }
        r = post(a.url + "/v1/completions", obj)
        first = False
        try:
            for line in r:
                if line.startswith(b"data: ") and line.strip() != b"data: [DONE]":
                    c = json.loads(line[6:])
                    first = True
                    result["stream_finished_reason"] = c.get("choices", [{}])[0].get(
                        "finish_reason"
                    )
        except Exception as e:
            result["stream_error"] = repr(e)
        result["got_first_chunk"] = first

    th = threading.Thread(target=go)
    th.start()
    time.sleep(2)
    result["abort_http_status"] = post(
        a.url + "/abort_request", {"abort_all": True}, 30
    ).status
    th.join(180)
    result["stream_thread_alive"] = th.is_alive()
    time.sleep(3)
    rows.append(result)
elif a.kind == "mixed":
    deadline = time.monotonic() + a.seconds
    short = load(a.short_fixture)
    long = load(a.long_fixture)
    s = short.get("prompts", [])
    l = long.get("prompts", [])
    s = list(s.values()) if isinstance(s, dict) else s
    l = list(l.values()) if isinstance(l, dict) else l
    failed = threading.Event()

    def worker(w):
        k = 0
        while time.monotonic() < deadline and not failed.is_set():
            cycle_start = time.monotonic()
            ids = l[(w + k) % len(l)] if k % 5 == 0 else s[(w + k) % len(s)]
            try:
                z = req(ids, 64, f"mix-{w}-{k}")
                rows.append(
                    {
                        "worker": w,
                        "iter": k,
                        "input_len": len(ids),
                        "ok": z["ok"],
                        "elapsed_s": z["elapsed_s"],
                        "meta": z["meta"],
                    }
                )
            except Exception as e:
                rows.append(
                    {
                        "worker": w,
                        "iter": k,
                        "input_len": len(ids),
                        "ok": False,
                        "error": repr(e),
                    }
                )
                failed.set()
            if a.rate > 0:
                time.sleep(max(0, 1 / a.rate - (time.monotonic() - cycle_start)))
            k += 1

    with concurrent.futures.ThreadPoolExecutor(max_workers=a.concurrency) as ex:
        list(ex.map(worker, range(a.concurrency)))
elif a.kind == "stress":
    deadline = time.monotonic() + a.seconds
    k = 0
    while time.monotonic() < deadline:
        ids = [rng.randrange(3, 262143) for _ in range(1024 if k % 5 == 0 else 128)]
        z = req(ids, 32, f"stress-{k}")
        rows.append(
            {
                "ok": z["ok"],
                "elapsed_s": z["elapsed_s"],
                "input_len": len(ids),
                "meta": z["meta"],
            }
        )
        k += 1
(O / "results.json").write_text(json.dumps(rows, indent=2) + "\n")
print(
    json.dumps(
        {
            "kind": a.kind,
            "records": len(rows),
            "errors": sum(x.get("ok") is False for x in rows),
            "out": str(O / "results.json"),
        }
    )
)
