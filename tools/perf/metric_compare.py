#!/usr/bin/env python3
"""A-B per-episode restore metrics from sglang [P2A] engine logs.

Pairing key: (rid, restore_episode_id).  The current M4T workload is one
rid = one restore episode (episode_id 0); the field is kept in the output
structure so future workloads with rid reuse / multiple suspend-restore
cycles do not silently mismatch episodes.

Per episode (user M7 semantics):
  A_ep   = first prefetch_issued ts -> FINAL io_finished ts   (request cycle)
  B_ep   = last prefetch_issued ts before the FINAL finish -> FINAL finish ts
           (service window of the episode's completing attempt)
  A-B_ep = A_ep - B_ep >= 0   (per-sample waste; quantiles are taken on the
           per-sample difference distribution, never p90(A)-p90(B))
  n_issues / n_finishes / final_tokens (the FINAL finish's n_tokens; the
           full-chain >=20k classification uses the final finish, not the
           max tokens among the episode's finishes)
Episodes without any finish (all lookups revoked/recomputed) are listed as
no_finish rows and do not participate in any quantile.

Dual B track:
  B_fin (per-finish service windows, the historical metric_compare
         "definition B") is kept as a verification gate + history baseline:
         it must reproduce the e5 report values (e5 1.158s n=15 / m4t
         1.051s n=11 / m4f 1.320s n=20 / e4 1.236s n=17).
  B_ep  (per-episode) is the primary pairing metric (user M7).  Multi-finish
         episodes (finish -> admission deny -> re-issue -> finish ...) make
         B_fin != B_ep by construction: the intermediate finishes are part
         of the re-issue loop, i.e. part of the A-B waste.

The old per-attempt view (every issued -> its first subsequent finish) is
retained as a diagnostic appendix named "attempt spans".

CLI:
  python3 metric_compare.py [label=path ...] [--csv OUT] [--single LABEL]
                            [--no-attempt]
Default runs (no args): m4f / m4t / m4t-e4 / e5 (paths below; if a path is
missing, re-pull the log from the 3090 first, e.g.
  scp -P 24052 root@175.155.64.171:/root/engine-p2io-m4f.log .
)
"""
import argparse
import collections
import re
import statistics

EVT_RE = re.compile(r"\[P2A\] ts_ms=(\d+) evt=(\w+)(.*)")

DEFAULT_RUNS = [
    ("m4f", "/tmp/p2io-e4/m4f/engine-p2io-m4f.log"),
    ("m4t", "/tmp/p2io-e4/baseline/engine-p2io-m4t.log"),
    ("m4t-e4", "/tmp/p2io-e4/run/engine-p2io-m4t-e4.log"),
    ("e5", "/tmp/p2io-e5/engine-p2io-m4t-e5.log"),
]

FULL_CHAIN_TOKENS = 20000


def parse(path):
    events = []
    with open(path, errors="replace") as f:
        for line in f:
            m = EVT_RE.search(line)
            if not m:
                continue
            ts, evt, rest = m.groups()
            fields = {"ts_ms": int(ts), "evt": evt}
            for kv in re.findall(r"(\w+)=([^\s]+)", rest):
                fields[kv[0]] = kv[1]
            events.append(fields)
    return events


def pct(s, p):
    if not s:
        return None
    idx = min(len(s) - 1, int(round(p / 100.0 * (len(s) - 1))))
    return s[idx]


def stat_line(vals, scale=1000.0):
    if not vals:
        return "n=0"
    s = sorted(vals)
    return (
        f"n={len(s)} p50={pct(s, 50) / scale:.3f}s "
        f"p90={pct(s, 90) / scale:.3f}s p95={pct(s, 95) / scale:.3f}s "
        f"max={s[-1] / scale:.3f}s mean={statistics.mean(s) / scale:.3f}s"
    )


def bucket_line(vals, scale=1000.0):
    if not vals:
        return ""
    s = [v / scale for v in vals]
    return (f"  buckets: <2s:{sum(1 for x in s if x < 2)} "
            f"2-5s:{sum(1 for x in s if 2 <= x < 5)} "
            f"5-15s:{sum(1 for x in s if 5 <= x < 15)} "
            f">=15s:{sum(1 for x in s if x >= 15)}")


