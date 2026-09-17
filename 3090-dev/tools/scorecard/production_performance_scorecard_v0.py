#!/usr/bin/env python3
"""Read-only extraction of the C32 v3 and closure-soak scorecard.

This is report tooling only.  It reads the already-existing phase7 artifacts and
request-metrics logs; it does not contact the server, start a workload, or
modify production files.  The generated scorecard JSON is written to the
authorized phase7 artifact directory and the markdown report to .memory/work.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import pathlib
import re
import statistics
from collections import Counter


ROOT = pathlib.Path("/var/log/sglang/local-prod-v1")
PHASE7 = ROOT / "phase7"
REPO = pathlib.Path(__file__).resolve().parents[1]
REPORT_DIR = REPO / ".memory" / "work"
SCORECARD_PATH = PHASE7 / "PRODUCTION-PERFORMANCE-SCORECARD-v0.json"
REPORT_PATH = REPORT_DIR / "PRODUCTION-PERFORMANCE-SCORECARD-v0.md"

V3_FINAL = PHASE7 / "c32v3_final.json"
V3_REQUESTS = PHASE7 / "c32v3_requests.jsonl"
V3_SAMPLES = PHASE7 / "c32v3_samples.jsonl"
CLOSURE_SUMMARY = PHASE7 / "c32closure_20260916_summary.json"
CLOSURE_FINAL = PHASE7 / "c32closure_20260916_final.json"
CLOSURE_POSTDRAIN = PHASE7 / "c32closure_20260916_postdrain.json"
CLOSURE_REQUESTS = PHASE7 / "c32closure_20260916_requests.jsonl"
CLOSURE_SAMPLES = PHASE7 / "c32closure_20260916_samples.jsonl"
REQUEST_LOGS = [
    ROOT / "sglang-request-metrics-20260916_00.log",
    ROOT / "sglang-request-metrics-20260916_01.log",
    ROOT / "sglang-request-metrics-20260916_02.log",
]

V3_SESSION_RE = re.compile(r"\[session \d+ turn \d+\]")
CLOSURE_RE = re.compile(r"C32CLOSURE sid=\d+ turn=\d+")


def sha256(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def load_json(path: pathlib.Path):
    with path.open() as f:
        return json.load(f)


def load_jsonl(path: pathlib.Path):
    rows = []
    with path.open() as f:
        for line_no, line in enumerate(f, 1):
            rows.append((line_no, json.loads(line)))
    return rows


def percentile(values, q):
    values = sorted(values)
    if not values:
        return None
    return values[min(len(values) - 1, max(0, math.ceil(q * len(values)) - 1))]


def numeric_stats(values):
    values = [x for x in values if isinstance(x, (int, float))]
    if not values:
        return {"n": 0, "p50": None, "p95": None, "p99": None, "max": None}
    return {
        "n": len(values),
        "p50": percentile(values, 0.50),
        "p95": percentile(values, 0.95),
        "p99": percentile(values, 0.99),
        "max": max(values),
        "mean": statistics.fmean(values),
    }


def hist(values, ranges):
    counts = {name: 0 for name, _, _ in ranges}
    for value in values:
        for name, low, high in ranges:
            if low <= value <= high:
                counts[name] += 1
                break
    return counts


def iso_epoch(value):
    return dt.datetime.fromtimestamp(value, dt.timezone.utc).isoformat()


def request_metrics(expected_v3, expected_closure):
    rows = []
    for path in REQUEST_LOGS:
        with path.open() as f:
            for line_no, line in enumerate(f, 1):
                obj = json.loads(line)
                params = json.loads(obj["request_parameters"])
                obj["_path"] = str(path)
                obj["_line"] = line_no
                obj["_text"] = params.get("text", "")
                rows.append(obj)
    v3_candidates = [
        x for x in rows
        if V3_SESSION_RE.search(x["_text"]) and not CLOSURE_RE.search(x["_text"])
    ]
    closure_candidates = [x for x in rows if CLOSURE_RE.search(x["_text"])]
    if not v3_candidates or not closure_candidates:
        raise AssertionError("request-metrics logs do not contain both soak populations")
    def exact_population(candidates, expected, label):
        candidates.sort(key=lambda x: x["request_received_ts"])
        groups = []
        group = []
        for row in candidates:
            if group and row["request_received_ts"] - group[-1]["request_received_ts"] > 300:
                groups.append(group)
                group = []
            group.append(row)
        if group:
            groups.append(group)
        matches = [g for g in groups if len(g) == expected]
        if len(matches) != 1:
            raise AssertionError(f"could not uniquely map {label} metrics population: {[len(g) for g in groups]}")
        return matches[0]
    v3 = exact_population(v3_candidates, expected_v3, "C32 v3")
    closure = exact_population(closure_candidates, expected_closure, "closure")
    return {"v3": v3, "closure": closure, "candidate_counts": {
        "v3": len(v3_candidates), "closure": len(closure_candidates)
    }}


def source_manifest():
    paths = [
        V3_FINAL, V3_REQUESTS, V3_SAMPLES,
        CLOSURE_SUMMARY, CLOSURE_FINAL, CLOSURE_POSTDRAIN,
        CLOSURE_REQUESTS, CLOSURE_SAMPLES,
        *REQUEST_LOGS,
    ]
    return {
        str(path): {"bytes": path.stat().st_size, "sha256": sha256(path)}
        for path in paths
    }


def client_metrics(path):
    rows = [x for _, x in load_jsonl(path)]
    def vals(key):
        return [x[key] for x in rows if isinstance(x.get(key), (int, float))]
    return {
        "rows": len(rows),
        "ttft_seconds": numeric_stats(vals("ttft")),
        "total_seconds": numeric_stats(vals("total")),
        "ttft_missing": sum(x.get("ttft") is None for x in rows),
        "completion_tokens_present": sum(x.get("completion_tokens") is not None for x in rows),
        "prompt_tokens_present": sum(x.get("prompt_tokens") is not None for x in rows),
    }


def metric_population(rows):
    def vals(key):
        return [x[key] for x in rows if isinstance(x.get(key), (int, float))]
    telemetry = [x.get("hicache_telemetry") or {} for x in rows]
    def hvals(key):
        return [x[key] for x in telemetry if isinstance(x.get(key), (int, float))]
    prompt = sum(vals("prompt_tokens"))
    cached = sum(vals("cached_tokens"))
    return {
        "requests": len(rows),
        "successes": sum(bool(x.get("finish_reason")) for x in rows),
        "errors": sum(not bool(x.get("finish_reason")) for x in rows),
        "request_received_window": {
            "start_epoch": min(x["request_received_ts"] for x in rows),
            "end_epoch": max(x["request_received_ts"] for x in rows),
            "start_utc": iso_epoch(min(x["request_received_ts"] for x in rows)),
            "end_utc": iso_epoch(max(x["request_received_ts"] for x in rows)),
            "span_seconds": max(x["request_received_ts"] for x in rows) - min(x["request_received_ts"] for x in rows),
        },
        "prompt_tokens": {"sum": prompt, "stats": numeric_stats(vals("prompt_tokens"))},
        "completion_tokens": {"sum": sum(vals("completion_tokens")), "stats": numeric_stats(vals("completion_tokens"))},
        "cached_tokens": {"sum": cached, "stats": numeric_stats(vals("cached_tokens")),
                          "positive_requests": sum((x.get("cached_tokens") or 0) > 0 for x in rows),
                          "prompt_reuse_ratio": cached / prompt if prompt else None},
        "queue_time_seconds": numeric_stats(vals("queue_time")),
        "e2e_latency_seconds": numeric_stats(vals("e2e_latency")),
        "generation_tps": numeric_stats(vals("decode_throughput")),
        "hicache": {
            "outcomes": {str(k): v for k, v in sorted(Counter(x.get("outcome") for x in telemetry).items(), key=lambda p: str(p[0]))},
            "prefetch_origins": {str(k): v for k, v in sorted(Counter(x.get("prefetch_origin") for x in telemetry).items(), key=lambda p: str(p[0]))},
            "l1_tokens_sum": sum(hvals("l1_tokens")),
            "l2_tokens_sum": sum(hvals("l2_tokens")),
            "l3_tokens_sum": sum(hvals("l3_tokens")),
            "l2_restore_request_count": sum((x.get("l2_tokens") or 0) > 0 for x in telemetry),
            "l3_restore_request_count": sum((x.get("l3_tokens") or 0) > 0 for x in telemetry),
            "completed_kv_tokens_present": sum(x.get("completed_kv_tokens") is not None for x in telemetry),
            "matched_prefix_tokens_present": sum(x.get("matched_prefix_tokens") is not None for x in telemetry),
        },
    }


def sample_metrics(path, exact_end=3600.0):
    rows = [x for _, x in load_jsonl(path)]
    exact = [x for x in rows if 0 <= x.get("t", -1) <= exact_end]
    def one(pop, key):
        return numeric_stats([x[key] for x in pop if isinstance(x.get(key), (int, float))])
    running = [x["num_running_reqs"] for x in exact]
    result = {
        "raw_sample_count": len(rows),
        "raw_span_seconds": rows[-1]["t"] - rows[0]["t"],
        "exact_window_sample_count": len(exact),
        "exact_window_seconds": exact[-1]["t"] - exact[0]["t"],
        "running_batch": {
            **one(exact, "num_running_reqs"),
            "histogram": hist(running, [("0", 0, 0), ("1-4", 1, 4), ("5-8", 5, 8),
                                         ("9-12", 9, 12), ("13-16", 13, 16),
                                         ("17-20", 17, 20), ("21+", 21, 10**9)]),
        },
    }
    if "gpu_util" in exact[0]:
        gpu = [x["gpu_util"] for x in exact]
        result["gpu_util_percent"] = {
            **one(exact, "gpu_util"),
            "histogram": hist(gpu, [("0", 0, 0), ("1-25", 1, 25), ("26-50", 26, 50),
                                     ("51-75", 51, 75), ("76-99", 76, 99), ("100", 100, 100)]),
        }
        result["vram_used_mib"] = one(exact, "vram_used")
        result["ram_used_bytes"] = one(exact, "ram_used")
        rss = {}
        for kind in ("server", "scheduler"):
            values = [item["rss_kb"] for row in exact for item in row.get("process_rss", [])
                      if item.get("kind") == kind]
            rss[kind] = numeric_stats(values)
        result["process_rss_kb"] = rss
        fs = [x["fs_used"] for x in exact]
        result["filesystem_used_bytes"] = {
            "start": fs[0], "end": fs[-1], "delta": fs[-1] - fs[0],
            "positive_intervals": sum(b > a for a, b in zip(fs, fs[1:])),
            "hourly_delta": (fs[-1] - fs[0]) / (exact[-1]["t"] / 3600),
        }
    return result


def make_scorecard():
    for path in [V3_FINAL, V3_REQUESTS, V3_SAMPLES, CLOSURE_SUMMARY,
                 CLOSURE_FINAL, CLOSURE_POSTDRAIN, CLOSURE_REQUESTS, CLOSURE_SAMPLES,
                 *REQUEST_LOGS]:
        if not path.is_file():
            raise FileNotFoundError(path)
    v3_final = load_json(V3_FINAL)
    closure_summary = load_json(CLOSURE_SUMMARY)
    closure_final = load_json(CLOSURE_FINAL)
    closure_postdrain = load_json(CLOSURE_POSTDRAIN)
    metrics = request_metrics(v3_final["n"], closure_summary["requests"]["total"])
    v3_client = client_metrics(V3_REQUESTS)
    closure_client = client_metrics(CLOSURE_REQUESTS)
    v3_duration = v3_final["elapsed_min"] * 60
    closure_duration = closure_summary["duration_min"] * 60
    soaks = {
        "c32_v3": {
            "label": "C32 v3",
            "duration_seconds_run_wide": v3_duration,
            "requests": metric_population(metrics["v3"]),
            "client_artifact_metrics": v3_client,
            "samples": sample_metrics(V3_SAMPLES),
            "requested_rows": {
                "requests": v3_final["n"],
                "duration": f"{v3_duration:.3f} s ({v3_final['elapsed_min']:.2f} min), final artifact",
                "success_rate": f"{v3_final['ok'] / v3_final['n']:.6%}",
                "req_per_s": v3_final["n"] / v3_duration,
                "aggregate_output_tps": sum(x.get("completion_tokens") or 0 for x in metrics["v3"]) / v3_duration,
                "per_request_generation_tps": metric_population(metrics["v3"])["generation_tps"],
                "ttft": v3_client["ttft_seconds"],
                "tpot_itl": "NOT CAPTURED: neither raw client requests nor request-metrics logs contain TPOT/ITL or per-token timing; decode_throughput is not substituted.",
                "queue_wait": metric_population(metrics["v3"])["queue_time_seconds"],
                "actual_running_batch": sample_metrics(V3_SAMPLES)["running_batch"],
                "gpu_util": "NOT CAPTURED: c32v3_samples.jsonl contains no GPU/resource fields, and no separate v3 resource artifact is in scope.",
                "vram_peak": "NOT CAPTURED: no v3 VRAM samples/resource artifact.",
                "ram_rss_peak": "NOT CAPTURED: no v3 RAM/RSS samples/resource artifact.",
                "cache_hit_token_reuse": metric_population(metrics["v3"])["cached_tokens"],
                "l2_l3_restore": metric_population(metrics["v3"])["hicache"],
                "wal_growth_per_hour": "NOT CAPTURED: filesystem usage is recorded only as df used bytes; no WAL-specific counter/path is present.",
                "nvme_read_write": "NOT CAPTURED: no NVMe/device I/O counters are present in the v3 artifacts or in-scope logs.",
            },
        },
        "c32_closure_20260916": {
            "label": "C32 closure 20260916",
            "duration_seconds_run_wide": closure_duration,
            "requests": metric_population(metrics["closure"]),
            "client_artifact_metrics": closure_client,
            "samples": sample_metrics(CLOSURE_SAMPLES),
            "requested_rows": {
                "requests": closure_summary["requests"]["total"],
                "duration": f"{closure_duration:.3f} s ({closure_summary['duration_min']:.3f} min), summary artifact",
                "success_rate": f"{closure_summary['requests']['ok'] / closure_summary['requests']['total']:.6%}",
                "req_per_s": closure_summary["requests"]["total"] / closure_duration,
                "aggregate_output_tps": sum(x.get("completion_tokens") or 0 for x in metrics["closure"]) / closure_duration,
                "per_request_generation_tps": metric_population(metrics["closure"])["generation_tps"],
                "ttft": closure_client["ttft_seconds"],
                "tpot_itl": "NOT CAPTURED: neither raw client requests nor request-metrics logs contain TPOT/ITL or per-token timing; decode_throughput is not substituted.",
                "queue_wait": metric_population(metrics["closure"])["queue_time_seconds"],
                "actual_running_batch": sample_metrics(CLOSURE_SAMPLES)["running_batch"],
                "gpu_util": sample_metrics(CLOSURE_SAMPLES)["gpu_util_percent"],
                "vram_peak": sample_metrics(CLOSURE_SAMPLES)["vram_used_mib"],
                "ram_rss_peak": {
                    "ram_used_bytes": sample_metrics(CLOSURE_SAMPLES)["ram_used_bytes"],
                    "process_rss_kb": sample_metrics(CLOSURE_SAMPLES)["process_rss_kb"],
                },
                "cache_hit_token_reuse": metric_population(metrics["closure"])["cached_tokens"],
                "l2_l3_restore": metric_population(metrics["closure"])["hicache"],
                "wal_growth_per_hour": "NOT CAPTURED: filesystem usage is recorded only as df used bytes; no WAL-specific counter/path is present.",
                "nvme_read_write": "NOT CAPTURED: no NVMe/device I/O counters are present in the closure artifacts or in-scope logs.",
            },
        },
    }
    # These checks are extraction invariants, not workload launches.
    assert soaks["c32_v3"]["requests"]["requests"] == v3_final["n"] == 4983
    assert soaks["c32_closure_20260916"]["requests"]["requests"] == closure_summary["requests"]["total"] == 5503
    assert v3_final["ok"] == 4983 and v3_final["err"] == 0
    assert closure_summary["requests"] == {"total": 5503, "ok": 5503, "errors": 0}
    assert closure_final["queue_drained"] and closure_postdrain["drained"]
    return {
        "scorecard": "PRODUCTION-PERFORMANCE-SCORECARD-v0",
        "generated_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "read_only": True,
        "workload_launched": False,
        "server_contacted": False,
        "source_manifest": source_manifest(),
        "request_metrics_selection": {
            "selection_rule": "C32 v3 = the unique contiguous session-marker group without C32CLOSURE whose row count matches c32v3_final.n; closure = the unique contiguous C32CLOSURE-marker group whose row count matches summary.requests.total.",
            "candidate_counts": metrics["candidate_counts"],
        },
        "soaks": soaks,
        "limitations": [
            "The client v3 request artifact has 1592 null ttft values; v3 TTFT percentiles cover 3391 observed values only.",
            "The client request artifacts have null prompt_tokens/completion_tokens; output-token totals use existing request-metrics completion_tokens.",
            "TPOT/ITL requires per-token or explicit timing fields and is not inferred from decode_throughput.",
            "WAL growth and NVMe read/write are not captured by the supplied artifacts; df filesystem growth is reported separately for closure only.",
            "C32 v3 samples have no epoch/resource fields and extend 3.87 seconds beyond the nominal 3600-second sample window; sample rows are restricted to t <= 3600 for exact-window statistics.",
            "The in-scope request-metrics logs contain 669 additional v3-pattern rows outside the selected v3 group (two earlier groups of 192 and 477); they were excluded by contiguous timestamp grouping and exact row-count matching to c32v3_final.json.",
            "Closure request-metrics rows are selected by the exact C32CLOSURE marker population and contiguous timestamp grouping, matching the 5503-row closure artifact.",
        ],
    }


def markdown(scorecard):
    def fmt(value):
        if isinstance(value, float):
            return f"{value:.6g}"
        return str(value)
    lines = [
        "# PRODUCTION-PERFORMANCE-SCORECARD-v0",
        "",
        "Read-only extraction from existing C32 v3, closure-soak, and request-metrics artifacts. No workload was launched, no server was restarted/contacted, and no production code/configuration was changed.",
        "",
        "## Exact windows",
        "",
        "| Soak | Request-metrics receipt window | Requests | Run-wide duration | Success | Req/s | Aggregate output TPS |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for soak in scorecard["soaks"].values():
        r = soak["requests"]
        lines.append(f"| {soak['label']} | {r['request_received_window']['start_utc']} → {r['request_received_window']['end_utc']} ({r['request_received_window']['span_seconds']:.3f}s) | {r['requests']} | {soak['duration_seconds_run_wide']:.3f}s | {r['successes']}/{r['requests']} ({r['successes']/r['requests']:.6%}) | {soak['requested_rows']['req_per_s']:.6f} | {soak['requested_rows']['aggregate_output_tps']:.6f} |")
    lines += [
        "",
        "Aggregate output TPS uses `completion_tokens` from the existing request-metrics records divided by the run-wide duration in the final/summary artifact. The client JSONL files contain null output-token fields, so they are not used for this total.",
        "",
        "## Required metrics",
        "",
        "| Metric | C32 v3 | Closure 20260916 |",
        "|---|---|---|",
    ]
    for key, title in [
        ("per_request_generation_tps", "Per-request generation TPS (p50/p95/p99)"),
        ("ttft", "TTFT seconds (p50/p95/p99)"),
        ("tpot_itl", "TPOT/ITL"),
        ("queue_wait", "Queue wait seconds (p50/p95/p99)"),
        ("actual_running_batch", "Actual running batch (p50/p95/max; histogram)"),
        ("gpu_util", "GPU util (p50/p95/max; histogram)"),
        ("vram_peak", "VRAM peak"),
        ("ram_rss_peak", "RAM/RSS peak"),
        ("cache_hit_token_reuse", "Cache hit/token reuse"),
        ("l2_l3_restore", "L2/L3 restore counts/tokens"),
        ("wal_growth_per_hour", "WAL growth/hour"),
        ("nvme_read_write", "NVMe read/write"),
    ]:
        cells = []
        for soak in scorecard["soaks"].values():
            value = soak["requested_rows"][key]
            if isinstance(value, dict):
                cells.append("`" + json.dumps(value, sort_keys=True, separators=(",", ":")) + "`")
            else:
                cells.append(str(value))
        lines.append(f"| {title} | {cells[0]} | {cells[1]} |")
    lines += [
        "",
        "## Limitations and evidence",
    ]
    for item in scorecard["limitations"]:
        lines.append(f"- {item}")
    lines += ["", "## Source SHA-256 manifest", "", "```text"]
    for path, info in scorecard["source_manifest"].items():
        lines.append(f"{info['sha256']}  {path} ({info['bytes']} bytes)")
    lines += ["```", "", "## Reproduction", "", "```text", "python3 tools/production_performance_scorecard_v0.py", "```", ""]
    return "\n".join(lines)


def main():
    scorecard = make_scorecard()
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    SCORECARD_PATH.write_text(json.dumps(scorecard, indent=2, sort_keys=True) + "\n")
    REPORT_PATH.write_text(markdown(scorecard))
    print(json.dumps({
        "scorecard": str(SCORECARD_PATH),
        "report": str(REPORT_PATH),
        "scorecard_sha256": sha256(SCORECARD_PATH),
        "report_sha256": sha256(REPORT_PATH),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
