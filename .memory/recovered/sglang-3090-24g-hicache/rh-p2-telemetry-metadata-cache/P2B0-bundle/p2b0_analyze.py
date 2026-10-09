#!/usr/bin/env python3
"""P2-B0 per-cell summary from join.jsonl + gpu.csv + metrics.csv + server-log.

Contract: work/P2B0-EXECUTION-CONTRACT-20260912.md (sec. 5 metrics + seams)
Semantics: work/P2-B0-CONTRACT-20260911-R71.md (scenario defs, four-term split).

Throughput (user ruling 2026-09-12): ``total_throughput`` is removed.  The four
authoritative metrics are ``aggregate_output_tps``, ``request_tps``,
``effective_compute_tps`` and ``served_context_tps``; each is ``not computable``
with a named reason when an input is missing, never 0.

The server-side probe extraction below reuses the exact regular expressions and
join logic from work/E4-bundle/extract_e4.py (M1/M2/M3, admission.v2,
ready_host) to compute:
  queue_lead_q1 = admission_monotonic_ns - enqueue_mono_ns        (join by rid)
  stage_q2      = ready_monotonic_ns     - prefetch_issue_mono_ns (join by attempt_id)

Client-side metrics use the real streaming timestamps recorded by
``p2b0_driver.py``.  Scenario classification uses the verbatim ``usage`` /
``sglext.cached_tokens_details`` fields when present and the server probe to
separate RH-staged-L3 from cold-L3; anything unclassifiable is reported as
``unclassified`` rather than guessed.

Idle split: ``gpu_idle_total`` is the fraction of the measure window with
``utilization_gpu < --idle-util-threshold``.  ``cache_induced_gpu_idle`` is
reported with two seams:

  * ``cache_induced_gpu_idle_engine`` (coarse): the idle subset whose nearest
    ``/metrics`` sample (within ``--join-tolerance-ms``) has
    ``num_running_reqs + num_queue_reqs > 0`` (runnable work exists in the
    engine).  Requires the ``sglang:num_running_reqs`` / ``sglang:num_queue_reqs``
    series to be present; otherwise ``not computable`` with the reason.
  * ``cache_induced_gpu_idle_restore`` (precise): the idle subset while some rid
    is inside a cache-wait interval, defined per rid as the union of
    ``[prefetch_issue_mono_ns, ready_monotonic_ns]`` pairs matched by
    ``attempt_id`` (``prefetch_issued`` -> ``ready_host``).  ``restore_state`` /
    ``restore_success`` / ``restore_recompute`` corroborate the outcome but carry
    only epoch ``ts_ms`` (no monotonic stamp), so they cannot bound a mono
    interval; rids with restore evidence but no bounded interval are reported
    explicitly.

Missing inputs are ``not computable`` with a named reason, never 0.

Usage:
  python p2b0_analyze.py --cell-json dry-run/cell.json
  python p2b0_analyze.py --join J --gpu G --metrics M --server-log L \
      --out cell-summary.json
"""
import argparse
import bisect
import csv
import hashlib
import json
import os
import re
import statistics
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))

# ---- exact regexes from work/E4-bundle/extract_e4.py (do not drift) ----
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
# P2A restore lifecycle events (used for the restore-interval idle seam).  These
# carry only epoch ``ts_ms``; the monotonic-bounded interval comes from
# prefetch_issued (M2) -> ready_host.  See ``compute_restore_intervals``.
RE_RSTATE = re.compile(
    r"evt=restore_state rid=(\S+) state=(\S+) reason=(\S+)")
RE_RSUCCESS = re.compile(
    r"evt=restore_success rid=(\S+) n_tokens=(\d+)")
RE_RRECOMP = re.compile(
    r"evt=restore_recompute rid=(\S+) cause=(\S+) "
    r"final_storage_survivability=(\S+)")
RE_RREADY = re.compile(
    r"evt=restore_ready rid=(\S+)")

TERMINAL_FAIL = (None, "", "error", "abort", "cancelled")


# --------------------------------------------------------------------------
# generic helpers
# --------------------------------------------------------------------------
def sha256_file(path):
    try:
        h = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:  # noqa: BLE001
        return None


def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:  # noqa: BLE001
        return None


def load_jsonl(path):
    rows = []
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:  # noqa: BLE001
                continue
    return rows


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
    vals = [float(v) for v in vals if v is not None]
    if not vals:
        return {"count": 0}
    return {
        "count": len(vals),
        "p50": pct(vals, 0.50),
        "p95": pct(vals, 0.95),
        "p99": pct(vals, 0.99),
        "min": min(vals),
        "max": max(vals),
        "mean": statistics.fmean(vals),
    }


def dist_ns(vals):
    d = dist(vals)
    if d["count"] == 0:
        return {"count": 0}
    out = {"count": d["count"], "unit": "ns"}
    for k in ("p50", "p95", "p99", "min", "max", "mean"):
        out[k + "_ns"] = round(d[k], 1)
        out[k + "_ms"] = round(d[k] / 1e6, 4)
    return out


# --------------------------------------------------------------------------
# server log probe window
# --------------------------------------------------------------------------
def parse_server_log(path, start_line=None, end_line=None):
    m1, m2, m3, adm, rh, rs = [], [], [], [], [], []
    rstate, rsucc, rrecomp, rready = [], [], [], []
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for ln, line in enumerate(fh, 1):
            if start_line and ln < start_line:
                continue
            if end_line and ln > end_line:
                break
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
                    m2.append({"rid": g.group(1),
                               "prefetch_length": int(g.group(2)),
                               "issue": int(g.group(3)),
                               "attempt_id": g.group(4),
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
                               "all_reduce_ns": g.group(6),
                               "caller": g.group(7), "rid": g.group(8),
                               "attempt_id": g.group(9),
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
                               "attempt_id": g.group(3),
                               "issue_origin": g.group(4),
                               "restore_state_after": g.group(7),
                               "result": g.group(8), "reason": g.group(9),
                               "frontier_rank": int(g.group(10))})
            elif "evt=restore_state" in line:
                g = RE_RSTATE.search(line)
                if g:
                    rstate.append({"rid": g.group(1), "state": g.group(2),
                                   "reason": g.group(3)})
            elif "evt=restore_success" in line:
                g = RE_RSUCCESS.search(line)
                if g:
                    rsucc.append({"rid": g.group(1),
                                  "n_tokens": int(g.group(2))})
            elif "evt=restore_recompute" in line:
                g = RE_RRECOMP.search(line)
                if g:
                    rrecomp.append({"rid": g.group(1), "cause": g.group(2),
                                    "survivability": g.group(3)})
            elif "evt=restore_ready" in line:
                g = RE_RREADY.search(line)
                if g:
                    rready.append({"rid": g.group(1)})
    return {"M1": m1, "M2": m2, "M3": m3, "admission": adm,
            "ready_host": rh, "ready_stage": rs,
            "restore_state": rstate, "restore_success": rsucc,
            "restore_recompute": rrecomp, "restore_ready": rready}


