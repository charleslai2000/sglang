#!/usr/bin/env python3
"""Generate/analyze shared-prefix E5M2 fixtures and real HTTP requests."""

import argparse, hashlib, json, os, statistics, time, urllib.request, urllib.error
from pathlib import Path
from transformers import AutoTokenizer

p = argparse.ArgumentParser()
p.add_argument(
    "--action", choices=["fixture", "warm", "batch", "analyze", "evict", "sequence", "pressure_restore"], required=True
)
p.add_argument("--url", default="http://127.0.0.1:31401")
p.add_argument("--fixture", required=True)
p.add_argument("--out", required=True)
p.add_argument("--count", type=int, default=32)
p.add_argument("--prefix-tokens", type=int, default=63488)
p.add_argument("--total-tokens", type=int, default=65536)
p.add_argument("--new-tokens", type=int, default=64)
p.add_argument("--count-override", type=int, default=0)
p.add_argument("--seed", type=int, default=20261120)
p.add_argument("--prompt-file", help="JSON containing requests with rid and input_ids")
p.add_argument("--max-parallel", type=int, default=0)
p.add_argument("--restore-indices", default="")
p.add_argument("--repeat-indices", default="")
a = p.parse_args()
F = Path(a.fixture)
O = Path(a.out)
O.mkdir(parents=True, exist_ok=True)


