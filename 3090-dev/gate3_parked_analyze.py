#!/usr/bin/env python3
"""gate3_parked_analyze.py -- Phase-2 experiment④: oversub degradation curve
analysis + fit Gate A/B judgement, cross-S comparison.

Reads gate3_parked run dirs produced by gate3_parked.py (one dir per S):

  run_dir/
    runs.csv                    per-request rows (resume rows carry
                                hit_parent_mux, age_at_wake_s, ttft_s, the
                                cached_* hit tokens, prefill_*_delta)
    recompute_attribution.csv   Gate A full-history recompute events with
                                reason tags (capacity_evicted / state_machine /
                                never_built / other)
    join.log                    same rows, JSONL
    mid-run-metrics.txt         gauge time series (incl. l3_physical footprint,
                                eviction_observed)
    verdict.json                run metadata (mode, rh, sessions, ...)

For OVERSUB runs the script emits the degradation-vs-S curve: for each S,
  - L3 residency  = (host_hit + storage_hit) / total served tokens
  - recycle-GC    = evicted/backuped/load_back token deltas + [P3] extent_recycle
                    events from the engine log (--engine-log), + physical L3
                    footprint delta from mid-run l3_physical
  - recompute fraction + per-reason attribution counts (state_machine must be 0
    for the "every recompute is explained by normal capacity eviction" claim)
  - random-resume TTFT p50/p95/p99, >30s/>60s ratios
  - turns/hour
  compared across S under the same H0/seed/active/lambda.

For FIT runs it reports the Gate A+B acceptance table:
  - avoidable historical recompute rate (Gate A: must be 0%)
  - TTFT p50/p95/p99 (Gate B fit: p95<=5s, p99<=10s)
  - storage_hit/session-resume stability, recycle (must be none)

FORBIDDEN CLAIM GUARD
---------------------
For S >= 500 this script reports ONLY within the "oversubscription stress,
degradation curve" framework.  It MUST NOT print a "the 200G L3 can fully park
S x 55K sessions" statement.  A full-retention figure is only meaningful at the
fit anchor (S=100), and any larger-NVMe capacity requirement is left to a later
decision (ledger:2476), never computed/claimed here.

Usage
-----
  # analyze one oversub cell (S=500) with engine log for authoritative recycle:
  python gate3_parked_analyze.py --run-dir /root/evidence-parked/run-S500 \
      --engine-log /root/engine-S500.log

  # cross-S degradation curve (all S cells, same family dir):
  python gate3_parked_analyze.py --family /root/evidence-parked \
      --engine-logs S500=/root/engine-S500.log,S1000=/root/engine-S1000.log \
      --csv degradation_curve.csv

  # fit judgement:
  python gate3_parked_analyze.py --run-dir /root/evidence-parked/run-S100 --fit
"""
import argparse
import csv
import glob
import json
import math
import os
import re
import statistics
import sys

# ---- per-request aggregation helpers (mirror gate2_analyze) ----

def _g(snap, prefix):
    for k, v in snap.items():
        if k.startswith(prefix):
            return v
    return None


def _load_runs(run_dir):
    """Load resume rows from runs.csv (fallback join.log)."""
    rows = []
    p = os.path.join(run_dir, "runs.csv")
    if os.path.exists(p):
        with open(p) as f:
            rd = csv.DictReader(f)
            for r in rd:
                for k, v in r.items():
                    if v == "":
                        r[k] = None
                rows.append(r)
    if rows:
        return rows
    p = os.path.join(run_dir, "join.log")
    if os.path.exists(p):
        for line in open(p):
            try:
                r = json.loads(line)
            except Exception:
                continue
            rows.append(r)
    return rows


def _load_attribution(run_dir):
    out = []
    p = os.path.join(run_dir, "recompute_attribution.csv")
    if os.path.exists(p):
        with open(p) as f:
            for r in csv.DictReader(f):
                out.append(r)
    return out