def split_episodes(by_rid):
    """Group a rid's issued/finish events into restore episodes.

    Rule: an episode opens at an issued and closes at the rid's LAST
    finish; finishes before the last finish are intermediate (the
    finish -> admission deny -> re-issue loop is ONE episode).  Issued
    events after the last finish would open a new episode (rid reuse /
    future multi-cycle requests); they are listed as no_finish rows.
    """
    episodes = []      # dicts with rid/ep/A_ms/B_ms/AB_ms/n_issues/...
    no_finish = []     # episodes without any finish (ep=0 or a tail ep>=1)
    n_tail_ep = 0      # rids with a second (post-final-finish) episode
    for rid, evs in by_rid.items():
        evs.sort(key=lambda x: x[1]["ts_ms"])
        fins = [e for k, e in evs if k == "finish"]
        issues = [e for k, e in evs if k == "issued"]
        if not fins:
            no_finish.append({"rid": rid, "ep": 0, "n_issues": len(issues)})
            continue
        final_fin = fins[-1]
        ep_issues = [e for e in issues if e["ts_ms"] <= final_fin["ts_ms"]]
        tail_issues = [e for e in issues if e["ts_ms"] > final_fin["ts_ms"]]
        if not ep_issues:
            continue  # defensive: finish without any prior issued
        first_ts = ep_issues[0]["ts_ms"]
        last_iss = max(ep_issues, key=lambda e: e["ts_ms"])
        a_ms = final_fin["ts_ms"] - first_ts
        b_ms = final_fin["ts_ms"] - last_iss["ts_ms"]
        episodes.append({
            "rid": rid,
            "ep": 0,
            "A_ms": a_ms,
            "B_ms": b_ms,
            "AB_ms": a_ms - b_ms,
            "n_issues": len(ep_issues),
            "n_finishes": len(fins),
            "final_tokens": int(final_fin["n_tokens"]),
        })
        if tail_issues:
            # issued events after the rid's LAST finish: a second restore
            # cycle (e.g. leftover-token re-restore after admission deny)
            # that never finishes in this log.  One no_finish row per rid
            # (all tail issues are contiguous after the last finish).
            n_tail_ep += 1
            no_finish.append({
                "rid": rid,
                "ep": 1,
                "n_issues": len(tail_issues),
                "note": "issued-after-last-finish",
            })
    return episodes, no_finish, n_tail_ep


def per_finish_spans(issued, io_fin):
    """B_fin: each io_finished -> last issued of the same rid at/before it."""
    iss_by_rid = collections.defaultdict(list)
    for e in issued:
        iss_by_rid[e["rid"]].append(e)
    spans = []
    for f in io_fin:
        iss = [e for e in iss_by_rid.get(f["rid"], [])
               if e["ts_ms"] <= f["ts_ms"]]
        if iss:
            spans.append((f["ts_ms"] - iss[-1]["ts_ms"], int(f["n_tokens"])))
    return spans


def attempt_spans(issued, io_fin):
    """attempt spans: every issued -> its first subsequent finish."""
    fin_by_rid = collections.defaultdict(list)
    for f in io_fin:
        fin_by_rid[f["rid"]].append(f)
    spans = []
    for e in issued:
        fins = [f for f in fin_by_rid.get(e["rid"], [])
                if f["ts_ms"] >= e["ts_ms"]]
        if fins:
            f0 = min(fins, key=lambda f: f["ts_ms"])
            spans.append((f0["ts_ms"] - e["ts_ms"], int(f0["n_tokens"])))
    return spans


def split_full(vals_tokens, full_tokens=FULL_CHAIN_TOKENS):
    """vals_tokens: list of (ms, tokens); returns (all_ms, full_ms)."""
    all_ms = [v for v, _ in vals_tokens]
    full_ms = [v for v, t in vals_tokens if t >= full_tokens]
    return all_ms, full_ms


