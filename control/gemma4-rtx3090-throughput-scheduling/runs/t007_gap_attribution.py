#!/usr/bin/env python3
"""Attribute device-idle time in one T007 Nsight window to three causes.

Buckets (deduped by union, residual reported separately):
  host_late           device idle, the scheduler thread issued no device work and
                      was inside a host range downstream of a finished batch
  submitted_stall     device idle, the scheduler thread DID issue device work in
                      that gap (submitted but the device did not start it)
  no_runnable         device idle while every waiting request was parked in an
                      L3 restore wait (nothing the scheduler may admit)
  handoff_after_sync  device idle while the scheduler thread was blocked inside a
                      stream/event synchronize (post-batch handoff boundary)
  residual            device idle covered by none of the above

Time-correlation only: a range overlapping a gap does not prove it caused it.
"""

from __future__ import annotations

import re
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path


def union(rows):
    rows = sorted((s, e) for s, e in rows if e > s)
    total = 0
    merged = []
    cs = ce = None
    for s, e in rows:
        if cs is None:
            cs, ce = s, e
        elif s <= ce:
            ce = max(ce, e)
        else:
            merged.append((cs, ce))
            total += ce - cs
            cs, ce = s, e
    if cs is not None:
        merged.append((cs, ce))
        total += ce - cs
    return total, merged


def intersect(left, right):
    i = j = total = 0
    left, right = sorted(left), sorted(right)
    while i < len(left) and j < len(right):
        a, b = left[i]
        c, d = right[j]
        total += max(0, min(b, d) - max(a, c))
        if b <= d:
            i += 1
        else:
            j += 1
    return total


DEVICE_WORK = (
    "cudaLaunchKernel",
    "cuLaunchKernel",
    "cudaGraphLaunch",
    "cudaMemcpyAsync",
    "cudaMemcpyBatchAsync",
    "cudaMemsetAsync",
    "cudaEventRecord",
    "cudaStreamWaitEvent",
)
SYNC = ("cudaStreamSynchronize", "cudaEventSynchronize", "cudaDeviceSynchronize")