def _load_mid(run_dir):
    snaps = []
    p = os.path.join(run_dir, "mid-run-metrics.txt")
    if not os.path.exists(p):
        return snaps
    for line in open(p):
        try:
            d = json.loads(line)
        except Exception:
            continue
        snaps.append(d)
    return snaps


def _load_verdict(run_dir):
    p = os.path.join(run_dir, "verdict.json")
    if os.path.exists(p):
        try:
            with open(p) as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def _pct(seq, p):
    seq = sorted(x for x in seq if x is not None)
    if not seq:
        return None
    idx = max(0, min(len(seq) - 1, int(math.ceil(p / 100.0 * len(seq)) - 1)))
    return seq[idx]


def _num(r, key):
    try:
        return float(r[key])
    except (TypeError, KeyError, ValueError):
        return None


# ---- engine log event parsing (authoritative Gate A + Gate C evidence) ----
# Event formats from scheduler.py/extent_allocator.py (spec e5 §3.1):
#   [P3] ts_ms=.. evt=extent_recycle slot=.. generation=.. freed=<bytes>
#   [P3] ts_ms=.. evt=ready_stage rid=.. result=.. state=.. headroom=..
#   [P3] ts_ms=.. evt=restore_ready rid=..
#   [P3] ts_ms=.. evt=restore_state rid=.. state=.. reason=..
#   [P3] ts_ms=.. evt=admission rid=.. pos=.. qlen=.. running_bs=.. can_run=..
#   [P3] ts_ms=.. evt=restore_recompute rid=.. cause=.. final_storage_survivability=..
# All are line-level; banned cross-span patterns are not used here.

_TS_MS_RE = re.compile(r"ts_ms=(\d+)")
_RID_RE = re.compile(r"rid=(\S+)")


def _ev_ts(line):
    m = _TS_MS_RE.search(line)
    if not m:
        return None
    return int(m.group(1)) / 1000.0  # ms -> s


def _ev_rid(line):
    m = _RID_RE.search(line)
    return m.group(1) if m else None


def parse_engine_events(engine_log_path):
    """Parse the engine log into a list of (event_type, ts_s, rid, attrs).
    Event types: extent_recycle / ready_stage / restore_ready / restore_state /
    admission / restore_recompute.  Returns a dict with per-type lists and an
    extent_recycle timeline (ts-only) for the Gate A flip."""
    if not engine_log_path or not os.path.exists(engine_log_path):
        return None
    out = {
        "extent_recycle": [],   # (ts_s, freed_bytes)
        "ready_stage": [],      # (ts_s, rid, result, state)
        "restore_ready": [],    # (ts_s, rid)
        "restore_state": [],    # (ts_s, rid, state, reason)
        "admission": [],        # (ts_s, rid)
        "restore_recompute": [],  # (ts_s, rid, cause)
    }
    ev_re = re.compile(r"evt=(\S+)")
    for line in open(engine_log_path, errors="replace"):
        m = ev_re.search(line)
        if not m:
            continue
        ev = m.group(1)
        ts = _ev_ts(line)
        if ev == "extent_recycle":
            freed = 0
            fm = re.search(r"freed=(\d+)", line)
            if fm:
                freed = int(fm.group(1))
            out["extent_recycle"].append((ts, freed))
        elif ev == "ready_stage":
            rid = _ev_rid(line)
            res = re.search(r"result=(\S+)", line)
            st = re.search(r"state=(\S+)", line)
            out["ready_stage"].append(
                (ts, rid, res.group(1) if res else None,
                 st.group(1) if st else None))
        elif ev == "restore_ready":
            out["restore_ready"].append((ts, _ev_rid(line)))
        elif ev == "restore_state":
            rid = _ev_rid(line)
            st = re.search(r"state=(\S+)", line)
            rn = re.search(r"reason=(\S+)", line)
            out["restore_state"].append(
                (ts, rid, st.group(1) if st else None,
                 rn.group(1) if rn else None))
        elif ev == "admission":
            out["admission"].append((ts, _ev_rid(line)))
        elif ev == "restore_recompute":
            rid = _ev_rid(line)
            cause = re.search(r"cause=(\S+)", line)
            out["restore_recompute"].append(
                (ts, rid, cause.group(1) if cause else None))
    return out


