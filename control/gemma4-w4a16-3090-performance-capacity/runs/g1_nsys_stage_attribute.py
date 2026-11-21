#!/usr/bin/env python3
"""Attribute the nsys capture-range window to restore-path stages.

Inputs are the nsys sqlite export of a `--capture-range=cudaProfilerApi` run and,
optionally, the service's per-request metrics so each HtoD copy can be matched to
a request window.

Reported quantities are kept separate on purpose:

  * HtoD bytes/time are DMA activity, not compute;
  * kernel busy time is the union of kernel intervals -- a duty ratio over the
    capture span, not SM occupancy (occupancy needs CUPTI counters, which are
    permission-blocked on this host);
  * H2D overlapped with compute is an interval intersection, so it is not added
    to compute time anywhere.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import statistics
from pathlib import Path

def merged_union(intervals: list[tuple[int, int]]) -> int:
    if not intervals:
        return 0
    intervals.sort()
    total = 0
    cur_start, cur_end = intervals[0]
    for start, end in intervals[1:]:
        if start > cur_end:
            total += cur_end - cur_start
            cur_start, cur_end = start, end
        else:
            cur_end = max(cur_end, end)
    total += cur_end - cur_start
    return total


def overlap_with(target: list[tuple[int, int]], union: list[tuple[int, int]]) -> int:
    total = 0
    index = 0
    for start, end in target:
        while index < len(union) and union[index][1] <= start:
            index += 1
        probe = index
        while probe < len(union) and union[probe][0] < end:
            total += min(end, union[probe][1]) - max(start, union[probe][0])
            probe += 1
    return total


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round(fraction * (len(ordered) - 1)))))
    return ordered[index]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sqlite", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--metrics-dir", default=None)
    parser.add_argument("--min-bytes", type=int, default=1 << 20)
    parser.add_argument("--mono-epoch-offset-s", type=float, default=None)
    parser.add_argument("--window-epoch-start", type=float, default=None,
                        help="epoch seconds when cudaProfilerStart was issued")
    parser.add_argument("--tolerance-s", type=float, default=0.5)
    args = parser.parse_args()

    connection = sqlite3.connect(args.sqlite)
    kinds = {
        row[0]: row[1]
        for row in connection.execute("SELECT id, name FROM ENUM_CUDA_MEMCPY_OPER")
    }
    htod_kinds = [kind for kind, name in kinds.items() if "HtoD" in name or "HTOD" in name]

    copies = list(
        connection.execute(
            "SELECT start, end, bytes, copyKind, streamId FROM CUPTI_ACTIVITY_KIND_MEMCPY"
        )
    )
    kernels = list(
        connection.execute("SELECT start, end FROM CUPTI_ACTIVITY_KIND_KERNEL")
    )
    nvtx = [
        row
        for row in connection.execute(
            "SELECT start, end, text, globalTid FROM NVTX_EVENTS WHERE end IS NOT NULL"
        )
    ]

    # NVTX timestamps live in a different clock domain on some installs, so the
    # capture span is taken from the CUDA activity tables only.
    span_start = min([c[0] for c in copies] + [k[0] for k in kernels] or [0])
    span_end = max([c[1] for c in copies] + [k[1] for k in kernels] or [0])
    span_ns = max(1, span_end - span_start)

    htod = [c for c in copies if c[3] in htod_kinds and c[2] >= args.min_bytes]
    kernel_intervals = [(k[0], k[1]) for k in kernels]
    kernel_busy = merged_union(kernel_intervals)
    htod_intervals = [(c[0], c[1]) for c in htod]

    report = {
        "sqlite": str(args.sqlite),
        "capture_window_s": round(span_ns / 1e9, 3),
        "rows": {"memcpy": len(copies), "kernel": len(kernels), "nvtx": len(nvtx)},
        "copy_kinds": kinds,
        "htod_ge_min_bytes": {
            "min_bytes": args.min_bytes,
            "count": len(htod),
            "bytes": sum(c[2] for c in htod),
            "sum_duration_s": round(sum(c[1] - c[0] for c in htod) / 1e9, 4),
            "p50_duration_ms": (percentile([(c[1] - c[0]) / 1e6 for c in htod], 0.5)),
            "p95_duration_ms": (percentile([(c[1] - c[0]) / 1e6 for c in htod], 0.95)),
            "largest": sorted(
                (
                    {
                        "start_s": round((c[0] - span_start) / 1e9, 3),
                        "bytes": c[2],
                        "duration_ms": round((c[1] - c[0]) / 1e6, 3),
                    }
                    for c in htod
                ),
                key=lambda item: -item["bytes"],
            )[:10],
        },
        "kernel_busy_s": round(kernel_busy / 1e9, 3),
        "kernel_duty_over_capture": round(kernel_busy / span_ns, 4),
        "htod_overlapped_with_compute_s": round(
            overlap_with(htod_intervals, kernel_intervals) / 1e9, 4
        ),
        "note": "kernel_duty_over_capture is CUDA kernel busy / capture span, not SM occupancy",
    }

    # Optional per-request attribution: a request's restore window is
    # [storage_query_start, ready]; copies are assigned to every rid whose window
    # covers them, so an ambiguous copy is reported as shared rather than guessed.
    if args.window_epoch_start is not None:
        report["clock"] = {
            "window_epoch_start": args.window_epoch_start,
            "first_activity_ns": span_start,
            "delta_ns": span_start - int(args.window_epoch_start * 1e9),
            "method": "first CUDA activity after cudaProfilerStart, so bias is the "
                      "start-to-first-kernel latency (sub-second at depth 64+)",
        }
    if args.metrics_dir:
        offset = args.mono_epoch_offset_s
        windows = []
        for path in Path(args.metrics_dir).glob("*.json"):
            try:
                record = json.loads(path.read_text())
            except json.JSONDecodeError:
                continue
            telemetry = record.get("hicache_telemetry") or {}
            start = telemetry.get("storage_query_start_mono_ns")
            ready = telemetry.get("ready_mono_ns")
            if not start or not ready:
                continue
            windows.append((record.get("id") or record.get("rid"), start, ready))
        attribution = {"requests_with_window": len(windows), "copies_matched": 0,
                       "copies_matched_multiple": 0, "copies_unmatched": 0,
                       "bytes_matched": 0, "examples": []}
        delta_ns = (
            span_start - int(args.window_epoch_start * 1e9)
            if args.window_epoch_start is not None
            else None
        )
        if delta_ns is not None and windows:
            for copy in htod:
                start_ns = copy[0] - delta_ns
                hits = [
                    rid
                    for rid, lo, hi in windows
                    if lo - args.tolerance_s * 1e9 <= start_ns <= hi + args.tolerance_s * 1e9
                ]
                if len(hits) == 1:
                    attribution["copies_matched"] += 1
                    attribution["bytes_matched"] += copy[2]
                    if len(attribution["examples"]) < 10:
                        attribution["examples"].append(
                            {"rid": hits[0], "bytes": copy[2],
                             "duration_ms": round((copy[1] - copy[0]) / 1e6, 3)}
                        )
                elif hits:
                    attribution["copies_matched_multiple"] += 1
                else:
                    attribution["copies_unmatched"] += 1
        report["per_rid_attribution"] = attribution

    sizes: dict[str, int] = {}
    for copy in htod:
        key = f"{round(copy[2] / 1e6)}MB"
        sizes[key] = sizes.get(key, 0) + 1
    report["htod_size_histogram_mb"] = dict(sorted(sizes.items(), key=lambda kv: -kv[1]))
    streams: dict[str, int] = {}
    for copy in htod:
        key = str(copy[4])
        streams[key] = streams.get(key, 0) + 1
    report["htod_streams"] = streams

    Path(args.out).write_text(json.dumps(report, indent=2, sort_keys=True))
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
