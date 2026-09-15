#!/usr/bin/env python3
"""R129 Q1/Q2/Q3 extraction from the frozen R128 probe log window.

Definitions (P2A-MEASUREMENT-CONTRACT-20260912.md):
  Q1 = admission_monotonic_ns - enqueue_mono_ns          (join by rid)
  Q2 = ready_monotonic_ns     - prefetch_issue_mono_ns   (join by attempt_id)
  Q3 = storage_hit_query exit_mono_ns - enter_mono_ns (+ backend_lookup_ns)

All marks are time.monotonic_ns() in the single scheduler process.  Fail
closed: every missing/unjoinable record is reported by exact rid/attempt_id;
nothing is imputed.
"""
import json
import os
import re
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
WINDOW = os.environ.get(
    "R129_WINDOW",
    "/mnt/data/nerun-dev/r129/window-36294-597400.log",
)
OUT = os.environ.get("R129_EXTRACT_OUT", os.path.join(HERE, "extracted.json"))

RE_M1 = re.compile(
    r"evt=enqueue_mono_ns rid=(\S+) enqueue_mono_ns=(\d+) node_id=(\S+) "
    r"build_id=(\S+) session_generation=(\S+) probe_ns=(\d+)")
RE_M2 = re.compile(
    r"evt=prefetch_issued rid=(\S+) prefetch_length=(\d+) "
    r"prefetch_issue_mono_ns=(\d+) attempt_id=(\S+) node_id=(\S+) "
    r"build_id=(\S+) session_generation=(\S+) probe_ns=(\d+)")
RE_M3 = re.compile(
    r"evt=storage_hit_query enter_mono_ns=(\d+) exit_mono_ns=(\d+) "
    r"backend_lookup_ns=(\S+) lock_wait_ns=(\S+) syscall_wait_ns=(\S+) "
    r"all_reduce_ns=(\S+) caller=(\S+) rid=(\S+) attempt_id=(\S+) "
    r"query_len=(\d+) kv_hit_pages=(\d+) probe_ns=(\d+)")
RE_ADM = re.compile(
    r"evt=admission\.v2 .*? rid=(\S+) .*? admission_monotonic_ns=(\d+)")
RE_RH = re.compile(
    r"evt=ready_host .*? rid=(\S+) attempt_id=(\S+) issue_origin=(\S+) "
    r"completed_kv_tokens=(\S+) .*? finalize_result=(\S+) "
    r"ready_monotonic_ns=(\d+)")
RE_RS = re.compile(
    r"evt=ready_stage .*? rid=(\S+) decision_id=(\S+) attempt_id=(\S+) "
    r"issue_origin=(\S+) demand_restore=(\S+) restore_state_before=(\S+) "
    r"restore_state_after=(\S+) result=(\S+) reason=(\S+) frontier_rank=(\d+)")


