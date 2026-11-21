#!/usr/bin/env python3
"""Analyse the queued-prefetch waves: per-RID timeline, per-depth statistics, A vs B."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def percentile(values, fraction):
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round(fraction * (len(ordered) - 1)))))
    return ordered[index]


def stats(values):
    values = [value for value in values if value is not None]
    if not values:
        return {"n": 0}
    return {
        "n": len(values),
        "p50": round(percentile(values, 0.50), 4),
        "p95": round(percentile(values, 0.95), 4),
        "p99": round(percentile(values, 0.99), 4),
        "mean": round(sum(values) / len(values), 4),
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
            if record.get("id"):
                records[record["id"]] = record
    return records


def lookup(records: dict[str, dict], rid: str) -> dict:
    if rid in records:
        return records[rid]
    for key, record in records.items():
        if key.startswith(rid + "_"):
            return record
    return {}


def parse_log(server_log: Path):
    states: dict[str, list[dict]] = {}
    hae: dict[str, list[dict]] = {}
    extent: dict[str, list[dict]] = {}
    frontier: dict[str, list[str]] = {}
    dispositions: dict[str, list[str]] = {}
    batches = []
    for line in server_log.read_text(errors="replace").splitlines():
        if line.startswith("[") and " [HAE] " in line:
            stamp = re.search(r"\[(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)\]", line)
            rid_match = re.search(r'"rid": "([^"]+)"', line)
            try:
                payload = json.loads(line.split(" [HAE] ", 1)[1])
            except json.JSONDecodeError:
                payload = {}
            if rid_match:
                hae.setdefault(rid_match.group(1), []).append(
                    {
                        "ts": stamp.group(1) if stamp else None,
                        "requested": payload.get("requested_primary_tokens"),
                        "free_kv": (payload.get("free_units") or {}).get("kv"),
                        "evictable_kv": (payload.get("evictable_units") or {}).get("kv"),
                        "decision": payload.get("decision"),
                    }
                )
            continue
        match = re.search(
            r"evt=(extent_read|restore_disposition|frontier_wait|frontier_wake|restore_backup)\b",
            line,
        )
        rid_match = re.search(r"rid=(\S+)", line)
        ts_match = re.search(r"ts_ms=(\d+)", line)
        if match:
            kind = match.group(1)
            rid = rid_match.group(1) if rid_match else ""
            if kind == "extent_read":
                number = lambda name: int(
                    (re.search(rf"{name}=(-?\d+)", line) or [None, 0])[1]
                )  # noqa: E731
                extent.setdefault(rid, []).append(
                    {
                        "ts_ms": int(ts_match.group(1)) if ts_match else 0,
                        "physical_bytes": number("physical_bytes"),
                        "requested_bytes": number("requested_bytes"),
                        "preads": number("preads"),
                        "keys_n": number("keys_n"),
                    }
                )
            elif kind == "restore_disposition":
                dispositions.setdefault(rid, []).append(
                    line.split("evt=restore_disposition", 1)[1].strip()
                )
            else:
                frontier.setdefault(rid, []).append(
                    line.split(f"evt={kind}", 1)[1].strip()
                )
        state = re.search(r"evt=restore_state\b", line)
        if state and rid_match and ts_match:
            reason = (re.search(r"state=(\w+)\s+reason=(\S+)", line) or [None, "?", "?"])
            states.setdefault(rid_match.group(1), []).append(
                {"ts_ms": int(ts_match.group(1)), "state": reason[1], "reason": reason[2]}
            )
        batch = re.search(r"Decode batch, #running-req: (\d+)", line)
        if batch:
            stamp = re.search(r"\[(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)\]", line)
            batches.append(
                {"n": int(batch.group(1)), "ts": stamp.group(1) if stamp else None}
            )
    return extent, frontier, dispositions, batches, states, hae


def decompose_state_wait(states: list[dict], admission_ms: int | None) -> dict:
    """Attribute the queue wait to restore-state segments.

    `restore_state` events carry wall ms, so consecutive deltas are exact; the
    residual is whatever runs after the last emitted state until admission.
    """
    if not states:
        return {"segments": {}, "observed_s": 0.0, "residual_s": None}
    segments: dict[str, float] = {}
    for index, state in enumerate(states):
        start = state["ts_ms"]
        end = (
            states[index + 1]["ts_ms"]
            if index + 1 < len(states)
            else admission_ms
        )
        if end is None or end < start:
            continue
        key = f"{state['state']}:{state['reason']}"
        segments[key] = round(segments.get(key, 0.0) + (end - start) / 1000.0, 3)
    observed = round((states[-1]["ts_ms"] - states[0]["ts_ms"]) / 1000.0, 3)
    residual = (
        round((admission_ms - states[-1]["ts_ms"]) / 1000.0, 3)
        if admission_ms is not None
        else None
    )
    return {"segments": segments, "observed_s": observed, "residual_s": residual}


def aggregate_wait_decomposition(rows: list[dict]) -> dict:
    totals: dict[str, float] = {}
    residuals = []
    for row in rows:
        for key, value in (row.get("wait_decomposition") or {}).get("segments", {}).items():
            totals[key] = round(totals.get(key, 0.0) + value, 3)
        residual = (row.get("wait_decomposition") or {}).get("residual_s")
        if residual is not None and residual >= 0:
            residuals.append(residual)
    return {
        "requests": len(rows),
        "segment_totals_s": dict(sorted(totals.items(), key=lambda item: -item[1])),
        "residual_s": stats(residuals),
        "host_alloc_wait_lines": sum(len(row.get("host_alloc_waits") or []) for row in rows),
    }


def prefix_dedup(rows: list[dict]) -> dict:
    """Did concurrent requesters share one in-flight prefetch, or read twice?

    A prefix that is prefetched once has exactly one requester with Extent bytes
    and the rest land as L1/L2 hits. Two or more Extent-reading requesters for
    the same prefix means the prefetch was duplicated (or re-issued after the
    first one was revoked).
    """
    by_prefix: dict[int, list[dict]] = {}
    for row in rows:
        if row.get("prefix_index") is None:
            continue
        by_prefix.setdefault(int(row["prefix_index"]), []).append(row)
    table = []
    for prefix, group in sorted(by_prefix.items()):
        ordered = sorted(
            group,
            key=lambda row: (row.get("queue_wait_s") is None, -(row.get("queue_wait_s") or 0.0)),
        )
        readers = [row for row in ordered if (row.get("extent_bytes") or 0) > 0]
        table.append(
            {
                "prefix": prefix,
                "requesters": len(group),
                "extent_readers": len(readers),
                "first_reader_rid": readers[0]["rid"] if readers else None,
                "first_reader_bytes": readers[0]["extent_bytes"] if readers else 0,
                "later_requesters_l1_or_l2": sum(
                    1
                    for row in ordered
                    if row is not (readers[0] if readers else None)
                    and row.get("cached_tokens_details")
                    and ((row["cached_tokens_details"].get("device") or 0)
                         + (row["cached_tokens_details"].get("host") or 0)) > 0
                ),
                "host_alloc_wait_requesters": sum(
                    1 for row in ordered if row.get("host_alloc_waits")
                ),
            }
        )
    return {
        "prefixes": table,
        "extent_readers_total": sum(item["extent_readers"] for item in table),
        "requesters_total": sum(item["requesters"] for item in table),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True)
    parser.add_argument("--server-log", default=None)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()
    run = Path(args.run)
    out = Path(args.out) if args.out else run / "analysis"
    out.mkdir(parents=True, exist_ok=True)

    server_log = Path(args.server_log) if args.server_log else run / "server.log"
    metrics_dir = run / "service" / "request-metrics"
    if not metrics_dir.exists():
        metrics_dir = run / "request-metrics"
    metrics = load_metrics(metrics_dir)
    extent, frontier, dispositions, batches, states, hae = parse_log(server_log)

    waves = sorted(run.glob("wave-*.json"))
    report = {"run": str(run), "depths": []}
    for path in waves:
        wave = json.loads(path.read_text())
        depth = wave["depth"]
        rows = []
        for client in wave["queue"]:
            rid = client["rid"]
            record = lookup(metrics, rid)
            telemetry = record.get("hicache_telemetry") or {}
            stages = telemetry.get("stage_latency_seconds") or {}
            reads = extent.get(rid, [])
            io_span = (
                (max(r["ts_ms"] for r in reads) - min(r["ts_ms"] for r in reads))
                / 1000.0
                if len(reads) > 1
                else 0.0
            )
            received = record.get("request_received_ts")
            forward = record.get("forward_entry_time")
            prefill_done = record.get("prefill_finished_time")
            first_token = record.get("first_token_ts")
            finished = record.get("request_finished_ts")
            tokens = record.get("completion_tokens") or 0
            row = {
                "rid": rid,
                "ok": client.get("ok"),
                "prompt_tokens": record.get("prompt_tokens"),
                "completion_tokens": tokens,
                "cached_tokens_details": record.get("cached_tokens_details"),
                # wall-clock segments (seconds), all anchored at ingress
                "queue_wait_s": round(forward - received, 4)
                if received and forward
                else None,
                "prefill_s": round(prefill_done - forward, 4)
                if forward and prefill_done
                else None,
                "decode_s": round(finished - prefill_done, 4)
                if prefill_done and finished
                else None,
                "ttft_s": round(first_token - received, 4)
                if received and first_token
                else None,
                "e2e_s": record.get("e2e_latency"),
                "tpot_ms": round(
                    (finished - first_token) * 1000.0 / max(1, tokens - 1), 3
                )
                if first_token and finished
                else None,
                # hicache telemetry
                "storage_query_s": stages.get("storage_query"),
                "prefetch_to_ready_s": stages.get("prefetch_to_ready"),
                "ready_to_admission_s": stages.get("ready_to_admission"),
                "admission_to_prefill_finish_s": stages.get(
                    "admission_to_prefill_finish"
                ),
                "rh_prefetch_lead_s": telemetry.get("rh_prefetch_lead_seconds"),
                "rh_ready_slack_s": telemetry.get("rh_ready_slack_seconds"),
                "l3_tokens": telemetry.get("l3_tokens"),
                "l2_tokens": telemetry.get("l2_tokens"),
                "l1_tokens": telemetry.get("l1_tokens"),
                "prefetch_origin": telemetry.get("prefetch_origin"),
                "outcome": telemetry.get("outcome"),
                # real disk I/O
                "extent_io_s": round(io_span, 4),
                "extent_bytes": sum(r["physical_bytes"] for r in reads),
                "extent_preads": sum(r["preads"] for r in reads),
                "extent_keys": sum(r["keys_n"] for r in reads),
                "dispositions": dispositions.get(rid, [])[:4],
                "frontier_wait": len(frontier.get(rid, [])) if rid in frontier else 0,
                "prefix_index": client.get("prefix_index"),
                "restore_states": states.get(rid, [])[:16],
                "host_alloc_waits": hae.get(rid, [])[:8],
            }
            # Mechanism A is an *outcome*: an L3 lookup ran, physical bytes were
            # read from the Extent, and the data reached Host before GPU
            # admission. l3_tokens is 0 once the prefetch lands the prefix in
            # L1/L2, so it cannot be the discriminator.
            row["mechanism"] = (
                "A_prefetched_to_l2"
                if row["storage_query_s"] is not None
                and row["extent_bytes"] > 0
                and (row["ready_to_admission_s"] or 0) > 0
                else (
                    "B_frontier_wait"
                    if row["frontier_wait"]
                    else ("timeout_bound" if (row["queue_wait_s"] or 0) > 590 else "recompute_or_other")
                )
            )
            row["wait_decomposition"] = decompose_state_wait(
                row["restore_states"],
                int(round(forward * 1000)) if forward else None,
            )
            rows.append(row)

        def column(name):
            return [row[name] for row in rows if row.get(name) is not None]

        ready_lead = [
            row["ready_to_admission_s"]
            for row in rows
            if row["ready_to_admission_s"] is not None
        ]
        window = max(1e-9, (wave.get("queue_finished_at") or 0.0) - (wave.get("queue_submitted_at") or 0.0))
        output_tps = round(sum(row["completion_tokens"] or 0 for row in rows) / window, 2)
        depth_report = {
            "depth": depth,
            "requests": len(rows),
            "ok": sum(1 for row in rows if row["ok"]),
            "running_seen_before_queue": wave.get("running_seen_before_queue"),
            "wave_wall_s": wave.get("wave_wall_s"),
            "l3_io_s": stats(column("extent_io_s")),
            "l3_bytes": stats(column("extent_bytes")),
            "l3_preads": stats(column("extent_preads")),
            "storage_query_s": stats(column("storage_query_s")),
            "host_ready_s": stats(column("prefetch_to_ready_s")),
            "ready_to_admission_s": stats(ready_lead),
            "host_ready_ahead_of_admission": {
                "count": sum(1 for value in ready_lead if value > 0),
                "fraction": round(
                    sum(1 for value in ready_lead if value > 0) / len(ready_lead), 4
                )
                if ready_lead
                else None,
            },
            "queue_wait_s": stats(column("queue_wait_s")),
            "prefill_s": stats(column("prefill_s")),
            "decode_s": stats(column("decode_s")),
            "admission_to_prefill_finish_s": stats(
                column("admission_to_prefill_finish_s")
            ),
            "ttft_s": stats(column("ttft_s")),
            "tpot_ms": stats(column("tpot_ms")),
            "e2e_s": stats(column("e2e_s")),
            "output_tps": output_tps,
            "l3_lookup_requests": sum(1 for row in rows if row["storage_query_s"] is not None),
            "extent_read_requests": sum(1 for row in rows if row["extent_bytes"] > 0),
            "timeout_bound_requests": sum(1 for row in rows if (row["queue_wait_s"] or 0) > 590),
            "frontier_events": sum(row["frontier_wait"] for row in rows),
            "mechanism_a": sum(
                1 for row in rows if row["mechanism"] == "A_prefetched_to_l2"
            ),
            "mechanism_b": sum(
                1 for row in rows if row["mechanism"] == "B_frontier_wait"
            ),
            "recompute_or_other": sum(
                1 for row in rows if row["mechanism"] == "recompute_or_other"
            ),
            "capacity": {"before": wave.get("before"), "after": wave.get("after")},
            "queue_depth_seen": wave.get("queue_depth_seen"),
            "churn_settle": wave.get("churn_settle"),
            "host_free_tokens_before": wave.get("host_free_tokens_before"),
            "t13_fallback_ratio": round(
                sum(1 for row in rows if (row["queue_wait_s"] or 0) > 590) / max(1, len(rows)), 4
            ),
            "prefetch_origins": {
                str(origin): sum(1 for row in rows if row["prefetch_origin"] == origin)
                for origin in {row["prefetch_origin"] for row in rows}
            },
            "wait_decomposition": aggregate_wait_decomposition(
                [row for row in rows if (row["queue_wait_s"] or 0) > 590]
            ),
            "prefix_dedup": prefix_dedup(rows),
        }
        report["depths"].append({"summary": depth_report, "rows": rows})

    all_batches = batches
    report["decode_batch_distribution"] = {
        "samples": len(all_batches),
        "histogram": {
            str(n): sum(1 for b in all_batches if b["n"] == n)
            for n in sorted({b["n"] for b in all_batches})
        },
        "max": max((b["n"] for b in all_batches), default=None),
    }
    (out / "queue-prefetch.json").write_text(
        json.dumps(report, indent=2, sort_keys=True)
    )

    lines = ["# Queued prefetch experiment", "", f"Run: `{run.name}`", ""]
    for entry in report["depths"]:
        summary = entry["summary"]
        lines += [
            f"## depth {summary['depth']}",
            "",
            f"- requests {summary['requests']} (ok {summary['ok']}), active seen before queue {summary['running_seen_before_queue']}, wall {summary['wave_wall_s']} s",
            f"- real queue depth seen {summary['queue_depth_seen']}, Host free tokens at wave start {summary['host_free_tokens_before']}",
            f"- prefetch origins {summary['prefetch_origins']}",
            f"- mechanism A {summary['mechanism_a']} / B {summary['mechanism_b']} / other {summary['recompute_or_other']}, T13 fallback ratio {summary['t13_fallback_ratio']}",
            f"- wait decomposition (timeout-bound): {summary['wait_decomposition']}",
            f"- prefix dedup: {summary['prefix_dedup']['extent_readers_total']} Extent readers over {summary['prefix_dedup']['requesters_total']} requesters",
            f"- L3 lookups {summary['l3_lookup_requests']}, Extent-reading requests {summary['extent_read_requests']}, timeout-bound {summary['timeout_bound_requests']}, frontier events {summary['frontier_events']}",
            f"- L3 I/O s: {summary['l3_io_s']}",
            f"- L3 bytes: {summary['l3_bytes']}",
            f"- storage query s: {summary['storage_query_s']}",
            f"- Host-ready s: {summary['host_ready_s']}",
            f"- Host-ready ahead of admission: {summary['host_ready_ahead_of_admission']} of {summary['ready_to_admission_s']}",
            f"- queue wait s: {summary['queue_wait_s']}",
            f"- prefill s: {summary['prefill_s']}, decode s: {summary['decode_s']}",
            f"- TTFT s: {summary['ttft_s']}, TPOT ms: {summary['tpot_ms']}, E2E s: {summary['e2e_s']}",
            f"- capacity before: {summary['capacity']['before']}",
            f"- capacity after: {summary['capacity']['after']}",
            "",
        ]
    (out / "QUEUE-PREFETCH.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