def parse_extent_recycle(engine_log_path):
    """Count [P3] evt=extent_recycle events and their freed bytes from an
    engine log.  The extent allocator emits:
      [P3] ts_ms=... evt=extent_recycle slot=.. generation=.. freed=<bytes>
    Line-level regex only (no cross-span patterns)."""
    if not engine_log_path or not os.path.exists(engine_log_path):
        return None
    count = 0
    freed_bytes = 0
    pattern = re.compile(r"evt=extent_recycle\b")
    freed_re = re.compile(r"freed=(\d+)")
    for line in open(engine_log_path, errors="replace"):
        if not pattern.search(line):
            continue
        count += 1
        m = freed_re.search(line)
        if m:
            freed_bytes += int(m.group(1))
    return {"recycle_events": count, "recycle_freed_bytes": freed_bytes}


def recheck_attribution(attribution, engine_events):
    """Per-event attribution recheck (spec §4.4 / reviewer D3).  For each full
    recompute whose provisional reason is state_machine, flip to
    capacity_evicted ONLY when:
      - the session had prior L3-durable evidence (prior_l3=True), AND
      - there EXISTS an engine extent_recycle event with
          ts_recycle < recompute.ts
    (i.e. that session's L3 entry was provably capacity-evicted before the
    recompute).  Any remaining state_machine is the anomaly the oversub
    qualification requires to be ZERO.  Returns (final_attribution,
    flip_counts)."""
    if engine_events is None:
        return (attribution, {"flipped": 0, "remaining_state_machine":
                              sum(1 for a in attribution
                                  if a.get("reason") == "state_machine")})
    recycle_times = [ts for (ts, _) in engine_events["extent_recycle"]
                     if ts is not None]
    flipped = 0
    final = []
    for a in attribution:
        reason = a.get("reason")
        if reason == "state_machine":
            a["prior_l3"] = bool(a.get("prior_l3")) or a.get("prior_l3") is True
            try:
                t_re = float(a.get("ts"))
            except (TypeError, ValueError):
                t_re = None
            hit_ok = (t_re is not None
                      and any(rts is not None and rts < t_re
                              for rts in recycle_times))
            if a.get("prior_l3") and hit_ok:
                a["reason"] = "capacity_evicted"
                a["recheck"] = "flipped_to_capacity_evicted"
                flipped += 1
            else:
                a["reason"] = "state_machine"
                a["recheck"] = "unexplained_by_recycle"
        final.append(a)
    remaining = sum(1 for a in final
                    if a.get("reason") == "state_machine")
    return (final, {"flipped": flipped, "remaining_state_machine": remaining})


def gate_c_engine_join(resume_rows, engine_events, grace_s=1.0):
    """Gate C Host-ready-before-admission rate (spec §3.2).  Denominator = ON
    arm RIDs that have a `ready_stage result=issued` event (RH predicted the
    wake).  Numerator = those whose rid has a restore_ready (or
    restore_state=READY) timestamp <= admission timestamp + grace.  Returns
    (rate, counts).  Assumes engine event rid == driver SSE rid (tester
    verifies on 24052); if not joinable the caller degrades (report
    NOT_FULLY_VERIFIED)."""
    if engine_events is None:
        return (None, {"denom": 0, "ready_before_admission": 0,
                       "note": "no_engine_events"})
    # map rid -> admission ts (latest)
    adm = {}
    for (ts, rid) in engine_events["admission"]:
        if rid is not None:
            adm[rid] = ts
    # ready ts: restore_ready or restore_state=READY
    ready = {}
    for (ts, rid) in engine_events["restore_ready"]:
        if rid is not None:
            ready[rid] = ts
    for (ts, rid, st, _r) in engine_events["restore_state"]:
        if rid is not None and st == "READY":
            ready.setdefault(rid, ts)
    # ready_stage issued set (denominator)
    predicted = set()
    for (_ts, rid, res, _st) in engine_events["ready_stage"]:
        if rid is not None and res == "issued":
            predicted.add(rid)
    # Only resume rows that were RH-predicted
    pred_rows = [r for r in resume_rows
                 if r.get("rid") in predicted]
    denom = len(pred_rows)
    ok = 0
    for r in pred_rows:
        rid = r.get("rid")
        t_adm = adm.get(rid)
        t_rd = ready.get(rid)
        if t_adm is not None and t_rd is not None and t_rd <= t_adm + grace_s:
            ok += 1
    rate = (ok / denom) if denom else None
    return (rate, {"denom": denom, "ready_before_admission": ok,
                   "grace_s": grace_s})