def pct(vals, q):
    if not vals:
        return None
    s = sorted(vals)
    if len(s) == 1:
        return s[0]
    k = (len(s) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def dist(vals):
    vals = [int(v) for v in vals if v is not None]
    if not vals:
        return {"count": 0}
    return {
        "count": len(vals),
        "p50": pct(vals, 0.50), "p95": pct(vals, 0.95),
        "p99": pct(vals, 0.99), "max": max(vals), "min": min(vals),
        "mean": statistics.fmean(vals),
    }


def us(x):
    return None if x is None else round(x / 1000.0, 3)


def ms(x):
    return None if x is None else round(x / 1e6, 3)


def human(d):
    out = {}
    for k in ("p50", "p95", "p99", "max", "min", "mean"):
        if k in d and d[k] is not None:
            out[k] = {"ns": round(d[k], 1), "us": us(d[k]), "ms": ms(d[k])}
    out["count"] = d.get("count")
    return out


def bucket(qlen):
    if qlen < 1000:
        return "<1k"
    if qlen < 5000:
        return "1k-5k"
    if qlen < 20000:
        return "5k-20k"
    return ">=20k"


def main():
    if not os.path.exists(WINDOW):
        print("FATAL: window not found:", WINDOW, file=sys.stderr)
        return 2
    m1, m2, m3, adm, rh, rs = [], [], [], [], [], []
    with open(WINDOW, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if "evt=" not in line:
                continue
            if "evt=enqueue_mono_ns" in line:
                g = RE_M1.search(line)
                if g:
                    m1.append({"rid": g.group(1), "enqueue": int(g.group(2)),
                               "node_id": g.group(3), "build_id": g.group(4),
                               "session_generation": g.group(5),
                               "probe_ns": int(g.group(6))})
            elif "evt=prefetch_issued" in line:
                g = RE_M2.search(line)
                if g:
                    m2.append({"rid": g.group(1), "prefetch_length": int(g.group(2)),
                               "issue": int(g.group(3)), "attempt_id": g.group(4),
                               "node_id": g.group(5), "build_id": g.group(6),
                               "session_generation": g.group(7),
                               "probe_ns": int(g.group(8))})
            elif "evt=storage_hit_query" in line:
                g = RE_M3.search(line)
                if g:
                    m3.append({"enter": int(g.group(1)), "exit": int(g.group(2)),
                               "backend_lookup_ns": g.group(3),
                               "lock_wait_ns": g.group(4),
                               "syscall_wait_ns": g.group(5),
                               "all_reduce_ns": g.group(6), "caller": g.group(7),
                               "rid": g.group(8), "attempt_id": g.group(9),
                               "query_len": int(g.group(10)),
                               "kv_hit_pages": int(g.group(11)),
                               "probe_ns": int(g.group(12))})
            elif "evt=admission.v2" in line:
                g = RE_ADM.search(line)
                if g:
                    adm.append({"rid": g.group(1), "admission": int(g.group(2))})
            elif "evt=ready_host" in line:
                g = RE_RH.search(line)
                if g:
                    rh.append({"rid": g.group(1), "attempt_id": g.group(2),
                               "issue_origin": g.group(3),
                               "completed_kv_tokens": g.group(4),
                               "finalize_result": g.group(5),
                               "ready": int(g.group(6))})
            elif "evt=ready_stage" in line:
                g = RE_RS.search(line)
                if g:
                    rs.append({"rid": g.group(1), "decision_id": g.group(2),
                               "attempt_id": g.group(3), "issue_origin": g.group(4),
                               "restore_state_after": g.group(7),
                               "result": g.group(8), "reason": g.group(9),
                               "frontier_rank": int(g.group(10))})

    # ---- Q1: one M1 per rid, later admission.v2 ----
    enq_by_rid = {}
    m1_dupes = []
    for r in m1:
        if r["rid"] in enq_by_rid:
            m1_dupes.append(r["rid"])
        enq_by_rid.setdefault(r["rid"], r)
    adm_by_rid = {}
    adm_dupes = []
    for a in adm:
        if a["rid"] in adm_by_rid:
            adm_dupes.append(a["rid"])
        adm_by_rid.setdefault(a["rid"], a)
    q1 = []
    q1_missing_adm = []
    q1_not_later = []
    for rid, e in enq_by_rid.items():
        a = adm_by_rid.get(rid)
        if a is None:
            q1_missing_adm.append(rid)
            continue
        d = a["admission"] - e["enqueue"]
        if d < 0:
            q1_not_later.append(rid)
            continue
        q1.append({"rid": rid, "q1_ns": d})

    # ---- Q2: attempt_id join ----
    m2_by_attempt = {}
    m2_dupes = []
    for r in m2:
        if r["attempt_id"] in m2_by_attempt:
            m2_dupes.append(r["attempt_id"])
        m2_by_attempt.setdefault(r["attempt_id"], r)
    rh_by_attempt = {r["attempt_id"]: r for r in rh}
    q2 = []
    q2_issue_no_ready = []
    for aid, r in m2_by_attempt.items():
        h = rh_by_attempt.get(aid)
        if h is None:
            q2_issue_no_ready.append(aid)
            continue
        q2.append({"attempt_id": aid, "rid": r["rid"],
                   "issue": r["issue"], "ready": h["ready"],
                   "q2_ns": h["ready"] - r["issue"],
                   "issue_origin": h["issue_origin"],
                   "finalize_result": h["finalize_result"]})
    ready_no_issue = [a for a in rh_by_attempt if a not in m2_by_attempt]

    # ---- Q3 ----
    q3 = []
    for r in m3:
        dur = r["exit"] - r["enter"]
        try:
            be = int(r["backend_lookup_ns"])
        except ValueError:
            be = None
        q3.append({"caller": r["caller"], "rid": r["rid"],
                   "attempt_id": r["attempt_id"], "query_len": r["query_len"],
                   "kv_hit_pages": r["kv_hit_pages"], "q3_ns": dur,
                   "backend_ns": be, "probe_ns": r["probe_ns"],
                   "lock_wait_ns": r["lock_wait_ns"],
                   "syscall_wait_ns": r["syscall_wait_ns"],
                   "all_reduce_ns": r["all_reduce_ns"]})
    q3_by_caller = {}
    q3_by_bucket = {}
    for r in q3:
        q3_by_caller.setdefault(r["caller"], []).append(r["q3_ns"])
        q3_by_bucket.setdefault(bucket(r["query_len"]), []).append(r["q3_ns"])
    q3_backend_by_caller = {}
    for r in q3:
        if r["backend_ns"] is not None:
            q3_backend_by_caller.setdefault(r["caller"], []).append(r["backend_ns"])

    # ---- Q1-vs-Q2 coverage (per completed attempt) ----
    coverage = []
    for r in q2:
        rid = r["rid"]
        a = adm_by_rid.get(rid)
        e = enq_by_rid.get(rid)
        rec = {"attempt_id": r["attempt_id"], "rid": rid, "q2_ns": r["q2_ns"],
               "issue_origin": r["issue_origin"]}
        if a is not None:
            rec["admission_minus_ready_ns"] = a["admission"] - r["ready"]
            rec["admission_minus_issue_ns"] = a["admission"] - r["issue"]
            rec["covered"] = (a["admission"] - r["ready"]) >= 0
        else:
            rec["admission_minus_ready_ns"] = None
            rec["covered"] = None
            rec["gap"] = "no_admission_v2_for_rid"
        if e is not None:
            rec["q1_ns"] = a["admission"] - e["enqueue"] if a is not None else None
        coverage.append(rec)

    # ---- overhead ----
    overhead = {
        "M1": dist([r["probe_ns"] for r in m1]),
        "M2": dist([r["probe_ns"] for r in m2]),
        "M3": dist([r["probe_ns"] for r in m3]),
    }
    over_1ms = [{"event": ev, "count": sum(1 for r in lst if r["probe_ns"] > 1_000_000)}
                for ev, lst in (("M1", m1), ("M2", m2), ("M3", m3))]

    result = {
        "window": WINDOW,
        "counts_raw": {"M1": len(m1), "M2": len(m2), "M3": len(m3),
                       "admission.v2": len(adm), "ready_host": len(rh),
                       "ready_stage": len(rs)},
        "Q1": {"dist": human(dist([r["q1_ns"] for r in q1])),
               "samples": q1,
               "gaps": {"no_admission_v2": q1_missing_adm,
                        "admission_not_after_enqueue": q1_not_later,
                        "duplicate_M1_rid": sorted(set(m1_dupes)),
                        "duplicate_admission_v2_rid": sorted(set(adm_dupes))}},
        "Q2": {"dist": human(dist([r["q2_ns"] for r in q2])),
               "samples": q2,
               "gaps": {"issue_without_ready_host": q2_issue_no_ready,
                        "ready_host_without_issue": ready_no_issue,
                        "duplicate_M2_attempt": m2_dupes}},
        "Q3": {
            "all": human(dist([r["q3_ns"] for r in q3])),
            "by_caller": {c: human(dist(v)) for c, v in q3_by_caller.items()},
            "by_caller_backend_lookup": {
                c: human(dist(v)) for c, v in q3_backend_by_caller.items()},
            "by_query_len_bucket": {
                b: human(dist(v)) for b, v in sorted(q3_by_bucket.items())},
            "by_caller_and_bucket": {},
            "kv_hit_pages": {
                "hit": sum(1 for r in q3 if r["kv_hit_pages"] > 0),
                "miss": sum(1 for r in q3 if r["kv_hit_pages"] == 0)},
            "n_a_fields": {
                "lock_wait_ns": sorted({r["lock_wait_ns"] for r in q3}),
                "syscall_wait_ns": sorted({r["syscall_wait_ns"] for r in q3}),
                "all_reduce_ns": sorted({r["all_reduce_ns"] for r in q3})},
            "samples": q3,
        },
        "coverage": coverage,
        "overhead": {k: {kk: vv for kk, vv in v.items()}
                     for k, v in overhead.items()},
        "overhead_human": {k: human(v) for k, v in overhead.items()},
        "overhead_marks_over_1ms": over_1ms,
        "ready_stage": {"count": len(rs),
                        "by_origin": _count_by(rs, "issue_origin"),
                        "by_result": _count_by(rs, "result"),
                        "by_reason": _count_by(rs, "reason")},
    }
    # cross-tab caller x bucket
    for r in q3:
        key = "%s|%s" % (r["caller"], bucket(r["query_len"]))
        result["Q3"]["by_caller_and_bucket"].setdefault(key, []).append(r["q3_ns"])
    result["Q3"]["by_caller_and_bucket"] = {
        k: human(dist(v)) for k, v in result["Q3"]["by_caller_and_bucket"].items()}
    with open(OUT, "w") as fh:
        json.dump(result, fh, indent=1, default=str)
    print("WROTE", OUT)
    print("counts_raw", result["counts_raw"])
    print("Q1", result["Q1"]["dist"])
    print("Q2", result["Q2"]["dist"])
    print("Q3 all", result["Q3"]["all"])
    print("coverage", coverage)
    print("overhead", result["overhead_human"])
    print("over_1ms", over_1ms)
    return 0


def _count_by(rows, key):
    out = {}
    for r in rows:
        out[r[key]] = out.get(r[key], 0) + 1
    return out


if __name__ == "__main__":
    sys.exit(main())