def compute_q1(parsed):
    enq = {}
    for r in parsed["M1"]:
        enq.setdefault(r["rid"], r)
    adm = {}
    for a in parsed["admission"]:
        adm.setdefault(a["rid"], a)
    vals = []
    missing = 0
    not_later = 0
    for rid, e in enq.items():
        a = adm.get(rid)
        if a is None:
            missing += 1
            continue
        d = a["admission"] - e["enqueue"]
        if d < 0:
            not_later += 1
            continue
        vals.append(d)
    return vals, {
        "enqueue_rids": len(enq),
        "admission_rids": len(adm),
        "no_admission_v2": missing,
        "admission_not_after_enqueue": not_later,
    }


def compute_q2(parsed):
    m2 = {}
    for r in parsed["M2"]:
        m2.setdefault(r["attempt_id"], r)
    rh = {}
    for r in parsed["ready_host"]:
        rh.setdefault(r["attempt_id"], r)
    vals = []
    missing = 0
    for aid, r in m2.items():
        h = rh.get(aid)
        if h is None:
            missing += 1
            continue
        vals.append(h["ready"] - r["issue"])
    ready_no_issue = sum(1 for a in rh if a not in m2)
    return vals, {
        "prefetch_attempts": len(m2),
        "ready_host_attempts": len(rh),
        "issue_without_ready_host": missing,
        "ready_host_without_issue": ready_no_issue,
    }


def compute_proxy_m1_m2(parsed, w0=None, w1=None):
    """Fallback RH-lead proxy: enqueue_mono_ns (M1) -> first prefetch_issued
    (M2) per rid.  This is NOT ``queue_lead_q1`` (which needs admission.v2);
    it measures how long after enqueue the prefetch is issued under the RH
    profile.  Returns (all_vals, window_vals, gaps)."""
    enq = {}
    for r in parsed["M1"]:
        enq.setdefault(r["rid"], r)
    first_m2 = {}
    for r in parsed["M2"]:
        cur = first_m2.get(r["rid"])
        if cur is None or r["issue"] < cur["issue"]:
            first_m2[r["rid"]] = r
    vals = []
    win = []
    missing = 0
    not_later = 0
    for rid, e in enq.items():
        m = first_m2.get(rid)
        if m is None:
            missing += 1
            continue
        d = m["issue"] - e["enqueue"]
        if d < 0:
            not_later += 1
            continue
        vals.append(d)
        if (w0 is not None and w1 is not None
                and w0 <= e["enqueue"] <= w1):
            win.append(d)
    return vals, win, {
        "enqueue_rids": len(enq),
        "enqueue_rids_with_prefetch": sum(1 for rid in enq if rid in first_m2),
        "enqueue_without_prefetch": missing,
        "prefetch_not_after_enqueue": not_later,
    }


def compute_restore_intervals(parsed):
    """Per-rid cache-wait intervals from monotonic probe events.

    Interval definition: for every ``ready_host`` (``ready_monotonic_ns``) that
    matches a ``prefetch_issued`` (``prefetch_issue_mono_ns``) by ``attempt_id``,
    the closed interval ``[issue, ready]`` (when ``ready >= issue``).  Returns
    ``(intervals, meta)`` where intervals are ``(start_ns, end_ns, rid,
    attempt_id)``.  Unmatched events are reported, never imputed.
    """
    m2_by_attempt = {}
    for r in parsed["M2"]:
        m2_by_attempt.setdefault(r["attempt_id"], r)
    rh_attempts = set()
    intervals = []
    matched = 0
    bad_order = 0
    for h in parsed["ready_host"]:
        rh_attempts.add(h["attempt_id"])
        m = m2_by_attempt.get(h["attempt_id"])
        if m is None:
            continue
        matched += 1
        if h["ready"] < m["issue"]:
            bad_order += 1
            continue
        intervals.append((m["issue"], h["ready"], m["rid"], h["attempt_id"]))
    issue_no_ready = [a for a in m2_by_attempt if a not in rh_attempts]
    ready_no_issue = sorted(
        set(h["attempt_id"] for h in parsed["ready_host"]
            if h["attempt_id"] not in m2_by_attempt))
    state_counts = {}
    for r in parsed["restore_state"]:
        state_counts[r["state"]] = state_counts.get(r["state"], 0) + 1
    # rids that show restore lifecycle evidence but have no mono-bounded interval
    restore_rids = set()
    for key in ("restore_state", "restore_success", "restore_recompute",
                "restore_ready"):
        for r in parsed[key]:
            restore_rids.add(r["rid"])
    bounded_rids = set(iv[2] for iv in intervals)
    unbounded = sorted(restore_rids - bounded_rids)
    meta = {
        "prefetch_attempts": len(m2_by_attempt),
        "ready_host_attempts": len(rh_attempts),
        "matched_pairs": matched,
        "ready_before_issue": bad_order,
        "issue_without_ready_host": len(issue_no_ready),
        "ready_host_without_issue": len(ready_no_issue),
        "restore_state_counts": state_counts,
        "restore_success_count": len(parsed["restore_success"]),
        "restore_recompute_count": len(parsed["restore_recompute"]),
        "restore_ready_count": len(parsed["restore_ready"]),
        "rids_with_restore_evidence": len(restore_rids),
        "rids_with_bounded_interval": len(bounded_rids),
        "rids_with_restore_evidence_but_no_bounded_interval": len(unbounded),
        "unbounded_interval_rids_sample": unbounded[:20],
        "unbounded_reason": (
            "restore_state/restore_success/restore_recompute carry only epoch "
            "ts_ms (no monotonic_ns) and a MISS_RECOMPUTE has no ready_host, so "
            "no [prefetch_issue, ready_host] interval can be closed in the "
            "monotonic clock; WAIT_CAPACITY after ready_host is likewise "
            "unbounded (no compute-start event)"),
    }
    return intervals, meta