def post(obj, timeout=3600):
    r = urllib.request.Request(
        a.url + "/generate",
        data=json.dumps(obj).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(r, timeout=timeout) as response:
        return json.loads(response.read())


def prompt(ids, rid, n=None):
    return {
        "rid": rid,
        "input_ids": [ids],
        "sampling_params": {
            "temperature": 0,
            "top_p": 1,
            "max_new_tokens": n or a.new_tokens,
            "min_new_tokens": n or a.new_tokens,
            "ignore_eos": True,
        },
        "return_token_ids": True,
    }


def request_rows():
    if a.prompt_file:
        data = json.loads(Path(a.prompt_file).read_text())
    else:
        data = json.loads(F.read_text())
    rows = data if isinstance(data, list) else data.get("requests", [])
    if a.count_override:
        rows = rows[: a.count_override]
    return rows


def observe():
    for endpoint in ("/metrics", "/get_server_info"):
        try:
            return urllib.request.urlopen(a.url + endpoint, timeout=10).read().decode()
        except Exception:
            pass
    return ""


def one(ids, rid, n=None, attempt_timeout=600):
    t = time.perf_counter()
    try:
        x = post(prompt(ids, rid, n), timeout=attempt_timeout)
        x = x[0] if isinstance(x, list) and len(x) == 1 else x
    except Exception as exc:
        return {"rid": rid, "elapsed_s": time.perf_counter() - t, "error": f"{type(exc).__name__}: {exc}", "meta": {}, "output_ids": [], "ok": False}
    m = x.get("meta_info", {})
    return {
        "rid": m.get("id", rid),
        "elapsed_s": time.perf_counter() - t,
        "output_ids": x.get("output_ids", []),
        "output_text": x.get("text", ""),
        "meta": m,
        "ttft_s": (m.get("first_token_ts", 0) - m.get("request_received_ts", 0)) or None,
        "tpot_s": ((m.get("request_finished_ts", 0) - m.get("first_token_ts", 0)) / max(1, m.get("completion_tokens", len(x.get("output_ids", []))) - 1)) if m.get("first_token_ts") and m.get("request_finished_ts") else None,
        "ok": m.get("completion_tokens", len(x.get("output_ids", [])))
        >= (n or a.new_tokens),
    }


if a.action == "fixture":
    tok = AutoTokenizer.from_pretrained(
        "/data/sglang-hicache/gemma4/model", trust_remote_code=True
    )
    prefix_text = "G1 production readiness deterministic shared KV prefix. This text is repeated verbatim so all requests share precisely the same token IDs.\n"
    unit = tok.encode(prefix_text, add_special_tokens=False)
    base = (unit * ((a.prefix_tokens + len(unit) - 1) // len(unit)))[: a.prefix_tokens]
    assert len(base) == a.prefix_tokens
    rows = []
    for i in range(a.count):
        suffix_text = f"\nIndependent request identifier: client-{i:02d}. Continue this distinct context accurately."
        s = tok.encode(suffix_text, add_special_tokens=False)
        ids = base + s
        if len(ids) < a.total_tokens:
            filler = tok.encode(
                f"Client-{i:02d} private continuation block. ", add_special_tokens=False
            )
            ids += (
                filler * ((a.total_tokens - len(ids) + len(filler) - 1) // len(filler))
            )[: a.total_tokens - len(ids)]
        ids = ids[: a.total_tokens]
        assert ids[: len(base)] == base and len(ids) == a.total_tokens
        rows.append(
            {
                "rid": f"g1sp-{i:02d}",
                "input_ids": ids,
                "prefix_tokens": len(base),
                "suffix_tokens": len(ids) - len(base),
                "prefix_sha256": hashlib.sha256(
                    json.dumps(base, separators=(",", ":")).encode()
                ).hexdigest(),
            }
        )
    d = {
        "fixture_kind": "E5M2_SHARED_PREFIX_64K",
        "tokenizer": "/data/sglang-hicache/gemma4/model",
        "count": len(rows),
        "prefix_tokens": len(base),
        "total_tokens": a.total_tokens,
        "distinct_suffixes": len({tuple(r["input_ids"][len(base) :]) for r in rows}),
        "prefix_sha256": rows[0]["prefix_sha256"],
        "requests": rows,
    }
    assert d["distinct_suffixes"] == a.count
    F.write_text(json.dumps(d, separators=(",", ":")) + "\n")
    print(json.dumps({k: v for k, v in d.items() if k != "requests"}))
elif a.action == "warm":
    d = json.load(open(F))
    r = one(d["requests"][0]["input_ids"], "g1sp-prefix-warm", a.new_tokens)
    (O / "warm.json").write_text(json.dumps(r, indent=2) + "\n")
    (O / "warm-metrics.txt").write_text(observe())
    print(json.dumps({"ok": r["ok"], "elapsed_s": r["elapsed_s"], "meta": r["meta"]}))
elif a.action == "pressure_restore":
    rows = request_rows()
    pressure_n = int(os.environ.get("G1_PRESSURE_NEW_TOKENS", "1"))
    per_request_timeout = int(os.environ.get("G1_REQUEST_TIMEOUT_S", "600"))
    checkpoint_path = O / "pressure_restore.partial.json"
    def checkpoint():
        payload = {"mode": "capacity_pressure_then_restore",
                   "pressure_requests": pressure_results,
                   "restore_requests": restore_results,
                   "repeat_requests": repeat_results,
                   "pressure_wall_s": pressure_wall}
        tmp_path = checkpoint_path.with_suffix(".tmp")
        with open(tmp_path, "w") as stream:
            json.dump(payload, stream, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp_path, checkpoint_path)

    restore_n = int(os.environ.get("G1_RESTORE_NEW_TOKENS", "256"))
    restore_indices = [int(x) for x in (a.restore_indices or os.environ.get("G1_RESTORE_INDICES", "0,1,2")).split(",") if x.strip()]
    pressure_results = []
    restore_results = []
    repeat_results = []
    pressure_wall = None
    repeat_indices = [int(x) for x in a.repeat_indices.split(",") if x.strip()]
    checkpoint()
    # Cold, independent long prompts exercise actual allocator eviction; cap
    # concurrency explicitly so the full device tier turns over predictably.
    from concurrent.futures import ThreadPoolExecutor
    import threading
    gate = threading.Event()
    def pressure_one(item):
        gate.wait()
        return one(item["input_ids"], item["rid"] + "-pressure", pressure_n, per_request_timeout)
    start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=a.max_parallel or 4) as pool:
        futures = [pool.submit(pressure_one, row) for row in rows]
        gate.set()
        for future in futures:
            pressure_results.append(future.result())
            checkpoint()
    pressure_wall = time.perf_counter() - start
    checkpoint()
    for index in restore_indices:
        if not 0 <= index < len(rows):
            raise SystemExit(f"restore index out of range: {index}")
        row = rows[index]
        result = one(row["input_ids"], row["rid"] + "-restore", restore_n, per_request_timeout)
        result["pressure_index"] = index
        restore_results.append(result)
        checkpoint()
    repeat_results = []
    for index in repeat_indices:
        row = rows[index]
        result = one(row["input_ids"], row["rid"] + "-repeat", restore_n, per_request_timeout)
        result["pressure_index"] = index
        repeat_results.append(result)
        checkpoint()
    payload = {"mode":"capacity_pressure_then_restore", "pressure_count":len(pressure_results),
               "pressure_success":sum(bool(r.get("ok")) for r in pressure_results),
               "pressure_wall_s":pressure_wall, "restore_count":len(restore_results),
               "restore_success":sum(bool(r.get("ok")) for r in restore_results),
               "repeat_count":len(repeat_results), "repeat_success":sum(bool(r.get("ok")) for r in repeat_results),
               "pressure_requests":pressure_results,"restore_requests":restore_results,"repeat_requests":repeat_results}
    json.dump(payload, open(O / "pressure_restore.json", "w"), indent=2)
    print(json.dumps({k:payload[k] for k in ("mode","pressure_count","pressure_success","pressure_wall_s","restore_count","restore_success")}))
elif a.action == "sequence":
    data = json.loads(Path(a.prompt_file).read_text()) if a.prompt_file else json.loads(F.read_text())
    steps = data.get("steps", data.get("requests", [])) if isinstance(data, dict) else data
    results = []
    for index, step in enumerate(steps):
        rid = step.get("rid", f"sequence-{index:03d}")
        n = int(step.get("new_tokens", a.new_tokens))
        before = observe()
        started = time.time()
        result = one(step["input_ids"], rid, n)
        after = observe()
        result.update({"phase": step.get("phase", "unspecified"), "sequence_index": index,
                       "started_epoch": started, "metrics_before": before, "metrics_after": after})
        results.append(result)
        json.dump({"mode":"sequential_real_requests", "completed":len(results), "requests":results},
                  open(O / "sequence.partial.json", "w"), indent=2)
    payload = {"mode":"sequential_real_requests", "submitted":len(steps),
               "success":sum(bool(r.get("ok")) for r in results), "requests":results}
    json.dump(payload, open(O / "sequence.json", "w"), indent=2)
    print(json.dumps({k:payload[k] for k in ("mode","submitted","success")}))
elif a.action == "evict":
    rows = request_rows()
    from concurrent.futures import ThreadPoolExecutor
    import threading
    if not rows:
        raise SystemExit("No eviction prompts in fixture")
    gate = threading.Event()
    workers = a.max_parallel or min(a.count, len(rows))
    def evict_one(item):
        gate.wait()
        return one(item["input_ids"], item.get("rid", f"evict-{threading.get_ident()}"), a.new_tokens)
    start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(evict_one, item) for item in rows]
        gate.set()
        results = [future.result() for future in futures]
    elapsed = time.perf_counter() - start
    payload = {
        "mode": "evict_pressure_requests",
        "submitted": len(results),
        "success": sum(bool(item["ok"]) for item in results),
        "wall_s": elapsed,
        "requests": results,
    }
    json.dump(payload, open(O / "evict.json", "w"), indent=2)
    print(json.dumps({k: payload[k] for k in ("mode", "submitted", "success", "wall_s")}))
elif a.action == "batch":
    rows = request_rows()
    import concurrent.futures, threading

    gate = threading.Event()

    def f(x):
        gate.wait()
        return one(x["input_ids"], x["rid"], a.new_tokens)

    t = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=a.max_parallel or a.count) as ex:
        fs = [ex.submit(f, x) for x in rows]
        gate.set()
        rs = [z.result() for z in fs]
    wall = time.perf_counter() - t
    good = [r for r in rs if r["ok"]]
    lat = [r["elapsed_s"] for r in rs]
    ttft = sorted(r["ttft_s"] for r in good if r.get("ttft_s") is not None)
    tpot = sorted(r["tpot_s"] for r in good if r.get("tpot_s") is not None)
    e2e = sorted((r["meta"].get("e2e_latency") or r["elapsed_s"]) for r in good)
    percentile = lambda values, q: values[min(len(values)-1, int(q*(len(values)-1)))] if values else None
    json.dump(
        {
            "count": len(rs),
            "success": len(good),
            "errors": len(rs) - len(good),
            "wall_s": wall,
            "aggregate_output_tps": sum(len(r["output_ids"]) for r in good) / wall,
            "latency_p50_s": statistics.median(lat),
            "latency_p95_s": sorted(lat)[int(0.95 * (len(lat) - 1))],
            "ttft_p50_s": statistics.median(ttft) if ttft else None,
            "ttft_p95_s": percentile(ttft, 0.95),
            "tpot_p50_s": statistics.median(tpot) if tpot else None,
            "tpot_p95_s": percentile(tpot, 0.95),
            "e2e_latency_p50_s": statistics.median(e2e) if e2e else None,
            "e2e_latency_p95_s": percentile(e2e, 0.95),
            "requests": rs,
        },
        open(O / "batch.json", "w"),
        indent=2,
    )
    print(
        json.dumps(
            {
                "count": len(rs),
                "success": len(good),
                "wall_s": wall,
                "aggregate_output_tps": sum(len(r["output_ids"]) for r in good) / wall,
            }
        )
    )
elif a.action == "analyze":
    d = json.load(open(O / "batch.json"))
    logs = Path(a.url).name if False else None
    print(
        json.dumps(
            {
                "success": d["success"],
                "wall_s": d["wall_s"],
                "aggregate_output_tps": d["aggregate_output_tps"],
                "latency_p50_s": d["latency_p50_s"],
                "latency_p95_s": d["latency_p95_s"],
            }
        )
    )
