#!/usr/bin/env python3
"""Queued-prefetch experiment: 32 active requests + N waiting, N = 64/128/256.

Reuses the existing evidence machinery rather than adding a profiling stack:

  * `run_radix_tree_lifecycle.snapshot` for /metrics and /server_info watermarks,
  * the service's own per-request metrics export (`--export-metrics-to-file`) for
    the RID timeline -- request_received_ts, forward_entry_time, queue_time,
    prefill_finished_time, first_token_ts, request_finished_ts and the
    hicache_telemetry mono_ns chain (enqueue, prefetch_issue, storage_query,
    ready, admission, prefill_finish),
  * the [P2A]/[P3] event log for extent_read bytes/preads and frontier events.

Every staged queue request uses one of eight 4,096-token prefixes (2,048-token
shared ancestor + 2,048-token branch suffix) and is repeated across the queue, so
prefix reuse is real; a unique 32-token tail keeps per-request prefill non-zero.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import random
import re
import statistics
import threading
import time
import urllib.request
from pathlib import Path

RUNS = "/home/ubuntu/workspaces/3rdparty/sglang-hicache/control/gemma4-g1-hicache-tier-lifecycle-20261119/runs"
_spec = importlib.util.spec_from_file_location(
    "g1_lifecycle", f"{RUNS}/run_radix_tree_lifecycle.py"
)
g1 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(g1)


def post(url: str, path: str, payload, timeout: float = 3600.0) -> dict:
    data = None if payload is None else json.dumps(payload).encode()
    request = urllib.request.Request(
        url + path, data=data, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read().decode(errors="replace")
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return {"text": body.strip()}


def flush_cache(url: str, timeout_s: float = 180.0) -> dict:
    """POST with an empty body, `?timeout=` as a query parameter (repo helper)."""
    started = time.time()
    record = g1.flush_radix_cache(url, timeout_s)
    record["epoch"] = started
    record["seconds"] = round(time.time() - started, 2)
    return record


def get_json(url: str, path: str, timeout: float = 60.0) -> dict:
    with urllib.request.urlopen(url + path, timeout=timeout) as response:
        return json.loads(response.read())


def generate(
    url: str,
    rid: str,
    input_ids: list[int],
    max_new_tokens: int,
    timeout: float = 3600.0,
) -> dict:
    started = time.time()
    try:
        reply = post(
            url,
            "/generate",
            {
                "input_ids": input_ids,
                "rid": rid,
                "sampling_params": {
                    "max_new_tokens": max_new_tokens,
                    "temperature": 0.0,
                    "ignore_eos": True,
                },
            },
            timeout=timeout,
        )
    except Exception as error:  # noqa: BLE001
        return {
            "rid": rid,
            "ok": False,
            "error": f"{type(error).__name__}: {error}",
            "client_start": started,
            "client_end": time.time(),
        }
    meta = reply.get("meta_info", {})
    return {
        "rid": rid,
        "ok": True,
        "client_start": started,
        "client_end": time.time(),
        "completion_tokens": meta.get("completion_tokens"),
        "cached_tokens_details": meta.get("cached_tokens_details") or {},
    }


def build_tokens(rng: random.Random, count: int) -> list[int]:
    return [rng.randrange(1000, 30000) for _ in range(count)]


def fixtures(branches: int, prefix: int, suffix: int, tail: int) -> list[dict]:
    """Shared ancestor + disjoint branch suffixes, deterministic per branch."""
    rng = random.Random(20261121)
    root = build_tokens(rng, prefix)
    rows = []
    for branch in range(branches):
        body = root + build_tokens(random.Random(5000 + branch), suffix)
        rows.append({"branch": branch, "prefix": body, "tail_seed": 9000 + branch})
    return rows


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round(fraction * (len(ordered) - 1)))))
    return ordered[index]


def stats(values: list[float]) -> dict:
    if not values:
        return {"n": 0}
    return {
        "n": len(values),
        "p50": round(percentile(values, 0.50), 4),
        "p95": round(percentile(values, 0.95), 4),
        "p99": round(percentile(values, 0.99), 4),
        "mean": round(statistics.fmean(values), 4),
        "max": round(max(values), 4),
    }


def load_metrics(metrics_dir: Path) -> dict[str, dict]:
    records = {}
    for path in sorted(metrics_dir.glob("*.log")):
        for line in path.read_text(errors="replace").splitlines():
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            rid = record.get("id")
            if rid:
                records[rid] = record
    return records


def parse_extent(server_log: Path) -> dict[str, list[dict]]:
    per_rid: dict[str, list[dict]] = {}
    for line in server_log.read_text(errors="replace").splitlines():
        if "evt=extent_read" not in line:
            continue
        rid = (re.search(r"rid=(\S+)", line) or [None, ""])[1]
        ts = int((re.search(r"ts_ms=(\d+)", line) or [None, 0])[1])
        field = lambda name: int((re.search(rf"{name}=(-?\d+)", line) or [None, 0])[1])  # noqa: E731
        per_rid.setdefault(rid, []).append(
            {
                "ts_ms": ts,
                "physical_bytes": field("physical_bytes"),
                "requested_bytes": field("requested_bytes"),
                "preads": field("preads"),
                "keys_n": field("keys_n"),
            }
        )
    return per_rid


def _pending_of(info: dict) -> dict:
    """`g1_p0_hicache_pending` lives under internal_states[0], not top level."""
    states = info.get("internal_states") or []
    if not states:
        return {}
    return states[0].get("g1_p0_hicache_pending") or {}


def wait_backup_settled(url: str, budget: float, log: Path) -> dict:
    deadline = time.time() + budget
    last = None
    while time.time() < deadline:
        info = get_json(url, "/server_info")
        pending = _pending_of(info)
        last = pending
        if not pending.get("backup"):
            return {
                "settled": True,
                "pending": pending,
                "waited_s": round(budget - (deadline - time.time()), 1),
            }
        time.sleep(5)
    return {"settled": False, "pending": last, "waited_s": budget}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:31401")
    parser.add_argument("--metrics-dir", required=True)
    parser.add_argument("--extent-dir", required=True)
    parser.add_argument("--server-log", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--depths", default="64,128,256")
    parser.add_argument("--active", type=int, default=32)
    parser.add_argument("--active-context", type=int, default=512)
    parser.add_argument("--active-output", type=int, default=512)
    parser.add_argument("--queue-output", type=int, default=64)
    parser.add_argument("--branches", type=int, default=8)
    parser.add_argument("--prefix-tokens", type=int, default=2048)
    parser.add_argument("--suffix-tokens", type=int, default=2048)
    parser.add_argument("--tail-tokens", type=int, default=32)
    parser.add_argument("--churn-tokens", type=int, default=131072)
    parser.add_argument("--flush-before-wave", action="store_true",
                        help="use /flush_cache to put the chain in an L3-only state "
                             "with full Host headroom instead of churning Host full")
    parser.add_argument("--start-profile", action="store_true")
    parser.add_argument("--stop-profile", action="store_true")
    parser.add_argument("--profile-seconds", type=float, default=0.0)
    parser.add_argument("--backup-budget", type=float, default=420.0)
    args = parser.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    server_log = Path(args.server_log)
    metrics_dir = Path(args.metrics_dir)
    depths = [int(value) for value in args.depths.split(",")]
    rows = fixtures(
        args.branches, args.prefix_tokens, args.suffix_tokens, args.tail_tokens
    )

    waves = []
    bootstrap = {"capacity": g1.snapshot(args.url, out, "baseline", Path(args.extent_dir))}

    # 1. Make the eight branch prefixes L3-durable.
    seeds = []
    for row in rows:
        seeds.append(generate(args.url, f"qp-seed-{row['branch']}", row["prefix"], 1))
    bootstrap["seed"] = seeds
    bootstrap["seed_settle"] = wait_backup_settled(
        args.url, args.backup_budget, server_log
    )

    (out / "bootstrap.json").write_text(
        json.dumps(bootstrap, indent=2, sort_keys=True, default=str)
    )

    for depth in depths:
        # 2. Re-churn device + host before every wave: after a wave the eight
        # prefixes are resident again, and an L3-only start is what makes this a
        # queued-prefetch measurement rather than an L1/L2 hit test.
        flush_record = None
        if args.flush_before_wave:
            # /flush_cache clears L1+L2; the Extent keeps the durability. This is
            # the only way to get "L3 only" together with free Host staging,
            # because evicting the chain out of the Host pool by churn requires
            # filling that pool (it is only 46,748 tokens larger than the device).
            flush_record = flush_cache(args.url, 180.0)
            flatten = g1.snapshot(args.url, out, f"after_flush_{depth}", Path(args.extent_dir))
        churn = []
        chunk = args.churn_tokens // 3
        for index in range(3):
            if args.flush_before_wave:
                break
            ids = build_tokens(random.Random(70000 + depth * 10 + index), chunk)
            churn.append(generate(args.url, f"qp-churn-{depth}-{index}", ids, 1))
        churn_settle = wait_backup_settled(
            args.url, args.backup_budget, server_log
        )
        wave_started = time.time()
        before = g1.snapshot(args.url, out, f"before_wave_{depth}", Path(args.extent_dir))

        active_records: list[dict] = []
        active_threads = []
        rng = random.Random(40000 + depth)
        for index in range(args.active):
            ids = build_tokens(rng, args.active_context)
            thread = threading.Thread(
                target=lambda i=index, ids=ids: active_records.append(
                    generate(
                        args.url, f"qp-active-{depth}-{i}", ids, args.active_output
                    )
                )
            )
            thread.start()
            active_threads.append(thread)

        # Submit the queue only once the active set actually occupies the slots.
        # /server_info exposes server args, not live counters: the scheduler's own
        # "Decode batch, #running-req: N" line is the authoritative active count.
        running_seen = 0
        for _ in range(600):
            match = None
            with server_log.open("rb") as stream:
                stream.seek(0, 2)
                stream.seek(max(0, stream.tell() - 200_000))
                tail = stream.read().decode(errors="replace")
            for line in tail.splitlines()[::-1]:
                match = re.search(r"#running-req: (\d+)", line)
                if match:
                    break
            running = int(match.group(1)) if match else 0
            running_seen = max(running_seen, running)
            if running >= max(1, args.active - 4):
                break
            time.sleep(0.5)

        if args.start_profile:
            # Only cudaProfilerStart/Stop: torch profiler activities would add
            # its own overhead and traces on top of the nsys capture range.
            try:
                profile_start_epoch = time.time()
                post(args.url, "/start_profile", {"activities": ["CUDA_PROFILER"]})
                profile_started = profile_start_epoch
            except Exception as error:  # noqa: BLE001
                profile_started = f"{type(error).__name__}: {error}"
        else:
            profile_started = None
        queue_records: list[dict] = []
        queue_threads = []
        queue_submitted = time.time()
        for index in range(depth):
            row = rows[index % len(rows)]
            tail = build_tokens(
                random.Random(row["tail_seed"] * 1000 + index), args.tail_tokens
            )
            ids = row["prefix"] + tail
            prefix_index = row["branch"]
            thread = threading.Thread(
                target=lambda i=index, ids=ids, p=prefix_index: queue_records.append(
                    dict(
                        generate(args.url, f"qp-queue-{depth}-{i}", ids, args.queue_output),
                        prefix_index=p,
                    )
                )
            )
            thread.start()
            queue_threads.append(thread)

        for thread in queue_threads:
            thread.join()
        queue_finished = time.time()
        for thread in active_threads:
            thread.join()
        active_finished = time.time()
        if args.stop_profile and args.profile_seconds:
            def _stop_later(seconds: float) -> None:
                time.sleep(seconds)
                try:
                    stop_epoch = time.time()
                    post(args.url, "/stop_profile", {}, timeout=900.0)
                    (out / f"profile-{depth}.json").write_text(
                        json.dumps({"start_epoch": profile_started, "stop_epoch": stop_epoch,
                                    "limit_s": seconds}, indent=2)
                    )
                except Exception as error:  # noqa: BLE001
                    print(f"stop_profile (timer) failed: {error}", flush=True)

            threading.Thread(target=_stop_later, args=(args.profile_seconds,), daemon=True).start()
        elif args.stop_profile:
            try:
                profile_stop_epoch = time.time()
                post(args.url, "/stop_profile", {}, timeout=900.0)
                (out / f"profile-{depth}.json").write_text(
                    json.dumps(
                        {"start_epoch": profile_started, "stop_epoch": profile_stop_epoch},
                        indent=2,
                    )
                )
            except Exception as error:  # noqa: BLE001
                print(f"stop_profile failed: {error}", flush=True)
        after = g1.snapshot(args.url, out, f"after_wave_{depth}", Path(args.extent_dir))
        queue_depth_seen = 0
        for line in server_log.read_text(errors="replace").splitlines()[::-1]:
            match = re.search(r"#queue-req: (\d+)", line)
            if match:
                queue_depth_seen = max(queue_depth_seen, int(match.group(1)))

        wave = {
            "depth": depth,
            "running_seen_before_queue": running_seen,
            "queue_depth_seen": queue_depth_seen,
            "flush_before_wave": flush_record,
            "after_flush": flatten if args.flush_before_wave else None,
            "profile_started": profile_started,
            "queue_submitted_at": queue_submitted,
            "queue_finished_at": queue_finished,
            "active_finished_at": active_finished,
            "wave_wall_s": round(active_finished - wave_started, 2),
            "churn": [{"rid": record["rid"], "ok": record.get("ok")} for record in churn],
            "churn_settle": churn_settle,
            "before": before.get("pool_capacities"),
            "host_free_tokens_before": (
                (before.get("pool_capacities") or {}).get("sglang:hicache_host_total_tokens", 0)
                - (before.get("pool_capacities") or {}).get("sglang:hicache_host_used_tokens", 0)
            ),
            "after": after.get("pool_capacities"),
            "queue": [
                {k: v for k, v in record.items() if k != "error"}
                | {"ok": record.get("ok")}
                for record in queue_records
            ],
            "active_summary": {
                "n": len(active_records),
                "ok": sum(1 for record in active_records if record.get("ok")),
                "tokens": sum(
                    record.get("completion_tokens") or 0 for record in active_records
                ),
            },
        }
        waves.append(wave)
        (out / f"wave-{depth}.json").write_text(
            json.dumps(
                {**wave, "active": active_records},
                indent=2,
                sort_keys=True,
                default=str,
            )
        )
        print(
            f"wave depth={depth} running_seen={running_seen} queue_wall={queue_finished - queue_submitted:.1f}s",
            flush=True,
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