def merge_intervals(intervals):
    """Merge ``(start, end, ...)`` tuples into a sorted list of ``(start, end)``
    unions (ignores non-positive spans)."""
    out = []
    for iv in sorted(intervals, key=lambda x: (x[0], x[1])):
        a, b = iv[0], iv[1]
        if b <= a:
            continue
        if out and a <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def prestaged_rids(parsed):
    """RH-staged-L3 = a ready_host completed at/before admission.v2 for the rid."""
    adm = {}
    for a in parsed["admission"]:
        adm.setdefault(a["rid"], a["admission"])
    out = set()
    for h in parsed["ready_host"]:
        fr = h.get("finalize_result")
        if fr not in ("accepted", None):
            continue
        a = adm.get(h["rid"])
        if a is not None and h["ready"] <= a:
            out.add(h["rid"])
    return out


def server_section(parsed, w0, w1, nc):
    """Server-side probe section.  ``parsed`` is a ``parse_server_log`` dict (or
    None when the log was unavailable)."""
    if parsed is None:
        nc("server", "no server-log path supplied or log unavailable")
        return {"status": "not computable",
                "reason": "no server-log path supplied or log unavailable"}
    q1, q1_gaps = compute_q1(parsed)
    q2, q2_gaps = compute_q2(parsed)
    proxy, proxy_win, proxy_gaps = compute_proxy_m1_m2(parsed, w0, w1)
    if q1_gaps.get("admission_rids", 0) == 0:
        q1_out = {
            "status": "not computable",
            "value": "not computable",
            "reason": "admission.v2 only emitted on AddReqResult.CONTINUE",
            "n": 0,
            "dist": {"count": 0},
            "seam": "admission_monotonic_ns - enqueue_mono_ns",
        }
        nc("server.queue_lead_q1",
           "admission.v2 only emitted on AddReqResult.CONTINUE")
    else:
        q1_out = {
            "status": "ok",
            "dist": dist_ns(q1),
            "n": len(q1),
            "seam": "admission_monotonic_ns - enqueue_mono_ns",
        }
    if proxy:
        proxy_out = {
            "status": "ok",
            "definition": ("enqueue_mono_ns -> prefetch_issued_mono_ns, per "
                           "rid; NOT enqueue->admission"),
            "proxy_for": ("queue_lead_q1 fallback only; MUST NOT be aliased "
                          "with or presented as the real enqueue -> admission "
                          "duration"),
            "dist": dist_ns(proxy),
            "n": len(proxy),
            "dist_measure_window": dist_ns(proxy_win),
            "n_measure_window": len(proxy_win),
            "gaps": proxy_gaps,
        }
    else:
        proxy_out = {
            "status": "not computable",
            "value": "not computable",
            "reason": ("no rid has both enqueue_mono_ns (M1) and "
                       "prefetch_issued (M2)"),
            "n": 0,
            "dist": {"count": 0},
            "definition": ("enqueue_mono_ns -> prefetch_issued_mono_ns, per "
                           "rid; NOT enqueue->admission"),
            "proxy_for": ("queue_lead_q1 fallback only; MUST NOT be aliased "
                          "with or presented as the real enqueue -> admission "
                          "duration"),
            "gaps": proxy_gaps,
        }
    return {
        "counts_raw": {k: len(v) for k, v in parsed.items()},
        "queue_lead_q1": q1_out,
        "prefetch_lead_proxy": proxy_out,
        "stage_q2": {"dist": dist_ns(q2), "n": len(q2),
                     "seam": "ready_monotonic_ns - prefetch_issue_mono_ns"},
        "gaps": {"q1": q1_gaps, "q2": q2_gaps},
    }


# --------------------------------------------------------------------------
# scenario classification
# --------------------------------------------------------------------------
def cache_details(row):
    for key in ("cached_tokens_details",):
        v = row.get(key)
        if isinstance(v, dict) and any(k in v for k in ("device", "host", "storage")):
            return v
    sg = row.get("sglext")
    if isinstance(sg, dict):
        v = sg.get("cached_tokens_details")
        if isinstance(v, dict) and any(k in v for k in ("device", "host", "storage")):
            return v
    usage = row.get("usage")
    if isinstance(usage, dict):
        v = usage.get("cached_tokens_details")
        if isinstance(v, dict) and any(k in v for k in ("device", "host", "storage")):
            return v
    return None


def classify(row, prestaged):
    """Frozen scenario classes (R71 3.2).  Never guesses details that are absent."""
    details = cache_details(row)
    if details is not None:
        dev = int(details.get("device") or 0)
        host = int(details.get("host") or 0)
        store = int(details.get("storage") or 0)
        if store > 0:
            return ("RH-staged-L3" if row.get("rid") in prestaged
                    else "cold-L3")
        if host > 0:
            return "L2-restore"
        if dev > 0:
            return "L1-hit"
        return "cold-L3" if row.get("phase") == "prime" else "unclassified"
    return "unclassified"


