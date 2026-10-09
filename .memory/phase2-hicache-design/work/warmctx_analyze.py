#!/usr/bin/env python3
"""warmctx_analyze.py -- recompute exp-2 warm-turn latency numbers from raw
evidence (runs.csv + verdict.json + engine log).

For each tier evidence dir, reads run-*/runs.csv and prints:
  - cold turn: prompt tokens, wall_s (E2E), ttft_s
  - warm turns: per-row prompt_len, completion_tokens, wall_s (E2E), ttft_s,
    cached_tokens, cached_{device,host,storage}
  - warm summary: median/mean/p50 of wall_s and ttft_s across sessions/repeats
Cross-tier table at the end: warm wall/ttft p50 by tier -> the core judgement
(warm-turn does NOT scale with context length if p50 ~flat).
"""
import argparse
import csv
import json
import os
import statistics


def load_runs(evidence_dir):
    run_dirs = sorted(
        d for d in os.listdir(evidence_dir)
        if d.startswith("run-") and os.path.isdir(os.path.join(evidence_dir, d))
    )
    if not run_dirs:
        raise SystemExit("no run-* dirs under %s" % evidence_dir)
    # most recent run
    rd = os.path.join(evidence_dir, run_dirs[-1])
    runs_path = os.path.join(rd, "runs.csv")
    with open(runs_path) as f:
        rows = list(csv.DictReader(f))
    verdict = {}
    try:
        with open(os.path.join(rd, "verdict.json")) as f:
            verdict = json.load(f)
    except Exception:
        pass
    return rd, rows, verdict


def fmt(v):
    if v is None or v == "":
        return "None"
    return v


def analyze(tiers):
    summary = []
    for tier in tiers:
        rd, rows, verdict = load_runs(tier)
        cold = [r for r in rows if r.get("turn") == "cold"]
        warm = [r for r in rows if r.get("turn") == "warm"]
        print("=" * 80)
        print("TIER %s  run_dir=%s  cold=%d warm=%d"
              % (tier, rd, len(cold), len(warm)))
        print("  verdict: %s" % json.dumps(verdict))
        for r in cold:
            print("  COLD s=%s prompt_len=%s wall=%s ttft=%s "
                  "cached=%s comp=%s fr=%s rc=%s" % (
                      r.get("session"), fmt(r.get("prompt_len")),
                      fmt(r.get("wall_s")), fmt(r.get("ttft_s")),
                      fmt(r.get("cached_tokens")), fmt(r.get("completion_tokens")),
                      fmt(r.get("finish_reason")), fmt(r.get("rc"))))
        for r in warm:
            print("  WARM s=%s r=%s prompt_len=%s comp=%s wall=%s ttft=%s "
                  "cached=%s d=%s h=%s st=%s pin=%s pd=%s ph=%s ps=%s" % (
                      r.get("session"), r.get("turn"),
                      fmt(r.get("prompt_len")), fmt(r.get("completion_tokens")),
                      fmt(r.get("wall_s")), fmt(r.get("ttft_s")),
                      fmt(r.get("cached_tokens")), fmt(r.get("cached_device")),
                      fmt(r.get("cached_host")), fmt(r.get("cached_storage")),
                      fmt(r.get("prefill_input_delta")),
                      fmt(r.get("prefill_devicehit_delta")),
                      fmt(r.get("prefill_hosthit_delta")),
                      fmt(r.get("prefill_storagehit_delta"))))
        def _nums(rows, key):
            vals = []
            for r in rows:
                v = r.get(key)
                if v is not None and v != "":
                    try:
                        vals.append(float(v))
                    except Exception:
                        pass
            return vals
        ww = _nums(warm, "wall_s")
        wt = _nums(warm, "ttft_s")
        def _p50(v):
            return round(statistics.median(v), 3) if v else None
        def _mean(v):
            return round(sum(v) / len(v), 3) if v else None
        ww50, wwmean = _p50(ww), _mean(ww)
        wt50, wtmean = _p50(wt), _mean(wt)
        print("  WARM wall_s: n=%d p50=%s mean=%s min=%s max=%s" % (
            len(ww), ww50, wwmean,
            round(min(ww), 3) if ww else None,
            round(max(ww), 3) if ww else None))
        print("  WARM ttft_s: n=%d p50=%s mean=%s min=%s max=%s" % (
            len(wt), wt50, wtmean,
            round(min(wt), 3) if wt else None,
            round(max(wt), 3) if wt else None))
        summary.append({
            "tier": tier, "run_dir": rd,
            "warm_wall_n": len(ww), "warm_wall_p50": ww50,
            "warm_wall_mean": wwmean,
            "warm_ttft_p50": wt50, "warm_ttft_mean": wtmean,
            "cold_wall": cold[0].get("wall_s") if cold else None,
            "cold_prompt": cold[0].get("prompt_len") if cold else None,
        })
    print("=" * 80)
    print("CROSS-TIER WARM SUMMARY (core judgement)")
    print("%-6s %-8s %-10s %-10s %-10s %-10s" % (
        "tier", "warm_n", "wall_p50", "wall_mean", "ttft_p50", "ttft_mean"))
    for s in summary:
        print("%-6s %-8s %-10s %-10s %-10s %-10s" % (
            s["tier"], s["warm_wall_n"], s["warm_wall_p50"],
            s["warm_wall_mean"], s["warm_ttft_p50"], s["warm_ttft_mean"]))
    return summary


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("evidence_dirs", nargs="+",
                    help="evidence dirs, one per tier (e.g. "
                         "/root/evidence-warmctx-32k ...)")
    args = ap.parse_args()
    analyze(args.evidence_dirs)