def main():
    run = Path(sys.argv[1])
    db = sqlite3.connect(run / "t007-c8-window.sqlite")
    cols = lambda t: {r[1] for r in db.execute(f"pragma table_info({t})")}
    strings = dict(db.execute("select id,value from StringIds"))

    kernels = [
        (r[0], r[1])
        for r in db.execute("select start,end from CUPTI_ACTIVITY_KIND_KERNEL")
    ]
    mem = (
        [
            (r[0], r[1])
            for r in db.execute("select start,end from CUPTI_ACTIVITY_KIND_MEMCPY")
        ]
        if cols("CUPTI_ACTIVITY_KIND_MEMCPY")
        else []
    )
    memset = (
        [
            (r[0], r[1])
            for r in db.execute("select start,end from CUPTI_ACTIVITY_KIND_MEMSET")
        ]
        if cols("CUPTI_ACTIVITY_KIND_MEMSET")
        else []
    )
    dev = kernels + mem + memset
    if not dev:
        print("empty capture")
        return 1
    lo, hi = min(s for s, _ in dev), max(e for _, e in dev)
    wall = hi - lo
    busy, merged = union(dev)
    gaps = []
    prev = lo
    for s, e in merged:
        if s > prev:
            gaps.append((prev, s))
        prev = max(prev, e)
    if hi > prev:
        gaps.append((prev, hi))
    idle = sum(e - s for s, e in gaps)

    api = defaultdict(list)
    for s, e, nid in db.execute(
        "select start,end,nameId from CUPTI_ACTIVITY_KIND_RUNTIME"
    ):
        api[strings.get(nid, "")].append((s, e))
    work_calls = [(s, e) for name in DEVICE_WORK for s, e in api.get(name, ())]
    sync_calls = [(s, e) for name in SYNC for s, e in api.get(name, ())]

    nv = []
    if cols("NVTX_EVENTS"):
        for s, e, text, tid, textid in db.execute(
            "select start,end,text,globalTid,textId from NVTX_EVENTS where end is not null"
        ):
            nv.append((s, e, text or strings.get(textid), tid))

    # Index NVTX ranges per thread and resolve "innermost containing range" by
    # bisecting on start times; a plain scan over ~1e9 (gap, range) pairs does
    # not finish on a full C-8 window.
    import bisect

    by_thread = defaultdict(list)
    for s, e, t, tid in nv:
        by_thread[tid].append((s, e, t))
    for rows in by_thread.values():
        rows.sort()
    starts = {tid: [r[0] for r in rows] for tid, rows in by_thread.items()}

    def innermost_at(ts):
        best = None
        for tid, rows in by_thread.items():
            idx = bisect.bisect_right(starts[tid], ts)
            # Walk back while ranges may still contain ts; ranges are nested at
            # most a few levels deep in this trace.
            for j in range(idx - 1, max(-1, idx - 200), -1):
                s, e, t = rows[j]
                if s <= ts < e and (best is None or (e - s) < (best[1] - best[0])):
                    best = (s, e, t)
                if s <= ts - 2_000_000_000:
                    break
        return best[2] if best else None

    # Gaps are disjoint by construction, so classifying each gap once gives
    # disjoint bucket totals; no interval subtraction is needed.
    merged_work = union(work_calls)[1]
    merged_sync = union(sync_calls)[1]

    restore = []
    log_path = run / "server.log"
    session = db.execute("select utcEpochNs from TARGET_INFO_SESSION_START_TIME").fetchone()
    if log_path.exists() and session:
        epoch_ns = session[0]
        states = defaultdict(list)
        pat = re.compile(
            r"ts_ms=(\d+).*?evt=restore_state rid=([^ ]+) state=([A-Z_]+) reason=([a-zA-Z_]+)"
        )
        for line in log_path.open(errors="replace"):
            m = pat.search(line)
            if m:
                ts_ms, rid, state, reason = m.groups()
                states[rid].append((int(ts_ms) * 1_000_000 - epoch_ns, state, reason))
        waits = []
        for transitions in states.values():
            transitions.sort()
            for (start_ts, state, _reason), (end_ts, _, _) in zip(transitions, transitions[1:]):
                if state != "WAIT_CAPACITY" or end_ts <= start_ts:
                    continue
                start_ts, end_ts = max(start_ts, lo), min(end_ts, hi)
                if end_ts > start_ts:
                    waits.append((start_ts, end_ts))
        restore = union(waits)[1]

    def sweep(intervals):
        """Boolean per gap: does any merged interval overlap it (linear)."""
        flags = [False] * len(gaps)
        j = 0
        for i, (gs, ge) in enumerate(gaps):
            while j < len(intervals) and intervals[j][1] <= gs:
                j += 1
            k = j
            while k < len(intervals) and intervals[k][0] < ge:
                if intervals[k][1] > gs:
                    flags[i] = True
                    break
                k += 1
        return flags

    work_flag = sweep(merged_work)
    sync_flag = sweep(merged_sync)
    restore_flag = sweep(restore)

    # Intra-batch launch gaps are microseconds wide and dominate the count;
    # scheduling starvation shows up in the wide ones. Both are reported, but
    # the buckets only classify gaps at or above the threshold.
    min_gap = int(float(sys.argv[2]) * 1e6) if len(sys.argv) > 2 else 1_000_000
    buckets = defaultdict(float)
    counts = Counter()
    restore_overlap = defaultdict(float)
    per_range = Counter()
    micro_total = 0
    for i, (gs, ge) in enumerate(gaps):
        dur = ge - gs
        if dur < min_gap:
            micro_total += dur
            continue
        label = innermost_at(gs) or "<none>"
        if work_flag[i]:
            name = "submitted_stall"
        elif sync_flag[i]:
            name = "handoff_after_sync"
        elif label.startswith("scheduler.process_batch_result"):
            name = "host_late_result_processing"
        elif label.startswith("scheduler.run_batch"):
            name = "host_late_before_launch"
        elif label.startswith("scheduler.get_next_batch_to_run") or label.startswith(
            "scheduler.get_new_batch_prefill"
        ):
            name = "host_scheduling"
        elif label.startswith("scheduler.process_input_requests"):
            name = "no_runnable_waiting_supply"
        else:
            name = "residual"
        buckets[name] += dur
        counts[name] += 1
        per_range[(name, label)] += dur
        if restore_flag[i]:
            restore_overlap[name] += dur

    pct = lambda x: 100.0 * x / wall if wall else 0.0
    wide = sum(buckets.values())
    print(
        f"run={run.name} device_span_s={wall/1e9:.3f} busy_s={busy/1e9:.3f} ({pct(busy):.2f}%) "
        f"idle_s={idle/1e9:.3f} ({pct(idle):.2f}%) gaps={len(gaps)}"
    )
    print(
        f"  gaps<{min_gap/1e6:.1f}ms: {micro_total/1e9:6.3f}s ({100.0*micro_total/idle if idle else 0:5.2f}% of idle, "
        f"{sum(1 for gs, ge in gaps if ge-gs < min_gap)} gaps)"
    )
    print(f"  gaps>={min_gap/1e6:.1f}ms: {wide/1e9:6.3f}s ({100.0*wide/idle if idle else 0:5.2f}% of idle)")
    for name in (
        "host_late_result_processing",
        "host_late_before_launch",
        "host_scheduling",
        "no_runnable_waiting_supply",
        "submitted_stall",
        "handoff_after_sync",
        "residual",
    ):
        value = buckets.get(name, 0.0)
        print(
            f"    {name:28s} {value/1e9:7.3f}s {counts.get(name,0):5d} gaps "
            f"{pct(value):5.2f}% of wall  (restore-wait overlap {restore_overlap.get(name,0.0)/1e9:6.3f}s)"
        )
    print("  widest-gap coverage detail:")
    for (name, label), value in per_range.most_common(10):
        print(f"    {value/1e9:7.3f}s {name:26s} {label}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