# --------------------------------------------------------------------------
# client section
# --------------------------------------------------------------------------
def client_section(rows, prestaged, w0, w1, nc):
    window_s = (w1 - w0) / 1e9 if (w0 is not None and w1 is not None
                                   and w1 > w0) else None
    measure = [r for r in rows if r.get("phase") == "measure"]
    good = [r for r in measure
            if str(r.get("http")) == "200"
            and r.get("finish_reason") not in TERMINAL_FAIL]
    bad_http = sum(1 for r in rows if str(r.get("http")) != "200")
    scenarios = {}
    ttft_by = {}
    tftt_by = {}
    for r in good:
        sc = classify(r, prestaged)
        scenarios[sc] = scenarios.get(sc, 0) + 1
        if r.get("ttft_s") is not None:
            ttft_by.setdefault(sc, []).append(r["ttft_s"])
            ttft_by.setdefault("overall", []).append(r["ttft_s"])
        if r.get("tftt_s") is not None:
            tftt_by.setdefault(sc, []).append(r["tftt_s"])
            tftt_by.setdefault("overall", []).append(r["tftt_s"])

    if window_s is None:
        agg = nc("client.aggregate_output_tps", "measure window not derivable")
        rps = nc("client.request_throughput", "measure window not derivable")
    else:
        tok_rows = [r for r in good
                    if isinstance(r.get("usage"), dict)
                    and r["usage"].get("completion_tokens") is not None]
        if not tok_rows:
            agg = nc("client.aggregate_output_tps",
                     "no completion_tokens in any measure usage object")
        else:
            total_tokens = sum(r["usage"]["completion_tokens"] for r in tok_rows)
            agg = round(total_tokens / window_s, 4)
        rps = round(len(good) / window_s, 4) if window_s > 0 else None

    return {
        "requests": {
            "total": len(rows),
            "measure": len(measure),
            "completed_measure": len(good),
            "bad_http": bad_http,
        },
        "completion_set": completion_set(rows),
        "scenario_counts": scenarios,
        "ttft_s": {k: dist(v) for k, v in ttft_by.items()},
        "tftt_s": {k: dist(v) for k, v in tftt_by.items()},
        "aggregate_output_tps": agg,
        "request_throughput": rps,
        "tokens_coverage": {
            "rows_with_completion_tokens": len(
                [r for r in good if isinstance(r.get("usage"), dict)
                 and r["usage"].get("completion_tokens") is not None]),
            "completed_measure_rows": len(good),
        },
        "classification_basis": (
            "usage.prompt_tokens_details.cached_tokens / "
            "sglext.cached_tokens_details{device,host,storage}; "
            "RH-staged vs cold from ready_host<=admission.v2 by rid"),
    }


THROUGHPUT_DEFS = {
    "aggregate_output_tps": (
        "sum(output_tokens) over completed measure requests / wall_time"),
    "request_tps": "completed_measure_requests / wall_time",
    "effective_compute_tps": (
        "(sum(uncached_prefill_tokens) + sum(output_tokens)) / wall_time; "
        "uncached_prefill_tokens = prompt_tokens - cached prompt tokens "
        "(device+host+storage); HARD RULE: L1/L2/L3-hit prefix tokens are never "
        "counted as input throughput"),
    "served_context_tps": (
        "(sum(all_prompt_tokens) + sum(output_tokens)) / wall_time; "
        "product/capacity indicator, NOT compute throughput"),
}
THROUGHPUT_KEYS = ("aggregate_output_tps", "request_tps",
                   "effective_compute_tps", "served_context_tps")


def _row_completion_tokens(r):
    v = r.get("completion_tokens")
    if v is None and isinstance(r.get("usage"), dict):
        v = r["usage"].get("completion_tokens")
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _row_prompt_tokens(r):
    v = r.get("prompt_tokens")
    if v is None and isinstance(r.get("usage"), dict):
        v = r["usage"].get("prompt_tokens")
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _row_cached_prompt_tokens(r):
    """Return (cached_tokens|None, source).  Prefers the device+host+storage
    breakdown; falls back to usage.prompt_tokens_details.cached_tokens."""
    d = cache_details(r)
    if d is not None:
        try:
            dev = int(d.get("device") or 0)
            host = int(d.get("host") or 0)
            store = int(d.get("storage") or 0)
        except (TypeError, ValueError):
            return None, "cached_tokens_details unparseable"
        return dev + host + store, "cached_tokens_details"
    usage = r.get("usage")
    if isinstance(usage, dict):
        ptd = usage.get("prompt_tokens_details")
        if isinstance(ptd, dict) and ptd.get("cached_tokens") is not None:
            try:
                return int(ptd["cached_tokens"]), (
                    "usage.prompt_tokens_details.cached_tokens")
            except (TypeError, ValueError):
                return None, "usage.prompt_tokens_details.cached_tokens invalid"
    return None, "no cached_tokens_details"