def report_run(path, label, args, csv_rows):
    single = args.single is not None and args.single == label
    events = parse(path)
    issued = [e for e in events if e["evt"] == "prefetch_issued"]
    revoke = [e for e in events if e["evt"] == "prefetch_revoke"]
    io_fin = [e for e in events if e["evt"] == "prefetch_io_finished"]
    # restore_success ("issued->satisfied", added in P0 reserve fix): the
    # restored KV is actually served to the request this admission. A
    # satisfied window is a per-request service completion; where the IO
    # channel's prefetch_io_finished is a host-tier finish, restore_success
    # is the request-tier service finish (finishes can be chained to
    # issued events of the same rid).
    satisfied = [e for e in events if e["evt"] == "restore_success"]
    cons = len(issued) == len(revoke) + len(io_fin) + len(satisfied)

    rid_issued = collections.Counter(e["rid"] for e in issued)
    counts = sorted(rid_issued.values())
    cc = collections.Counter(counts)

    by_rid = collections.defaultdict(list)
    for e in issued:
        by_rid[e["rid"]].append(("issued", e))
    for e in io_fin:
        by_rid[e["rid"]].append(("finish", e))
    for e in satisfied:
        by_rid[e["rid"]].append(("finish", e))
    episodes, no_finish, n_tail_ep = split_episodes(by_rid)

    bfin = per_finish_spans(issued, io_fin + satisfied)
    bfin_all, bfin_full = split_full(bfin)
    att = attempt_spans(issued, io_fin + satisfied)
    att_all, att_full = split_full(att)

    full_ep = [ep for ep in episodes if ep["final_tokens"] >= FULL_CHAIN_TOKENS]
    all_ep = episodes

    print(f"===== {label} ({path}) =====")
    print(f"conservation: issued={len(issued)} == revoke={len(revoke)} "
          f"+ io_finished={len(io_fin)} + satisfied={len(satisfied)} "
          f"-> {cons}")
    if counts:
        print(f"lookup/rid: n_rids={len(counts)} p50={pct(counts, 50)} "
              f"p95={pct(counts, 95)} max={counts[-1]} dist={dict(sorted(cc.items()))}")
    print(f"[B_fin per-finish (history gate)] all: {stat_line(bfin_all)}")
    print(f"[B_fin per-finish] full>=20k: {stat_line(bfin_full)}"
          f"{bucket_line(bfin_full)}")
    if satisfied:
        sat_spans = per_finish_spans(issued, satisfied)
        sat_all, sat_full = split_full(sat_spans)
        print(f"[B_sat issued->satisfied] all: {stat_line(sat_all)}")
        print(f"[B_sat issued->satisfied] full>=20k: {stat_line(sat_full)}"
              f"{bucket_line(sat_full)}")
    print(f"[episodes] with_finish={len(all_ep)} (tail_second_episodes="
          f"{n_tail_ep}) no_finish_episodes={len(no_finish)} "
          f"full>=20k={len(full_ep)}")
    if full_ep:
        print(f"[main full>=20k] A_ep: {stat_line([e['A_ms'] for e in full_ep])}")
        print(f"[main full>=20k] B_ep: {stat_line([e['B_ms'] for e in full_ep])}")
        print(f"[main full>=20k] A-B:  {stat_line([e['AB_ms'] for e in full_ep])}")
        print(f"[main full>=20k] A-B buckets:{bucket_line([e['AB_ms'] for e in full_ep])}")
    print(f"[appendix all ep] A_ep: {stat_line([e['A_ms'] for e in all_ep])}")
    print(f"[appendix all ep] B_ep: {stat_line([e['B_ms'] for e in all_ep])}")
    print(f"[appendix all ep] A-B:  {stat_line([e['AB_ms'] for e in all_ep])}")
    print(f"[no_finish episodes] {len(no_finish)}: "
          + ", ".join(f"{e['rid'][:8]}(ep={e['ep']},iss={e['n_issues']})"
                      for e in no_finish[:8])
          + (" ..." if len(no_finish) > 8 else ""))
    if not args.no_attempt:
        print(f"[attempt spans appendix] all: {stat_line(att_all)}")
        print(f"[attempt spans appendix] full>=20k: {stat_line(att_full)}")
    # self-checks
    bad = [e for e in episodes if e["AB_ms"] < 0 or e["B_ms"] > e["A_ms"]]
    print(f"[self-check] A-B<0 or B>A violations: {len(bad)}")
    # per-episode rows (all episodes with finish), sorted by A-B desc;
    # default truncates to 8 rows per run, --single LABEL prints the full
    # per-episode table for that run only.
    rows = sorted(episodes, key=lambda x: -x["AB_ms"])
    limit = None if single else 8
    print("[per-episode rows] (rid, ep, A_s, B_s, A-B_s, n_issues, n_finishes, final_tokens)"
          + ("" if single else "; truncated to 8, use --single LABEL for full"))
    for e in rows[:limit]:
        print(f"  {e['rid']} ep={e['ep']} A={e['A_ms']/1000:.3f} "
              f"B={e['B_ms']/1000:.3f} A-B={e['AB_ms']/1000:.3f} "
              f"n_issues={e['n_issues']} n_finishes={e['n_finishes']} "
              f"final_tokens={e['final_tokens']}")
    if limit is not None and len(rows) > limit:
        print(f"  ... ({len(rows) - limit} more episodes)")
    if csv_rows is not None:
        for e in episodes:
            csv_rows.append({
                "run": label, "rid": e["rid"], "episode": e["ep"],
                "A_s": round(e["A_ms"] / 1000, 3),
                "B_s": round(e["B_ms"] / 1000, 3),
                "A-B_s": round(e["AB_ms"] / 1000, 3),
                "n_issues": e["n_issues"], "n_finishes": e["n_finishes"],
                "final_tokens": e["final_tokens"],
            })
    return {
        "label": label,
        "cons": cons,
        "lookup": (pct(counts, 50), counts[-1]) if counts else (None, None),
        "bfin_full": bfin_full,
        "bfin_all": bfin_all,
        "full_ep": full_ep,
        "all_ep": all_ep,
        "n_no_finish": len(no_finish),
    }


