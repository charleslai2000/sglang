#!/usr/bin/env python3
"""T007: quantify GPU and host-side time inside one bounded C-8 Nsight window."""

from __future__ import annotations
import re
import sqlite3, sys
from collections import Counter, defaultdict
from pathlib import Path


def union_ns(rows):
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


def intersect_ns(left, right):
    i = j = total = 0
    left = sorted(left)
    right = sorted(right)
    while i < len(left) and j < len(right):
        a, b = left[i]
        c, d = right[j]
        total += max(0, min(b, d) - max(a, c))
        if b <= d:
            i += 1
        else:
            j += 1
    return total


def main():
    run = Path(sys.argv[1])
    db = sqlite3.connect(run / "t007-c8-window.sqlite")

    def cols(t):
        return {r[1] for r in db.execute(f"pragma table_info({t})")}

    strings = dict(db.execute("select id,value from StringIds"))
    kcols = cols("CUPTI_ACTIVITY_KIND_KERNEL")
    tidcol = "globalTid" if "globalTid" in kcols else "NULL"
    kernels = [
        tuple(r)
        for r in db.execute(
            f"select start,end,streamId,{tidcol},correlationId from CUPTI_ACTIVITY_KIND_KERNEL"
        )
    ]
    mem = (
        [
            tuple(r)
            for r in db.execute(
                "select start,end,bytes,copyKind,correlationId from CUPTI_ACTIVITY_KIND_MEMCPY"
            )
        ]
        if cols("CUPTI_ACTIVITY_KIND_MEMCPY")
        else []
    )
    memset = (
        [
            tuple(r)
            for r in db.execute(
                "select start,end,bytes from CUPTI_ACTIVITY_KIND_MEMSET"
            )
        ]
        if cols("CUPTI_ACTIVITY_KIND_MEMSET")
        else []
    )
    dev = (
        [(r[0], r[1]) for r in kernels]
        + [(r[0], r[1]) for r in mem]
        + [(r[0], r[1]) for r in memset]
    )
    if not dev:
        print("empty capture")
        return 1
    lo = min(s for s, e in dev)
    hi = max(e for s, e in dev)
    wall = hi - lo
    busy, merged = union_ns(dev)
    kb, _ = union_ns([(s, e) for s, e, *_ in kernels])
    mb, _ = union_ns([(s, e) for s, e, *_ in mem])
    sb, _ = union_ns([(s, e) for s, e, *_ in memset])
    gaps = []
    prev = lo
    for s, e in merged:
        if s > prev:
            gaps.append((prev, s))
        prev = max(prev, e)
    if hi > prev:
        gaps.append((prev, hi))
    gl = [e - s for s, e in gaps]
    pct = lambda x: 100 * x / wall if wall else 0
    print(
        f"device_span_s={wall / 1e9:.3f} kernel_rows={len(kernels)} memcpy_rows={len(mem)} memset_rows={len(memset)}"
    )
    print(
        f"busy_union_s={busy / 1e9:.3f} ({pct(busy):.2f}%) kernel_union_s={kb / 1e9:.3f} ({pct(kb):.2f}%) memcpy_union_s={mb / 1e9:.3f} ({pct(mb):.2f}%) memset_union_s={sb / 1e9:.3f}"
    )
    print(
        f"idle_gap_s={sum(gl) / 1e9:.3f} ({pct(sum(gl)):.2f}%) gaps={len(gl)} >10ms={sum(x > 1e7 for x in gl)} >100ms={sum(x > 1e8 for x in gl)} top_ms={sorted((x / 1e6 for x in gl), reverse=True)[:12]}"
    )
    kinds = Counter()
    nbytes = Counter()
    for s, e, b, k, c in mem:
        kinds[k] += e - s
        nbytes[k] += b or 0
    print("memcpy_ms_by_kind=" + str({k: round(v / 1e6, 2) for k, v in kinds.items()}))
    print("memcpy_bytes_by_kind=" + str(dict(nbytes)))
    if not cols("NVTX_EVENTS"):
        return 0
    nv = []
    for s, e, text, tid, textid in db.execute(
        "select start,end,text,globalTid,textId from NVTX_EVENTS where end is not null"
    ):
        nv.append((s, e, text or strings.get(textid), tid))
    totals = Counter()
    counts = Counter()
    for s, e, t, tid in nv:
        totals[t] += e - s
        counts[t] += 1
    print("--- NVTX host ranges (summed per-thread inclusive time; can overlap) ---")
    for t, d in totals.most_common(20):
        print(f"{d / 1e9:8.3f}s {counts[t]:6d}x {t}")
    bythread = defaultdict(list)
    for s, e, t, tid in nv:
        bythread[tid].append((s, e, t))
    attr = Counter()
    ac = Counter()
    # Linear interval intersection per thread; nested scans are quadratic on
    # the full C-8 window (hundreds of thousands of GPU gaps).
    gaps_sorted = sorted(gaps)
    for tid, rows in bythread.items():
        rows.sort(key=lambda x: x[0])
        i = j = 0
        while i < len(rows) and j < len(gaps_sorted):
            s, e, t = rows[i]
            gs, ge = gaps_sorted[j]
            ov = min(e, ge) - max(s, gs)
            if ov > 0:
                attr[t] += ov
                ac[t] += 1
            if e <= ge:
                i += 1
            else:
                j += 1
    print("--- NVTX host time overlapping device idle gaps (ranges may overlap) ---")
    for t, d in attr.most_common(20):
        print(f"{d / 1e9:8.3f}s {ac[t]:6d} intersections {t}")
    # CUDA API host-call totals; device execution and CPU waiting remain separate.
    if cols("CUPTI_ACTIVITY_KIND_RUNTIME"):
        api = Counter()
        acount = Counter()
        for s, e, nid in db.execute(
            "select start,end,nameId from CUPTI_ACTIVITY_KIND_RUNTIME"
        ):
            name = strings.get(nid, "")
            api[name] += e - s
            acount[name] += 1
        print("--- CUDA runtime API (host time) ---")
        for n in (
            "cudaStreamSynchronize_v3020",
            "cudaEventSynchronize_v3020",
            "cudaStreamWaitEvent_v3020",
        ):
            print(f"{n}: calls={acount[n]} host_ms={api[n] / 1e6:.3f}")

    # Join the existing per-RID restore-state log to the GPU event timeline.
    # Timestamps in telemetry use epoch milliseconds; Nsight's session start
    # gives the UTC epoch origin for its relative CUPTI timestamps.
    log_path = run / "server.log"
    if log_path.exists() and gaps:
        session = db.execute(
            "select utcEpochNs from TARGET_INFO_SESSION_START_TIME"
        ).fetchone()
        if session:
            epoch_ns = session[0]
            states = defaultdict(list)
            pat = re.compile(
                r"ts_ms=(\d+).*?evt=restore_state rid=([^ ]+) "
                r"state=([A-Z_]+) reason=([a-zA-Z_]+)"
            )
            for line in log_path.open(errors="replace"):
                m = pat.search(line)
                if m:
                    ts_ms, rid, state, reason = m.groups()
                    states[rid].append((int(ts_ms) * 1_000_000 - epoch_ns, state, reason))
            waits = defaultdict(list)
            for transitions in states.values():
                transitions.sort()
                for (start, state, reason), (end, _, _) in zip(transitions, transitions[1:]):
                    if state != "WAIT_CAPACITY" or end <= start:
                        continue
                    start, end = max(start, lo), min(end, hi)
                    if end > start:
                        waits[reason].append((start, end))
            merged_waits = []
            print("--- restore WAIT_CAPACITY intervals intersecting this GPU window ---")
            for reason, rows in sorted(waits.items()):
                _, merged_reason = union_ns(rows)
                merged_waits.extend(merged_reason)
                idle_overlap = intersect_ns(merged_reason, gaps)
                print(
                    f"{reason}: rid_intervals={len(rows)} unique_wait_s="
                    f"{sum(e-s for s,e in merged_reason)/1e9:.3f} "
                    f"unique_idle_overlap_s={idle_overlap/1e9:.3f}"
                )
            _, merged_waits = union_ns(merged_waits)
            any_idle_overlap = intersect_ns(merged_waits, gaps)
            print(
                f"any_capacity_wait_unique_idle_overlap_s={any_idle_overlap/1e9:.3f} "
                f"of_idle_s={sum(e-s for s,e in gaps)/1e9:.3f} "
                f"(time correlation only; does not prove waits caused GPU gaps)"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