def throughput_section(rows, w0, w1, nc):
    """The four authoritative throughput metrics (total_throughput removed)."""
    measure = [r for r in rows if r.get("phase") == "measure"]
    good = [r for r in measure
            if str(r.get("http")) == "200"
            and r.get("finish_reason") not in TERMINAL_FAIL]
    out = {
        "completed_measure_requests": len(good),
        "definitions": dict(THROUGHPUT_DEFS),
    }
    if w0 is None or w1 is None or w1 <= w0:
        for k in THROUGHPUT_KEYS:
            out[k] = nc("throughput." + k,
                        "wall_time not derivable (measure window missing)")
        return out
    window_s = (w1 - w0) / 1e9
    out["wall_time_s"] = round(window_s, 6)

    n_good = len(good)
    n_ct = sum(1 for r in good if _row_completion_tokens(r) is not None)
    n_pt = sum(1 for r in good if _row_prompt_tokens(r) is not None)
    n_cached = sum(1 for r in good if _row_cached_prompt_tokens(r)[0] is not None)
    out["coverage"] = {
        "completed_measure_rows": n_good,
        "rows_with_output_tokens": n_ct,
        "rows_with_prompt_tokens": n_pt,
        "rows_with_cached_breakdown": n_cached,
    }

    # ---- aggregate_output_tps ----
    if n_ct == 0:
        out["aggregate_output_tps"] = nc(
            "throughput.aggregate_output_tps",
            "no completion/output tokens in any completed measure row")
    else:
        total_out = sum(_row_completion_tokens(r) for r in good
                        if _row_completion_tokens(r) is not None)
        out["aggregate_output_tps"] = round(total_out / window_s, 4)
        out["aggregate_output_tps_output_tokens"] = total_out

    # ---- request_tps ----
    out["request_tps"] = round(n_good / window_s, 4)
    out["request_tps_completed_requests"] = n_good

    # ---- served_context_tps (product/capacity indicator) ----
    if n_pt < n_good:
        out["served_context_tps"] = nc(
            "throughput.served_context_tps",
            ("prompt_tokens missing for %d of %d completed measure rows; "
             "sum(all_prompt_tokens) would be incomplete"
             % (n_good - n_pt, n_good)))
    elif n_ct < n_good:
        out["served_context_tps"] = nc(
            "throughput.served_context_tps",
            ("output tokens missing for %d of %d completed measure rows"
             % (n_good - n_ct, n_good)))
    else:
        total_pt = sum(_row_prompt_tokens(r) for r in good)
        total_out = sum(_row_completion_tokens(r) for r in good)
        out["served_context_tps"] = round((total_pt + total_out) / window_s, 4)
        out["served_context_tps_prompt_tokens"] = total_pt
        out["served_context_tps_output_tokens"] = total_out

    # ---- effective_compute_tps (excludes all hit prefix tokens) ----
    missing_parts = []
    if n_pt < n_good:
        missing_parts.append("prompt_tokens missing for %d rows" % (n_good - n_pt))
    if n_ct < n_good:
        missing_parts.append("output tokens missing for %d rows" % (n_good - n_ct))
    if n_cached < n_good:
        missing_parts.append(
            "cached_tokens_details missing for %d rows; uncached prefill cannot "
            "be derived without overcounting hit prefix tokens"
            % (n_good - n_cached))
    bad_rows = []
    if not missing_parts:
        uncached_total = 0
        total_out = 0
        for r in good:
            pt = _row_prompt_tokens(r)
            ct = _row_completion_tokens(r)
            cached, _src = _row_cached_prompt_tokens(r)
            if cached > pt:
                bad_rows.append(r.get("rid"))
                continue
            uncached_total += pt - cached
            total_out += ct
    if missing_parts or bad_rows:
        reason = "; ".join(missing_parts)
        if bad_rows:
            reason = (reason + "; " if reason else "") + (
                "cached_tokens > prompt_tokens for %d rows: %s"
                % (len(bad_rows), bad_rows[:5]))
        out["effective_compute_tps"] = nc(
            "throughput.effective_compute_tps", reason)
    else:
        out["effective_compute_tps"] = round(
            (uncached_total + total_out) / window_s, 4)
        out["effective_compute_tps_uncached_prefill_tokens"] = uncached_total
        out["effective_compute_tps_output_tokens"] = total_out
    return out


def completion_set(rows):
    total = len(rows)
    bad = sum(1 for r in rows if str(r.get("http")) != "200")
    completed = sum(
        1 for r in rows
        if str(r.get("http")) == "200"
        and r.get("finish_reason") not in TERMINAL_FAIL)
    reasons = {}
    for r in rows:
        key = r.get("finish_reason")
        key = "null" if key is None else str(key)
        reasons[key] = reasons.get(key, 0) + 1
    return {"requests_total": total, "completed": completed, "bad_http": bad,
            "finish_reasons": reasons}


# --------------------------------------------------------------------------
# idle section
# --------------------------------------------------------------------------
def _read_gpu(path):
    rows = []
    with open(path, "r", encoding="utf-8", newline="") as fh:
        for rec in csv.DictReader(fh):
            try:
                ns = int(rec["mono_ns"])
            except (KeyError, ValueError, TypeError):
                continue
            util = rec.get("utilization_gpu")
            try:
                util = float(util)
            except (ValueError, TypeError):
                util = None
            rows.append((ns, util))
    return rows


def _read_metrics(path):
    """Read metrics.csv into dicts.  ``num_queue_reqs_present`` /
    ``num_running_reqs_present`` are honoured when present (new sampler); for
    legacy files presence falls back to a non-empty/numeric value cell.  An
    absent metric yields ``present=False`` -- never a silent 0."""
    def _f(rec, key):
        try:
            return float(rec.get(key))
        except (ValueError, TypeError):
            return None

    def _rec_present(rec, present_key, value_key):
        v = rec.get(present_key)
        if v is not None and str(v).strip() != "":
            return str(v).strip() == "1"
        raw = rec.get(value_key)
        if raw is None or str(raw).strip() == "":
            return False
        try:
            float(raw)
            return True
        except ValueError:
            return False

    rows = []
    with open(path, "r", encoding="utf-8", newline="") as fh:
        for rec in csv.DictReader(fh):
            try:
                ns = int(rec["mono_ns"])
            except (KeyError, ValueError, TypeError):
                continue
            rows.append({
                "ns": ns,
                "queue": _f(rec, "num_queue_reqs"),
                "running": _f(rec, "num_running_reqs"),
                "decode": _f(rec, "realtime_decode_tokens"),
                "q_present": _rec_present(
                    rec, "num_queue_reqs_present", "num_queue_reqs"),
                "r_present": _rec_present(
                    rec, "num_running_reqs_present", "num_running_reqs"),
                "http": (rec.get("http") or "").strip(),
                "err": (rec.get("err") or "").strip(),
                "q_err": (rec.get("num_queue_reqs_err") or "").strip(),
                "r_err": (rec.get("num_running_reqs_err") or "").strip(),
            })
    return rows


def _nearest(keys, idxs, want):
    if not keys:
        return None
    i = bisect.bisect_left(keys, want)
    best = None
    for j in (i - 1, i):
        if 0 <= j < len(keys):
            d = abs(keys[j] - want)
            if best is None or d < best[0]:
                best = (d, j)
    return best