def _counter_delta(snaps, prefix):
    """Delta of a counter across a mid-run time series (last - first)."""
    first = last = None
    for s in snaps:
        m = s.get("metrics") or {}
        v = _g(m, prefix)
        if v is None:
            continue
        if first is None:
            first = v
        last = v
    if first is None or last is None:
        return None
    return last - first


def _series_min_max(snaps, prefix):
    vals = []
    for s in snaps:
        m = s.get("metrics") or {}
        v = _g(m, prefix)
        if v is not None:
            vals.append(v)
    if not vals:
        return (None, None)
    return (min(vals), max(vals))


# ---- per-cell analysis ----

def analyze_cell(run_dir, engine_log=None, fit=False):
    """Returns a dict of computed metrics for one run dir."""
    rows = _load_runs(run_dir)
    resumes = [r for r in rows if r.get("turn_kind") == "resume"]
    attribution = _load_attribution(run_dir)
    mid = _load_mid(run_dir)
    verdict = _load_verdict(run_dir)
    engine_events = parse_engine_events(engine_log) if engine_log else None
    # Gate A: per-event attribution recheck (provisional state_machine ->
    # capacity_evicted when engine extent_recycle ts < recompute ts).
    if engine_events is not None:
        attribution, flip = recheck_attribution(attribution, engine_events)
        out_recheck = flip
    else:
        out_recheck = {
            "flipped": 0,
            "remaining_state_machine": sum(
                1 for a in attribution if a.get("reason") == "state_machine"),
            "note": "no_engine_log",
        }

    out = {
        "run_dir": run_dir,
        "mode": verdict.get("mode"),
        "rh": verdict.get("rh"),
        "sessions": verdict.get("sessions"),
        "build_tier": verdict.get("build_tier"),
        "active": verdict.get("active"),
        "resume_requests": len(resumes),
    }

    # ---- TTFT distribution (resumes only) ----
    ttfts = [_num(r, "ttft_s") for r in resumes]
    ttfts = [t for t in ttfts if t is not None]
    if ttfts:
        out["ttft_p50"] = round(_pct(ttfts, 50), 3)
        out["ttft_p95"] = round(_pct(ttfts, 95), 3)
        out["ttft_p99"] = round(_pct(ttfts, 99), 3)
        out["ttft_max"] = round(max(ttfts), 3)
        out["gt30s_frac"] = round(sum(1 for t in ttfts if t > 30) / len(ttfts), 5)
        out["gt60s_frac"] = round(sum(1 for t in ttfts if t > 60) / len(ttfts), 5)

    # ---- hit distribution (resumes) ----
    dev = sum(_num(r, "cached_device") or 0 for r in resumes)
    host = sum(_num(r, "cached_host") or 0 for r in resumes)
    stor = sum(_num(r, "cached_storage") or 0 for r in resumes)
    prompt = sum(_num(r, "prompt_len") or 0 for r in resumes)
    served = dev + host + stor
    out["device_hit"] = dev
    out["host_hit"] = host
    out["storage_hit"] = stor
    out["served_tokens"] = served
    if served > 0:
        out["l3_residency"] = round((host + stor) / served, 5)  # Host+L3 share
        out["device_frac"] = round(dev / served, 5)
        out["host_frac"] = round(host / served, 5)
        out["storage_frac"] = round(stor / served, 5)
    if prompt > 0:
        out["recompute_frac"] = round(max(0, prompt - served) / prompt, 5)
        out["hit_frac"] = round(served / prompt, 5)

    # Gate B parent distribution
    parents = {}
    for r in resumes:
        p = r.get("hit_parent_mux")
        parents[p] = parents.get(p, 0) + 1
    out["hit_parent_mux"] = parents
    rh_synced = sum(1 for r in resumes if r.get("rh_synced"))
    if resumes:
        out["rh_synced_frac"] = round(rh_synced / len(resumes), 5)

    # ---- Gate A recompute attribution (post-engine-recheck) ----
    by_reason = {}
    for a in attribution:
        by_reason[a.get("reason")] = by_reason.get(a.get("reason"), 0) + 1
    out["recompute_attribution"] = by_reason
    total_hist_recomp = len(attribution)
    out["historical_recompute_events"] = total_hist_recomp
    out["attribution_recheck"] = out_recheck
    if resumes:
        out["avoidable_historical_recompute_frac"] = round(
            total_hist_recomp / len(resumes), 5)

    # ---- Gate C: Host-ready-before-admission rate (engine-join) ----
    gc_rate, gc_counts = gate_c_engine_join(resumes, engine_events)
    out["gate_c_ready_before_admission_rate"] = gc_rate
    out["gate_c_counts"] = gc_counts

    # ---- turns/hour ----
    t0 = verdict.get("ts_start")
    t1 = verdict.get("ts_end")
    if t0 and t1 and t1 > t0:
        out["turns_per_hour"] = round(len(resumes) * 3600.0 / (t1 - t0), 2)

    # ---- recycle-GC evidence ----
    ev = _counter_delta(mid, "sglang:evicted_tokens_total")
    bk = _counter_delta(mid, "sglang:backuped_tokens_total")
    lb = _counter_delta(mid, "sglang:load_back_tokens_total")
    out["evicted_tokens_delta"] = ev
    out["backuped_tokens_delta"] = bk
    out["load_back_tokens_delta"] = lb
    # L3 physical footprint from coarse sampler
    l3phys = []
    for s in mid:
        if s.get("l3_physical") is not None:
            l3phys.append(s["l3_physical"])
    if l3phys:
        out["l3_physical_bytes_min"] = min(l3phys)
        out["l3_physical_bytes_max"] = max(l3phys)
        out["l3_physical_bytes_last"] = l3phys[-1]
    # engine-log extent_recycle (authoritative)
    recycle = parse_extent_recycle(engine_log)
    if recycle is not None:
        out.update(recycle)

    # Host/L3 occupancy gauges
    hused = _series_min_max(mid, "sglang:hicache_host_used_tokens")
    out["host_used_tokens_min"], out["host_used_tokens_max"] = hused

    # storage_hit stability (fit Gate: storage_hit/session resume stable)
    stor_sessions = set()
    for r in resumes:
        if (_num(r, "cached_storage") or 0) > 0:
            stor_sessions.add(r.get("session"))
    out["storage_hit_sessions"] = len(stor_sessions)
    return out