def comp_table(runs):
    print("===== multi-run comparison (full-chain >=20k) =====")
    hdr = (f"{'run':8s} {'n_full':>6s} {'B_fin p50/p90':>16s} "
           f"{'B_ep p50/p90':>16s} {'A_ep p50/p90':>16s} "
           f"{'A-B p50/p90/p95/max':>28s} {'lookup p50/max':>16s} cons")
    print(hdr)
    for r in runs:
        bf = sorted(r["bfin_full"])
        be = sorted(e["B_ms"] for e in r["full_ep"])
        ae = sorted(e["A_ms"] for e in r["full_ep"])
        ab = sorted(e["AB_ms"] for e in r["full_ep"])
        f = lambda s, p: f"{pct(s, p) / 1000:.3f}" if s else "-"
        ab_s = (f"{f(ab, 50)}/{f(ab, 90)}/{f(ab, 95)}/{ab[-1] / 1000:.3f}"
                if ab else "-")
        print(f"{r['label']:8s} {len(bf):6d} "
              f"{f(bf, 50) + '/' + f(bf, 90):>16s} "
              f"{f(be, 50) + '/' + f(be, 90):>16s} "
              f"{f(ae, 50) + '/' + f(ae, 90):>16s} "
              f"{ab_s:>28s} "
              f"{str(r['lookup'][0]) + '/' + str(r['lookup'][1]):>16s} "
              f"{r['cons']}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="*", help="label=path pairs; default four runs")
    ap.add_argument("--csv", metavar="OUT", help="dump per-episode rows to CSV")
    ap.add_argument("--single", metavar="LABEL",
                    help="print per-episode rows only for this run label")
    ap.add_argument("--no-attempt", action="store_true",
                    help="skip the attempt-spans appendix")
    args = ap.parse_args()

    if args.runs:
        runs = []
        for item in args.runs:
            if "=" not in item:
                ap.error(f"expected label=path, got {item!r}")
            label, path = item.split("=", 1)
            runs.append((label, path))
    else:
        runs = list(DEFAULT_RUNS)

    missing = [p for _, p in runs if not os.path.exists(p)]
    if missing:
        print("ERROR: missing log(s):", missing, file=sys.stderr)
        print("re-pull from 3090, e.g.:", file=sys.stderr)
        print("  scp -i ~/.ssh/id_ed25519 -o IdentitiesOnly=yes -P 24052 "
              "root@175.155.64.171:/root/engine-p2io-m4f.log .", file=sys.stderr)
        sys.exit(1)

    csv_rows = []
    results = []
    for label, path in runs:
        res = report_run(path, label, args, csv_rows)
        results.append(res)
        print()
    comp_table(results)

    if args.csv:
        import csv as _csv
        with open(args.csv, "w", newline="") as f:
            w = _csv.DictWriter(f, fieldnames=list(csv_rows[0].keys()))
            w.writeheader()
            w.writerows(csv_rows)
        print(f"per-episode rows dumped to {args.csv} ({len(csv_rows)} rows)")


if __name__ == "__main__":
    import os
    import sys
    main()