def _overlap_len(merged, a, b):
    """Length of [a,b) covered by the sorted, disjoint ``merged`` intervals."""
    total = 0
    for s, e in merged:
        if e <= a:
            continue
        if s >= b:
            break
        total += max(0, min(e, b) - max(s, a))
    return total


def _metrics_diag(metrics):
    """Short honest transport diagnosis for the engine seam."""
    n = len(metrics)
    http_counts = {}
    err_sample = None
    for m in metrics:
        http_counts[m["http"]] = http_counts.get(m["http"], 0) + 1
        if err_sample is None and m["err"]:
            err_sample = m["err"]
    return n, http_counts, err_sample


def idle_section(gpu_path, metrics_path, w0, w1, threshold, tol_ms, nc,
                 restore_intervals=None, restore_meta=None):
    if not gpu_path or not os.path.exists(gpu_path):
        nc("idle", "gpu.csv not found: %s" % gpu_path)
        return {"status": "not computable",
                "reason": "gpu.csv not found: %s" % gpu_path}
    if w0 is None or w1 is None or w1 <= w0:
        nc("idle", "measure window not derivable from join.jsonl")
        return {"status": "not computable",
                "reason": "measure window not derivable from join.jsonl"}
    try:
        gpu = _read_gpu(gpu_path)
    except Exception as e:  # noqa: BLE001
        nc("idle", "gpu.csv parse failed: %r" % (e,))
        return {"status": "not computable",
                "reason": "gpu.csv parse failed: %r" % (e,)}
    # dedupe multi-GPU rows by mono_ns, keeping max utilization
    by_ns = {}
    for ns, util in gpu:
        if ns < w0 or ns > w1:
            continue
        if ns not in by_ns or (util is not None
                               and (by_ns[ns] is None or util > by_ns[ns])):
            by_ns[ns] = util
    timeline = [(ns, by_ns[ns]) for ns in sorted(by_ns)
                if by_ns[ns] is not None]
    if not timeline:
        nc("idle.gpu_idle_total", "no GPU samples inside measure window")
        return {"status": "not computable",
                "reason": "no GPU samples inside measure window"}

    metrics = []
    if metrics_path and os.path.exists(metrics_path):
        try:
            metrics = sorted(_read_metrics(metrics_path),
                             key=lambda m: m["ns"])
        except Exception:  # noqa: BLE001
            metrics = []
    metrics = [m for m in metrics if w0 <= m["ns"] <= w1]
    mkeys = [m["ns"] for m in metrics]
    tol_ns = int(tol_ms * 1e6)

    total_ns = w1 - w0
    attributed = 0
    idle_ns = 0
    idle_samples = 0
    engine_idle_ns = 0
    engine_idle_samples = 0
    engine_evaluable_samples = 0
    engine_missing_metric_samples = 0
    restore_idle_ns = 0
    restore_idle_samples = 0

    merged = merge_intervals(restore_intervals or [])
    restore_wait_window_ns = _overlap_len(merged, w0, w1)

    for i, (ns, util) in enumerate(timeline):
        seg_start = max(ns, w0)
        seg_end = timeline[i + 1][0] if i + 1 < len(timeline) else w1
        seg_end = min(seg_end, w1)
        if seg_end <= seg_start:
            continue
        attributed += seg_end - seg_start
        if util < threshold:
            idle_ns += seg_end - seg_start
            idle_samples += 1
            hit = _nearest(mkeys, None, ns) if metrics else None
            if hit is not None and hit[0] <= tol_ns:
                m = metrics[hit[1]]
                if m["r_present"] and m["q_present"]:
                    engine_evaluable_samples += 1
                    pending = ((m["running"] or 0.0) + (m["queue"] or 0.0)) > 0
                    if pending:
                        engine_idle_ns += seg_end - seg_start
                        engine_idle_samples += 1
                else:
                    engine_missing_metric_samples += 1
            ov = _overlap_len(merged, seg_start, seg_end)
            if ov > 0:
                restore_idle_ns += ov
                restore_idle_samples += 1

    out = {
        "idle_util_threshold": threshold,
        "join_tolerance_ms": tol_ms,
        "measure_window": {"start_mono_ns": w0, "end_mono_ns": w1,
                           "duration_s": round(total_ns / 1e9, 6)},
        "gpu_samples_in_window": len(timeline),
        "metrics_samples_in_window": len(metrics),
        "attributed_s": round(attributed / 1e9, 6),
        "gpu_idle_total": {
            "fraction": round(idle_ns / total_ns, 6),
            "duration_s": round(idle_ns / 1e9, 6),
            "n_idle_samples": idle_samples,
            "seam": "nvidia-smi utilization_gpu < threshold",
        },
    }

    # ---- engine seam (coarse): running + queue > 0 at the nearest sample ----
    n_samples = len(metrics)
    n_running_present = sum(1 for m in metrics if m["r_present"])
    n_queue_present = sum(1 for m in metrics if m["q_present"])
    if n_samples == 0:
        engine = nc(
            "idle.cache_induced_gpu_idle_engine",
            "metrics.csv missing/unreadable or no samples in measure window; "
            "need '/metrics' num_queue_reqs/num_running_reqs at sub-second "
            "cadence")
    elif n_running_present == 0 or n_queue_present == 0:
        _n, http_counts, err_sample = _metrics_diag(metrics)
        engine = nc(
            "idle.cache_induced_gpu_idle_engine",
            ("num_queue_reqs/num_running_reqs absent in all %d metrics samples "
             "in window (present running=%d queue=%d, http=%s%s); the running "
             "server did not expose sglang:num_running_reqs/sglang:num_queue_reqs "
             "(launch without --enable-metrics yields /metrics HTTP 404)"
             % (n_samples, n_running_present, n_queue_present, http_counts,
                (", err=" + err_sample) if err_sample else "")))
    else:
        engine = {
            "fraction": round(engine_idle_ns / total_ns, 6),
            "duration_s": round(engine_idle_ns / 1e9, 6),
            "n_samples": engine_idle_samples,
            "n_pending_samples": engine_evaluable_samples,
            "n_missing_metric_samples": engine_missing_metric_samples,
            "seam": ("gpu util < threshold AND nearest /metrics sample within "
                     "tolerance has num_running_reqs + num_queue_reqs > 0"),
            "metric_source": ("sglang:num_running_reqs / sglang:num_queue_reqs"),
        }
    # legacy key keeps the engine (coarse) seam for backward compatibility
    out["cache_induced_gpu_idle"] = engine
    out["cache_induced_gpu_idle_engine"] = engine

    # ---- restore seam (precise): rid inside a bounded cache-wait interval ----
    if restore_intervals is None:
        out["cache_induced_gpu_idle_restore"] = nc(
            "idle.cache_induced_gpu_idle_restore",
            "server-log restore intervals unavailable (no readable server log "
            "or no probe events)")
    elif not restore_intervals:
        meta_note = ""
        if restore_meta:
            meta_note = ("; restore_state=%s restore_success=%s "
                         "restore_recompute=%s"
                         % (restore_meta.get("restore_state_counts"),
                            restore_meta.get("restore_success_count"),
                            restore_meta.get("restore_recompute_count")))
        out["cache_induced_gpu_idle_restore"] = nc(
            "idle.cache_induced_gpu_idle_restore",
            ("no attempt-matched prefetch_issued -> ready_host interval could "
             "be closed in the measure window" + meta_note))
    else:
        out["cache_induced_gpu_idle_restore"] = {
            "fraction": round(restore_idle_ns / total_ns, 6),
            "duration_s": round(restore_idle_ns / 1e9, 6),
            "n_idle_samples": restore_idle_samples,
            "n_intervals": len(restore_intervals),
            "n_rids": len(set(iv[2] for iv in restore_intervals)),
            "cache_wait_window_s": round(restore_wait_window_ns / 1e9, 6),
            "seam": ("gpu util < threshold AND sample time inside a per-rid "
                     "[prefetch_issue_mono_ns, ready_monotonic_ns] cache-wait "
                     "interval"),
            "interval_definition": (
                "per-rid union of [prefetch_issue_mono_ns (evt=prefetch_issued), "
                "ready_monotonic_ns (evt=ready_host)] matched by attempt_id"),
            "coverage": restore_meta,
        }
    return out