def _fmt(v):
    return "" if v is None else str(v)


def print_cell(c, fit=False):
    print("=" * 78)
    print("CELL mode=%s rh=%s S=%s tier=%s active=%s requests=%d"
          % (c.get("mode"), c.get("rh"), c.get("sessions"),
             c.get("build_tier"), c.get("active"), c.get("resume_requests")))
    print("  TTFT p50/p95/p99/max = %s / %s / %s / %s s"
          % (_fmt(c.get("ttft_p50")), _fmt(c.get("ttft_p95")),
             _fmt(c.get("ttft_p99")), _fmt(c.get("ttft_max"))))
    print("  >30s=%.4f%%  >60s=%.4f%%  turns/hr=%s"
          % ((c.get("gt30s_frac") or 0) * 100, (c.get("gt60s_frac") or 0) * 100,
             _fmt(c.get("turns_per_hour"))))
    print("  hit dev/host/storage = %d/%d/%d tokens  L3_residency=%s  "
          "recompute_frac=%s"
          % (c.get("device_hit"), c.get("host_hit"), c.get("storage_hit"),
             _fmt(c.get("l3_residency")), _fmt(c.get("recompute_frac"))))
    print("  hit_parent_mux = %s" % c.get("hit_parent_mux"))
    print("  historical_recompute_events=%d  attribution=%s"
          % (c.get("historical_recompute_events"), c.get("recompute_attribution")))
    rck = c.get("attribution_recheck") or {}
    print("  attribution_recheck: flipped_to_capacity_evicted=%s "
          "remaining_state_machine=%s note=%s"
          % (rck.get("flipped"), rck.get("remaining_state_machine"),
             rck.get("note", "engine_recheck_done")))
    gc = c.get("gate_c_ready_before_admission_rate")
    gcc = c.get("gate_c_counts") or {}
    print("  GateC ready-before-admission rate=%s (denom=%s ready_ok=%s grace=%s)"
          % (_fmt(round(gc, 4) if gc is not None else None),
             gcc.get("denom"), gcc.get("ready_before_admission"),
             gcc.get("grace_s")))
    print("  recycle: evicted_delta=%s backuped_delta=%s load_back_delta=%s "
          "extent_recycle=%s(%sB)"
          % (_fmt(c.get("evicted_tokens_delta")), _fmt(c.get("backuped_tokens_delta")),
             _fmt(c.get("load_back_tokens_delta")),
             _fmt((c.get("recycle_events") if c.get("recycle_events") is not None
                   else "n/a")),
             _fmt(c.get("recycle_freed_bytes"))))
    print("  host_used_tokens min/max = %s / %s"
          % (_fmt(c.get("host_used_tokens_min")), _fmt(c.get("host_used_tokens_max"))))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", help="single run dir to analyze")
    ap.add_argument("--family", help="dir containing multiple S run dirs "
                                     "(cross-S degradation curve)")
    ap.add_argument("--engine-logs", default="",
                    help="comma list of S=<path> for authoritative extent_recycle "
                         "(e.g. S500=/root/engine-S500.log,S1000=...); applies to "
                         "--family; for --run-dir pass a single path")
    ap.add_argument("--fit", action="store_true",
                    help="treat the run as a Gate A+B fit judgement (S=100)")
    ap.add_argument("--csv", default=None,
                    help="write cross-S degradation curve to this CSV")
    args = ap.parse_args()

    if args.run_dir:
        c = analyze_cell(args.run_dir, args.engine_logs or None, args.fit)
        print_cell(c, args.fit)
        if args.fit:
            _print_fit_judgement(c)
        return 0

    if not args.family:
        print("ERROR: pass --run-dir or --family", file=sys.stderr)
        return 2

    # cross-S curve
    run_dirs = sorted(glob.glob(os.path.join(args.family, "run-*")))
    engine_map = {}
    if args.engine_logs:
        for pair in args.engine_logs.split(","):
            if "=" in pair:
                s, path = pair.split("=", 1)
                engine_map[s.strip()] = path.strip()
    cells = []
    for rd in run_dirs:
        verdict = _load_verdict(rd)
        s = verdict.get("sessions")
        eng = engine_map.get(str(s))
        c = analyze_cell(rd, eng)
        cells.append(c)
    cells.sort(key=lambda c: c.get("sessions") or 0)

    print("=" * 78)
    print("OVERSUSBSCRIPTION STRESS -- DEGRADATION CURVE vs S")
    print("(oversubscription framework: recycle allowed & recorded; NOT a "
          "full-retention claim)")
    hdr = ("S", "L3_residency", "recompute_frac", "ttft_p50", "ttft_p95",
           "ttft_p99", "gt30s%", "gt60s%", "turns/hr", "recycle_events",
           "recycle_B", "state_machine_attr", "cap_evict_attr")
    print("\t".join(hdr))
    for c in cells:
        print("\t".join(str(x) for x in (
            c.get("sessions"), c.get("l3_residency"), c.get("recompute_frac"),
            c.get("ttft_p50"), c.get("ttft_p95"), c.get("ttft_p99"),
            (c.get("gt30s_frac") or 0) * 100, (c.get("gt60s_frac") or 0) * 100,
            c.get("turns_per_hour"), c.get("recycle_events"),
            c.get("recycle_freed_bytes"),
            (c.get("recompute_attribution") or {}).get("state_machine", 0),
            (c.get("recompute_attribution") or {}).get("capacity_evicted", 0),
        )))
    if args.csv:
        with open(args.csv, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=hdr)
            w.writeheader()
            for c in cells:
                w.writerow({
                    "S": c.get("sessions"),
                    "L3_residency": c.get("l3_residency"),
                    "recompute_frac": c.get("recompute_frac"),
                    "ttft_p50": c.get("ttft_p50"),
                    "ttft_p95": c.get("ttft_p95"),
                    "ttft_p99": c.get("ttft_p99"),
                    "gt30s%": (c.get("gt30s_frac") or 0) * 100,
                    "gt60s%": (c.get("gt60s_frac") or 0) * 100,
                    "turns/hr": c.get("turns_per_hour"),
                    "recycle_events": c.get("recycle_events"),
                    "recycle_B": c.get("recycle_freed_bytes"),
                    "state_machine_attr": (c.get("recompute_attribution") or {}).get("state_machine", 0),
                    "cap_evict_attr": (c.get("recompute_attribution") or {}).get("capacity_evicted", 0),
                })
        print("DEGRADATION_CSV_WRITTEN %s" % args.csv)
    return 0