# --------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(description="P2-B0 per-cell analyzer")
    ap.add_argument("--cell-json", default=None)
    ap.add_argument("--join", default=None)
    ap.add_argument("--gpu", default=None)
    ap.add_argument("--metrics", default=None)
    ap.add_argument("--server-log", default=None)
    ap.add_argument("--log-start-line", type=int, default=None)
    ap.add_argument("--log-end-line", type=int, default=None)
    ap.add_argument("--window-start-ns", type=int, default=None)
    ap.add_argument("--window-end-ns", type=int, default=None)
    ap.add_argument("--idle-util-threshold", type=float, default=10.0)
    ap.add_argument("--join-tolerance-ms", type=float, default=250.0)
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)

    nc_map = {}

    def nc(path, reason):
        nc_map[path] = reason
        return "not computable"

    cell = load_json(args.cell_json) if args.cell_json else None
    base_dir = (os.path.dirname(os.path.abspath(args.cell_json))
                if args.cell_json else HERE)

    def pick(explicit, cell_key, default_name):
        if explicit:
            return explicit
        if isinstance(cell, dict) and cell.get(cell_key):
            return cell[cell_key]
        return os.path.join(base_dir, default_name)

    join_path = pick(args.join, "join_path", "join.jsonl")
    gpu_path = pick(args.gpu, "gpu_path", "gpu.csv")
    metrics_path = pick(args.metrics, "metrics_path", "metrics.csv")
    server_log = args.server_log
    start_line = args.log_start_line
    end_line = args.log_end_line
    if server_log is None and isinstance(cell, dict):
        sl = cell.get("server_log") or {}
        server_log = sl.get("path")
        if start_line is None:
            start_line = sl.get("start_line")
        if end_line is None:
            end_line = sl.get("end_line")
    if server_log is None:
        server_log = "/mnt/data/neuron/sglang-3090-r112-20260911/sglang-server-e.log"

    rows = []
    if os.path.exists(join_path):
        try:
            rows = load_jsonl(join_path)
        except Exception as e:  # noqa: BLE001
            nc("client", "join.jsonl parse failed: %r" % (e,))
    else:
        nc("client", "join.jsonl not found: %s" % join_path)

    # ---- measure window ----
    measure = [r for r in rows if r.get("phase") == "measure"
               and r.get("send_mono_ns") is not None]
    w0 = args.window_start_ns
    w1 = args.window_end_ns
    if w0 is None and measure:
        w0 = min(r["send_mono_ns"] for r in measure)
    if w1 is None and measure:
        last = [r["last_token_mono_ns"] for r in measure
                if r.get("last_token_mono_ns") is not None]
        if last:
            w1 = max(last)
        else:
            ends = [r["send_mono_ns"] + int((r.get("elapsed_s") or 0) * 1e9)
                    for r in measure]
            w1 = max(ends) if ends else None
    if w0 is None or w1 is None:
        nc("window", "measure window not derivable from join.jsonl")

    # ---- server probe (parsed once, reused by server + idle seams) ----
    parsed_log = None
    prestaged = set()
    if server_log and os.path.exists(server_log):
        try:
            parsed_log = parse_server_log(server_log, start_line, end_line)
            prestaged = prestaged_rids(parsed_log)
        except Exception as e:  # noqa: BLE001
            nc("server", "server-log parse failed: %r" % (e,))
            parsed_log = None
    elif not server_log:
        nc("server", "no server-log path supplied")
    else:
        nc("server", "server-log not found: %s" % server_log)
    server = server_section(parsed_log, w0, w1, nc)

    restore_intervals, restore_meta = ((None, None) if parsed_log is None
                                       else compute_restore_intervals(parsed_log))

    client = client_section(rows, prestaged, w0, w1, nc)
    throughput = throughput_section(rows, w0, w1, nc)
    idle = idle_section(gpu_path, metrics_path, w0, w1,
                        args.idle_util_threshold, args.join_tolerance_ms, nc,
                        restore_intervals=restore_intervals,
                        restore_meta=restore_meta)

    # ---- four-term reconciliation (R71 3.4) ----
    good = [r for r in rows if r.get("phase") == "measure"
            and str(r.get("http")) == "200"
            and r.get("finish_reason") not in TERMINAL_FAIL]
    decode_s = sum(r["tftt_s"] for r in good
                   if r.get("tftt_s") is not None)
    uncomputable_terms = ["restore_wait", "queue_wait", "compute"]
    reconciliation = {
        "decode_s": round(decode_s, 6),
        "restore_wait": nc(
            "idle.reconciliation.restore_wait",
            "no per-request WAIT_CAPACITY enter/exit duration seam (R71 3.4)"),
        "queue_wait": nc(
            "idle.reconciliation.queue_wait",
            "no request enqueue timestamp seam on the decode path (R71 3.4)"),
        "compute": nc(
            "idle.reconciliation.compute",
            "no per-request prefill forward duration seam (R71 3.4)"),
        "residual_s": "not computable",
        "residual_reason": (
            "cannot reconcile while %s remain not computable (R71 3.4)"
            % ", ".join(uncomputable_terms)),
    }
    if isinstance(idle, dict):
        eng = idle.get("cache_induced_gpu_idle_engine")
        rst = idle.get("cache_induced_gpu_idle_restore")
        if isinstance(eng, dict):
            reconciliation["cache_induced_gpu_idle_engine_s"] = eng["duration_s"]
        else:
            reconciliation["cache_induced_gpu_idle_engine_s"] = "not computable"
        if isinstance(rst, dict):
            reconciliation["cache_induced_gpu_idle_restore_s"] = rst["duration_s"]
        else:
            reconciliation["cache_induced_gpu_idle_restore_s"] = "not computable"
        preferred = ("restore" if isinstance(rst, dict)
                     else ("engine" if isinstance(eng, dict) else "not computable"))
        reconciliation["cache_induced_gpu_idle_preferred"] = preferred
        reconciliation["cache_induced_gpu_idle_s"] = (
            reconciliation["cache_induced_gpu_idle_%s_s" % preferred]
            if preferred != "not computable" else "not computable")

    window = {
        "start_mono_ns": w0,
        "end_mono_ns": w1,
        "duration_s": (round((w1 - w0) / 1e9, 6)
                       if (w0 is not None and w1 is not None and w1 > w0)
                       else None),
        "source": ("explicit" if (args.window_start_ns is not None
                                  or args.window_end_ns is not None)
                   else "measure_rows"),
    }

    summary = {
        "schema": "p2b0-cell-summary-2",
        "summary_version": 2,
        "cell": {
            "synthetic": bool(cell.get("synthetic")) if isinstance(cell, dict)
            else None,
            "nonce": (cell or {}).get("nonce"),
            "args": (cell or {}).get("args"),
            "driver_sha256": ((cell or {}).get("driver") or {}).get("sha256"),
            "launch_script": (cell or {}).get("launch_script"),
            "completion_set": (cell or {}).get("completion_set"),
        },
        "window": window,
        "client": client,
        "server": server,
        "idle": idle,
        "aggregate_output_tps": throughput["aggregate_output_tps"],
        "request_tps": throughput["request_tps"],
        "effective_compute_tps": throughput["effective_compute_tps"],
        "served_context_tps": throughput["served_context_tps"],
        "throughput": throughput,
        "reconciliation": reconciliation,
        "not_computable": nc_map,
        "provenance": {
            "join": {"path": join_path, "sha256": sha256_file(join_path)},
            "gpu": {"path": gpu_path, "sha256": sha256_file(gpu_path)},
            "metrics": {"path": metrics_path,
                        "sha256": sha256_file(metrics_path)},
            "server_log": {"path": server_log,
                           "start_line": start_line, "end_line": end_line},
            "analyzer": {"path": os.path.abspath(__file__),
                         "sha256": sha256_file(__file__)},
        },
        "generated_mono_ns": time.monotonic_ns(),
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }

    out = args.out
    if not out:
        out = os.path.join(base_dir, "cell-summary.v2.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=1, default=str)
    print("WROTE", out)
    print("window_s", window["duration_s"],
          "completed_measure", client["requests"]["completed_measure"],
          "bad_http", client["requests"]["bad_http"])
    print("aggregate_output_tps", client["aggregate_output_tps"],
          "request_throughput", client["request_throughput"])
    print("request_tps", throughput["request_tps"],
          "effective_compute_tps", throughput["effective_compute_tps"],
          "served_context_tps", throughput["served_context_tps"])
    print("scenarios", client["scenario_counts"])
    q1 = server.get("queue_lead_q1", {})
    proxy = server.get("prefetch_lead_proxy", {})
    if isinstance(q1, dict) and q1.get("status") != "not computable":
        print("queue_lead_q1_n", q1.get("n"), "stage_q2_n",
              server.get("stage_q2", {}).get("n"))
    else:
        print("queue_lead_q1", "not computable",
              "reason", (q1 or {}).get("reason"),
              "stage_q2_n", server.get("stage_q2", {}).get("n"))
    if isinstance(proxy, dict) and proxy.get("status") != "not computable":
        pd = proxy.get("dist", {})
        print("prefetch_lead_proxy_n", proxy.get("n"),
              "p50_ms", pd.get("p50_ms"),
              "n_measure_window", proxy.get("n_measure_window"))
    else:
        print("prefetch_lead_proxy", "not computable",
              "reason", (proxy or {}).get("reason"))
    if isinstance(idle, dict) and "gpu_idle_total" in idle:
        print("gpu_idle_total", idle["gpu_idle_total"])
        print("cache_induced_gpu_idle_engine",
              idle.get("cache_induced_gpu_idle_engine"))
        print("cache_induced_gpu_idle_restore",
              idle.get("cache_induced_gpu_idle_restore"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