def _print_fit_judgement(c):
    print("=" * 78)
    print("FIT JUDGEMENT (Gate A + B + C) S=%s rh=%s" % (c.get("sessions"), c.get("rh")))
    aa = (c.get("recompute_attribution") or {})
    avoid = aa.get("state_machine", 0) + aa.get("other", 0) + aa.get("never_built", 0)
    print("  avoidable_historical_recompute=%d  (state_machine=%d other=%d "
          "never_built=%d)  -- Gate A wants 0"
          % (avoid, aa.get("state_machine", 0), aa.get("other", 0),
             aa.get("never_built", 0)))
    rck = c.get("attribution_recheck") or {}
    print("  attribution_recheck: flipped=%s remaining_state_machine=%s "
          "(engine-recycle evidence)"
          % (rck.get("flipped"), rck.get("remaining_state_machine")))
    print("  TTFT p50=%s p95=%s p99=%s  -- Gate B fit wants p95<=5s p99<=10s"
          % (_fmt(c.get("ttft_p50")), _fmt(c.get("ttft_p95")),
             _fmt(c.get("ttft_p99"))))
    print("  storage_hit_sessions=%s / requests=%d  (stability)"
          % (_fmt(c.get("storage_hit_sessions")), c.get("resume_requests")))
    print("  recycle: evicted_delta=%s (fit wants none)"
          % _fmt(c.get("evicted_tokens_delta")))
    gc = c.get("gate_c_ready_before_admission_rate")
    gcc = c.get("gate_c_counts") or {}
    print("  GateC ready-before-admission rate=%s (denom=%s ok=%s) -- wants >=0.95"
          % (_fmt(round(gc, 4) if gc is not None else None),
             gcc.get("denom"), gcc.get("ready_before_admission")))
    if gc is None:
        print("  GateC: NOT_FULLY_VERIFIED (no joinable engine events; "
              "needs tester smoke-boot on 24052)")


if __name__ == "__main__":
    sys.exit(main())
