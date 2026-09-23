#!/usr/bin/env python3
"""Offline performance scorecard collector (P1).

Merges:

  * client-side load-run timing  -> ``efficiency-<run-tag>.json`` produced by
    ``tools/perf/efficiency_sweep.py`` (F39 metric definitions), and
  * server-side per-request telemetry -> the JSONL written by
    ``FileRequestMetricsExporter`` (``--export-metrics-to-file``), plus an
    optional Prometheus scrape (``/metrics``) snapshot.

...into the owner-prescribed fixed base table (5 sections:
Workload / Latency / Compute / Cache / Runtime).

Owner table source (read-only): ``3090-dev/docs/PERFORMANCE-SCORECARD.md`` §6.
Metric definitions are taken verbatim from that document and from
``PERFORMANCE-BASELINE-SPEC-v2``; **no new metric is invented**.

Honesty rules (binding):
  * A counter that is not present in the provided inputs is reported as
    ``UNAVAILABLE`` with ``source = "UNAVAILABLE"``. It is never inferred from
    occupancy or total token throughput
    (``PERFORMANCE-BASELINE-SPEC-v2.json:24``).
  * ITL / TPOT are no longer ``UNAVAILABLE`` by construction:
    - ITL is taken from the existing Prometheus histogram
      ``sglang:inter_token_latency_seconds`` (window-level, NOT per-request;
      ``metrics_collector.py:1926``), and
    - TPOT is derived per-request from the JSONL as
      ``e2e_latency / completion_tokens`` -- an **upper-bound approximation**
      of the owner definition ``(E2E - TTFT) / output_tokens`` because the JSONL
      carries no independent TTFT field.
    Each stays ``UNAVAILABLE`` (via ``leaf()``) when its input is absent.
  * ``aggregate decode TPS`` keeps the F39 relative definition
    ``total_out_tokens / max(per-request dur_s)`` and is labelled as such; it is
    **not** silently replaced by the spec's ``output_tokens / wall_time``.

This tool is strictly read-only and offline by default. It does not start a
server, bind a port, use a GPU, drive load, or contact ``:30000`` unless the
caller explicitly passes an ``http(s)://`` ``--metrics-url``. For offline
replay of a Prometheus scrape, pass ``--metrics-url file:///path/to/metrics.txt``.
"""
from __future__ import annotations

import argparse
import glob
import json
import math
import os
import sys
import urllib.request
from datetime import datetime, timezone
from urllib.parse import urlsplit

UNAVAILABLE = "UNAVAILABLE"

DEFAULT_LEVELS = "1,2,4,8"
DEFAULT_COUNT_PER_LEVEL = 16
DEFAULT_OUT_TOKENS = 64
DEFAULT_MODE = "both"

# The owner fixed base table, verbatim from
# 3090-dev/docs/PERFORMANCE-SCORECARD.md §6 ("固定输出：精简版基础表").
BASE_TABLE = {
    "Workload": [
        "prompt tokens p50/p95",
        "output tokens p50/p95",
        "concurrency",
    ],
    "Latency": [
        "TTFT p50/p95",
        "E2E p50/p95",
        "queue_time p50/p95",
        "ITL/TPOT",
    ],
    "Compute": [
        "prefill TPS",
        "per-request decode TPS",
        "aggregate decode TPS",
    ],
    "Cache": [
        "cached tokens",
        "newly-prefilled tokens",
        "prefix hit rate",
        "L1/L2/L3 restore",
        "eviction / avoidable recompute",
    ],
    "Runtime": [
        "actual running concurrency",
        "decode batch size",
        "KV free/used",
        "Mamba slots free/used",
        "retractions",
        "CUDA Graph hit/fallback",
    ],
}

# Three output-discipline rules that must accompany any reading of the table
# (3090-dev/docs/PERFORMANCE-SCORECARD.md §7).
DISCIPLINE_NOTES = [
    "TTFT must be read together with cache state (cached / newly-prefilled).",
    "prefill TPS uses newly-prefilled tokens, never full prompt tokens.",
    "concurrency requires aggregate TPS + queue_time + actual concurrency together.",
]


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def pct(xs, p):
    """Linear-interpolated percentile, same method as efficiency_sweep.py."""
    if not xs:
        return None
    xs = sorted(xs)
    k = (len(xs) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def fmt(v, nd=3):
    if v is None:
        return UNAVAILABLE
    if isinstance(v, str):
        return v
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        if not math.isfinite(v):
            return UNAVAILABLE
        return str(round(v, nd))
    return str(v)


def _is_empty(value):
    """True when a cell holds no usable measurement (None, or all-None list/dict)."""
    if value is None:
        return True
    if isinstance(value, (list, tuple)):
        return all(v is None for v in value)
    if isinstance(value, dict):
        return all(v is None for v in value.values())
    return False


def leaf(definition, value, source, scope="window"):
    """One metric cell: definition + value + source (or UNAVAILABLE)."""
    if _is_empty(value):
        return {
            "definition": definition,
            "value": UNAVAILABLE,
            "source": "UNAVAILABLE",
            "scope": scope,
        }
    return {
        "definition": definition,
        "value": value,
        "source": source,
        "scope": scope,
    }


def num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def load_json(path):
    with open(path) as fh:
        return json.load(fh)


def load_jsonl(path):
    rows = []
    with open(path) as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                print(f"[warn] {path}:{lineno}: not JSON, skipped", file=sys.stderr)
    return rows


def load_server_rows(metrics_dir):
    """Read every sglang-request-metrics-*.log under metrics_dir (recursive)."""
    if not metrics_dir:
        return [], []
    patterns = [
        os.path.join(metrics_dir, "**", "*.log"),
        os.path.join(metrics_dir, "**", "*.jsonl"),
    ]
    files = sorted({p for pat in patterns for p in glob.glob(pat, recursive=True)})
    rows = []
    for path in files:
        rows.extend(load_jsonl(path))
    return rows, files


def fetch_text(url):
    """Read a metrics source. file:// (or bare path) is local; http(s) is remote.

    Remote fetch is opt-in via an explicit --metrics-url and is never used by
    the offline self-test.
    """
    parts = urlsplit(url)
    if parts.scheme in ("", "file"):
        path = parts.path if parts.scheme == "file" else url
        with open(path) as fh:
            return fh.read()
    if parts.scheme in ("http", "https"):
        with urllib.request.urlopen(url, timeout=30) as resp:
            return resp.read().decode("utf-8", errors="replace")
    raise ValueError(f"unsupported metrics-url scheme: {parts.scheme!r}")


def parse_prometheus(text):
    """Parse Prometheus exposition text into {metric_name: summed_value}.

    Series labels are summed (gauge/counter) to yield one scalar per metric.
    Only the first sample of each name is used for the raw snapshot map.
    """
    sums = {}
    samples = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if " " not in line:
            continue
        head, raw = line.rsplit(" ", 1)
        try:
            val = float(raw)
        except ValueError:
            continue
        name = head.split("{", 1)[0]
        sums[name] = sums.get(name, 0.0) + val
        samples.setdefault(name, val)
    return sums, samples


def parse_prometheus_histograms(text):
    """Parse Prometheus histogram families from exposition text.

    Returns ``{base_name: {"buckets": {le_str: cumulative_count},
    "sum": float|None, "count": float|None}}``. Cumulative bucket counts are
    summed across identical ``le`` label sets (a single-process scrape has one
    series per ``le``). The ``+Inf`` bucket is retained as the total.

    This reads only the already-captured exposition text; it adds no new
    observation mechanism (the ITL histogram was already emitted by
    ``metrics_collector.py:1926``).
    """
    hist = {}

    def _slot(base):
        return hist.setdefault(base, {"buckets": {}, "sum": None, "count": None})

    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if " " not in line:
            continue
        head, raw = line.rsplit(" ", 1)
        try:
            val = float(raw)
        except ValueError:
            continue
        name = head.split("{", 1)[0]
        if name.endswith("_bucket"):
            labels = head.split("{", 1)[1].rsplit("}", 1)[0] if "{" in head else ""
            le = None
            for part in labels.split(","):
                k, _, v = part.partition("=")
                if k.strip() == "le":
                    le = v.strip().strip('"')
            if le is None:
                continue
            slot = _slot(name[: -len("_bucket")])
            slot["buckets"][le] = slot["buckets"].get(le, 0.0) + val
        elif name.endswith("_sum"):
            slot = _slot(name[: -len("_sum")])
            slot["sum"] = (slot["sum"] or 0.0) + val
        elif name.endswith("_count"):
            slot = _slot(name[: -len("_count")])
            slot["count"] = (slot["count"] or 0.0) + val
    return hist


def histogram_quantile(buckets, q):
    """Prometheus-style linear-interpolation quantile over cumulative buckets.

    ``buckets`` is ``{le_str: cumulative_count}`` (``+Inf`` = total). Mirrors
    ``histogram_quantile``: the lower bound of the first bucket is treated as 0.
    Returns ``None`` when there are no finite buckets or the total is zero.
    """
    if not buckets:
        return None
    finite = []
    total = None
    for le, cnt in buckets.items():
        if le == "+Inf":
            total = cnt
            continue
        try:
            finite.append((float(le), cnt))
        except ValueError:
            continue
    if total is None:
        total = max((c for _, c in finite), default=0.0)
    if not finite or not num(total) or total <= 0:
        return None
    finite.sort()
    rank = q * total
    prev_le, prev_cnt = 0.0, 0.0
    for le, cnt in finite:
        if cnt >= rank:
            if cnt == prev_cnt:
                return le
            return prev_le + (le - prev_le) * (rank - prev_cnt) / (cnt - prev_cnt)
        prev_le, prev_cnt = le, cnt
    return finite[-1][0]


def itl_from_histograms(hists):
    """Window-level ITL summary from the existing Prometheus histogram.

    Uses ``sglang:inter_token_latency_seconds``; returns ``mean`` from
    ``_sum/_count`` plus ``p50``/``p95`` estimated from ``_bucket``. Returns
    ``None`` when the metric is absent or empty (fail-honest -> UNAVAILABLE).
    """
    h = hists.get("sglang:inter_token_latency_seconds")
    if not h:
        return None
    out = {}
    if num(h.get("sum")) and num(h.get("count")) and h["count"] > 0:
        out["mean"] = h["sum"] / h["count"]
    p50 = histogram_quantile(h.get("buckets"), 0.5)
    p95 = histogram_quantile(h.get("buckets"), 0.95)
    if p50 is not None:
        out["p50"] = p50
    if p95 is not None:
        out["p95"] = p95
    return out or None


# --------------------------------------------------------------------------- #
# server-side aggregation
# --------------------------------------------------------------------------- #
def _prefill_time(o):
    fe = o.get("forward_entry_time")
    pf = o.get("prefill_finished_time")
    if num(fe) and num(pf) and pf >= fe and pf > 0:
        return pf - fe
    return None


def _newly_prefilled(o):
    ht = o.get("hicache_telemetry") or {}
    npf = ht.get("newly_prefilled_tokens")
    if num(npf):
        return npf
    p, c = o.get("prompt_tokens"), o.get("cached_tokens")
    if num(p) and num(c):
        return max(0, p - c)
    return None


def aggregate_server(rows):
    """Window-level server aggregates over all parsed per-request records."""
    prompt = [o["prompt_tokens"] for o in rows if num(o.get("prompt_tokens"))]
    out = [o["completion_tokens"] for o in rows if num(o.get("completion_tokens"))]
    queue = [o["queue_time"] for o in rows if num(o.get("queue_time"))]
    e2e = [o["e2e_latency"] for o in rows if num(o.get("e2e_latency"))]
    pre = [_prefill_time(o) for o in rows]
    pre = [x for x in pre if num(x) and x > 0]
    npf = [_newly_prefilled(o) for o in rows]
    npf = [x for x in npf if num(x)]
    cached = [o["cached_tokens"] for o in rows if num(o.get("cached_tokens"))]

    prefill_tps_req = []
    for o in rows:
        t = _prefill_time(o)
        n = _newly_prefilled(o)
        if num(t) and t > 0 and num(n):
            prefill_tps_req.append(n / t)
    prefill_tps_window = (sum(npf) / sum(pre)) if pre and npf and sum(pre) > 0 else None

    def hit_rate():
        if sum(prompt) > 0 and cached:
            return sum(cached) / sum(prompt)
        return None

    l1 = [((o.get("hicache_telemetry") or {}).get("l1_tokens")) for o in rows]
    l2 = [((o.get("hicache_telemetry") or {}).get("l2_tokens")) for o in rows]
    l3 = [((o.get("hicache_telemetry") or {}).get("l3_tokens")) for o in rows]
    avoid = [
        ((o.get("hicache_telemetry") or {}).get("avoidable_recompute_tokens"))
        for o in rows
    ]
    avoid = [x for x in avoid if num(x)]

    retr = [o["num_retractions"] for o in rows if num(o.get("num_retractions"))]
    dthr = [o["decode_throughput"] for o in rows if num(o.get("decode_throughput"))]

    # Per-request TPOT approximation: e2e_latency / completion_tokens.
    # Upper-bound approximation of the owner definition (E2E - TTFT)/N because
    # the JSONL has no independent TTFT field (PERF-TELEMETRY-P2-DESIGN D2.3).
    tpot_req = []
    for o in rows:
        e2e_s, ct = o.get("e2e_latency"), o.get("completion_tokens")
        if num(e2e_s) and num(ct) and ct > 0:
            tpot_req.append(e2e_s / ct)

    return {
        "n_requests": len(rows),
        "tpot_per_request": tpot_req,
        "prompt_tokens": prompt,
        "output_tokens": out,
        "queue_time": queue,
        "e2e_latency": e2e,
        "prefill_time": pre,
        "newly_prefilled": npf,
        "cached_tokens": cached,
        "prefix_hit_rate": hit_rate(),
        "prefill_tps_per_request": prefill_tps_req,
        "prefill_tps_window": prefill_tps_window,
        "l1_tokens": [x for x in l1 if num(x)],
        "l2_tokens": [x for x in l2 if num(x)],
        "l3_tokens": [x for x in l3 if num(x)],
        "avoidable_recompute_tokens": avoid,
        "num_retractions": retr,
        "decode_throughput_server": dthr,
    }


# --------------------------------------------------------------------------- #
# client-side level summarisation
# --------------------------------------------------------------------------- #
CLIENT_LEVEL_FIELDS = [
    "label", "n_ok", "n_err", "ttft_p50", "ttft_p90", "ttft_p95",
    "dur_p50", "dur_p90", "dur_p95", "decode_tps_p50", "decode_tps_p90",
    "aggregate_tps", "total_out_tokens", "cached_tokens_nonzero",
    "cached_tokens_max", "cached_tokens_mean", "concurrency", "case", "wall_s",
]


def load_efficiency(path):
    if not path:
        return None
    if not os.path.exists(path):
        print(f"[warn] efficiency json not found: {path} (client fields UNAVAILABLE)",
              file=sys.stderr)
        return None
    data = load_json(path)
    levels = []
    for lvl in data.get("levels", []):
        levels.append({k: lvl.get(k) for k in CLIENT_LEVEL_FIELDS})
    return {"config": data.get("config", {}), "levels": levels}


# --------------------------------------------------------------------------- #
# metric cell construction
# --------------------------------------------------------------------------- #
def build_level_sections(level, server, prom, hists=None):
    """Return the five owner sections for one client level.

    Client (level-scoped) values come from the matching efficiency JSON level.
    Server / Prometheus values are window-scoped and are repeated per level
    (marked scope=window) because per-request JSONL has no concurrency label.
    """
    hists = hists or {}
    sec = {"Workload": {}, "Latency": {}, "Compute": {}, "Cache": {}, "Runtime": {}}

    def srv_p50(vals, nd=3):
        v = pct(vals, 0.5)
        return (round(v, nd) if v is not None else None), "server"

    # --- Workload -------------------------------------------------------- #
    p50, src = srv_p50(server["prompt_tokens"])
    p95 = pct(server["prompt_tokens"], 0.95)
    sec["Workload"]["prompt tokens p50/p95"] = leaf(
        "per-request prompt_tokens p50/p95 (server JSONL)",
        [p50, round(p95, 3)] if p95 is not None else None, src)
    p50, src = srv_p50(server["output_tokens"])
    p95 = pct(server["output_tokens"], 0.95)
    sec["Workload"]["output tokens p50/p95"] = leaf(
        "per-request completion_tokens p50/p95 (server JSONL)",
        [p50, round(p95, 3)] if p95 is not None else None, src)
    sec["Workload"]["concurrency"] = leaf(
        "nominal concurrency for this level (client efficiency JSON)",
        level.get("concurrency"), "client", scope="level")

    # --- Latency --------------------------------------------------------- #
    sec["Latency"]["TTFT p50/p95"] = leaf(
        "first streamed content delta - send time, client-side (efficiency_sweep.py:104-106)",
        [level.get("ttft_p50"), level.get("ttft_p95")], "client", scope="level")
    sec["Latency"]["E2E p50/p95"] = leaf(
        "request send -> stream end, client-side (dur_s p50/p95)",
        [level.get("dur_p50"), level.get("dur_p95")], "client", scope="level")
    p50, src = srv_p50(server["queue_time"], 4)
    p95 = pct(server["queue_time"], 0.95)
    sec["Latency"]["queue_time p50/p95"] = leaf(
        "per-request queue_time p50/p95 (server JSONL; req_time_stats.get_queueing_time)",
        [p50, round(p95, 4)] if p95 is not None else None, src)
    # ITL: window-level Prometheus histogram (NOT per-request).
    # TPOT: per-request JSONL approximation e2e_latency/completion_tokens
    # (upper bound of the owner (E2E-TTFT)/N definition; JSONL has no TTFT).
    itl = itl_from_histograms(hists)
    tpot_p50 = pct(server["tpot_per_request"], 0.5)
    tpot_p95 = pct(server["tpot_per_request"], 0.95)
    itl_cell = {
        "mean": round(itl["mean"], 6) if itl and "mean" in itl else None,
        "p50": round(itl["p50"], 6) if itl and "p50" in itl else None,
        "p95": round(itl["p95"], 6) if itl and "p95" in itl else None,
    }
    tpot_cell = {
        "p50": round(tpot_p50, 6) if tpot_p50 is not None else None,
        "p95": round(tpot_p95, 6) if tpot_p95 is not None else None,
    }
    itl_ok = itl is not None
    tpot_ok = tpot_p50 is not None
    if itl_ok or tpot_ok:
        source = "prometheus+server" if (itl_ok and tpot_ok) else (
            "prometheus" if itl_ok else "server")
        itl_tpot_value = {
            "ITL_seconds": dict(
                itl_cell if itl_ok else {},
                source="prometheus" if itl_ok else "UNAVAILABLE",
                scope="window",
            ),
            "TPOT_seconds": dict(
                tpot_cell if tpot_ok else {},
                source="server" if tpot_ok else "UNAVAILABLE",
                scope="per-request",
                definition="e2e_latency / completion_tokens "
                           "(upper-bound approximation of (E2E-TTFT)/N; no TTFT in JSONL)",
            ),
        }
        itl_tpot_def = (
            "ITL = sglang:inter_token_latency_seconds (Prometheus histogram, "
            "window-level mean from _sum/_count + p50/p95 from _bucket; NOT "
            "per-request). TPOT = e2e_latency/completion_tokens per-request "
            "p50/p95 from server JSONL -- an UPPER-BOUND approximation of the "
            "owner (E2E-TTFT)/output_tokens because JSONL has no independent "
            "TTFT field.")
    else:
        itl_tpot_def = (
            "requires sglang:inter_token_latency_seconds (Prometheus) and/or "
            "JSONL e2e_latency+completion_tokens; neither present")
        itl_tpot_value = None
        source = "UNAVAILABLE"
    cell_scope = "window+per-request" if (itl_ok and tpot_ok) else (
        "window" if itl_ok else ("per-request" if tpot_ok else "n/a"))
    sec["Latency"]["ITL/TPOT"] = leaf(itl_tpot_def, itl_tpot_value, source,
                                     scope=cell_scope)

    # --- Compute --------------------------------------------------------- #
    pre_tps = server["prefill_tps_window"]
    if pre_tps is None and server["prefill_tps_per_request"]:
        pre_tps = pct(server["prefill_tps_per_request"], 0.5)
    sec["Compute"]["prefill TPS"] = leaf(
        "sum(newly_prefilled_tokens) / sum(prefill_finished_time - forward_entry_time), "
        "server JSONL; p50 fallback when a window sum is not formable",
        round(pre_tps, 3) if num(pre_tps) else None, "server")
    sec["Compute"]["per-request decode TPS"] = leaf(
        "completion_tokens / (dur_s - ttft_s), p50 client-side (efficiency_sweep.py:212-213)",
        level.get("decode_tps_p50"), "client", scope="level")
    sec["Compute"]["aggregate decode TPS"] = leaf(
        "total_out_tokens / max(per-request dur_s) [F39 relative definition, "
        "NOT spec output_tokens/wall_time] (efficiency_sweep.py:227)",
        level.get("aggregate_tps"), "client", scope="level")

    # --- Cache ----------------------------------------------------------- #
    mean_c = level.get("cached_tokens_mean")
    max_c = level.get("cached_tokens_max")
    sec["Cache"]["cached tokens"] = leaf(
        "client mean/max cached_tokens for this level (efficiency JSON; "
        "server JSONL cached_tokens p50 also available in window block)",
        [mean_c, max_c] if mean_c is not None or max_c is not None else None,
        "client", scope="level")
    p50, src = srv_p50(server["newly_prefilled"])
    p95 = pct(server["newly_prefilled"], 0.95)
    sec["Cache"]["newly-prefilled tokens"] = leaf(
        "prompt_tokens - cached_tokens (telemetry newly_prefilled_tokens when present), "
        "p50/p95 server JSONL",
        [p50, round(p95, 3)] if p95 is not None else None, src)
    hr = server["prefix_hit_rate"]
    sec["Cache"]["prefix hit rate"] = leaf(
        "sum(cached_tokens) / sum(prompt_tokens) over server JSONL window",
        round(hr, 4) if num(hr) else None, "server")
    tiers = None
    if server["l1_tokens"] or server["l2_tokens"] or server["l3_tokens"]:
        tiers = {
            "L1_p50": round(pct(server["l1_tokens"], 0.5), 3) if server["l1_tokens"] else None,
            "L2_p50": round(pct(server["l2_tokens"], 0.5), 3) if server["l2_tokens"] else None,
            "L3_p50": round(pct(server["l3_tokens"], 0.5), 3) if server["l3_tokens"] else None,
        }
    sec["Cache"]["L1/L2/L3 restore"] = leaf(
        "telemetry l1_tokens / l2_tokens / l3_tokens p50 (hicache_telemetry)",
        tiers, "server")
    ev = prom.get("sglang:evicted_tokens_total")
    avoid = server["avoidable_recompute_tokens"]
    ev_avoid = {
        "evicted_tokens_total": ev if ev is not None else None,
        "avoidable_recompute_tokens_p50": (
            round(pct(avoid, 0.5), 3) if avoid else None),
    }
    if ev_avoid["evicted_tokens_total"] is None and not avoid:
        ev_avoid = None
    sec["Cache"]["eviction / avoidable recompute"] = leaf(
        "evicted_tokens_total from Prometheus; avoidable_recompute_tokens p50 from "
        "telemetry (null when durable-prefix authority unproven)",
        ev_avoid, "prometheus" if ev is not None else "server")

    # --- Runtime --------------------------------------------------------- #
    run = prom.get("sglang:num_running_reqs")
    sec["Runtime"]["actual running concurrency"] = leaf(
        "sglang:num_running_reqs gauge from Prometheus scrape",
        round(run, 3) if num(run) else None, "prometheus")
    dbs = prom.get("sglang:decode_batch_size")
    sec["Runtime"]["decode batch size"] = leaf(
        "sglang:decode_batch_size gauge from Prometheus scrape",
        round(dbs, 3) if num(dbs) else None,
        "prometheus" if num(dbs) else "UNAVAILABLE")
    kv_av, kv_used = prom.get("sglang:kv_available_tokens"), prom.get("sglang:kv_used_tokens")
    kv = {"free": kv_av, "used": kv_used} if kv_av is not None or kv_used is not None else None
    sec["Runtime"]["KV free/used"] = leaf(
        "sglang:kv_available_tokens / sglang:kv_used_tokens (Prometheus)",
        kv, "prometheus")
    m_av, m_used = prom.get("sglang:mamba_available_tokens"), prom.get("sglang:mamba_used_tokens")
    mamba = {"free": m_av, "used": m_used} if m_av is not None or m_used is not None else None
    sec["Runtime"]["Mamba slots free/used"] = leaf(
        "sglang:mamba_available_tokens / sglang:mamba_used_tokens (Prometheus)",
        mamba, "prometheus")
    if server["num_retractions"]:
        sec["Runtime"]["retractions"] = leaf(
            "sum/per-request max num_retractions from server JSONL",
            {"sum": int(sum(server["num_retractions"])),
             "max": int(max(server["num_retractions"]))}, "server")
    else:
        r = prom.get("sglang:num_retracted_reqs")
        sec["Runtime"]["retractions"] = leaf(
            "server JSONL num_retractions (empty) / sglang:num_retracted_reqs",
            round(r, 3) if num(r) else None, "prometheus")
    cg = prom.get("sglang:is_cuda_graph")
    cgp = prom.get("sglang:cuda_graph_passes_total")
    cg_val = None
    if num(cg) or num(cgp):
        cg_val = {"is_cuda_graph": cg, "cuda_graph_passes_total": cgp}
    sec["Runtime"]["CUDA Graph hit/fallback"] = leaf(
        "sglang:is_cuda_graph gauge + sglang:cuda_graph_passes_total counter (Prometheus)",
        cg_val, "prometheus")
    return sec


# --------------------------------------------------------------------------- #
# requirement vs. availability coverage
# --------------------------------------------------------------------------- #
def build_coverage(has_client, has_server, has_prom, itl_ok=False, tpot_ok=False):
    """Diff table: each owner §6 metric -> the channel that can satisfy it.

    ``source_ref`` is the repo file:line that defines/produces the field, or
    ``未找到`` when no on-disk producer exists.
    """
    def row(section, metric, channel, available, source_ref):
        return {
            "section": section,
            "metric": metric,
            "required_channel": channel,
            "source_ref": source_ref,
            "available": bool(available),
            "status": "AVAILABLE" if available else UNAVAILABLE,
        }

    return [
        row("Workload", "prompt tokens p50/p95", "server JSONL prompt_tokens", has_server,
            "request_metrics_exporter.py:54-62 (meta_info pass-through)"),
        row("Workload", "output tokens p50/p95", "server JSONL completion_tokens", has_server,
            "request_metrics_exporter.py:54-62"),
        row("Workload", "concurrency", "client efficiency JSON", has_client,
            "efficiency_sweep.py:346-347"),
        row("Latency", "TTFT p50/p95", "client efficiency JSON", has_client,
            "efficiency_sweep.py:104-106 (capture), :219-221 (summary)"),
        row("Latency", "E2E p50/p95", "client efficiency JSON (dur_*)", has_client,
            "efficiency_sweep.py:139, :222-224"),
        row("Latency", "queue_time p50/p95", "server JSONL queue_time", has_server,
            "req_time_stats.py:1180-1186 (get_queueing_time)"),
        # ITL: Prometheus window histogram (not per-request). TPOT: derived
        # per-request from JSONL e2e_latency/completion_tokens (upper-bound).
        # Status depends on the actual inputs, not on the channel name alone.
        row("Latency", "ITL/TPOT",
            "Prometheus sglang:inter_token_latency_seconds (window) + "
            "JSONL-derived e2e_latency/completion_tokens (per-request, upper-bound)",
            itl_ok or tpot_ok,
            "metrics_collector.py:1926-1932 (histogram), :2040-2048 (observe); "
            "server JSONL e2e_latency/completion_tokens; "
            "PERF-TELEMETRY-P2-DESIGN D2.2/D2.3"),
        row("Compute", "prefill TPS", "server JSONL newly_prefilled + prefill window", has_server,
            "request_metrics_exporter.py telemetry newly_prefilled_tokens; "
            "req_time_stats.py:1168-1187 prefill_finished/forward_entry"),
        row("Compute", "per-request decode TPS", "client efficiency JSON", has_client,
            "efficiency_sweep.py:212-213 (capture), :225 (summary)"),
        row("Compute", "aggregate decode TPS", "client efficiency JSON (F39 relative)", has_client,
            "efficiency_sweep.py:227"),
        row("Cache", "cached tokens", "client efficiency JSON / server JSONL", has_client or has_server,
            "efficiency_sweep.py:123 / usage_processor.py:43-49"),
        row("Cache", "newly-prefilled tokens", "server JSONL / telemetry", has_server,
            "hicache_telemetry.newly_prefilled_tokens (request_metrics_exporter.py)"),
        row("Cache", "prefix hit rate", "server JSONL cached/prompt", has_server,
            "derived from usage_processor.py:43-49 fields"),
        row("Cache", "L1/L2/L3 restore", "telemetry l1/l2/l3_tokens", has_server,
            "hicache_telemetry l1/l2/l3_tokens (schedule_batch.py:220-232)"),
        row("Cache", "eviction / avoidable recompute",
            "Prometheus evicted_tokens_total + telemetry avoidable_recompute",
            has_prom or has_server,
            "metrics_collector.py:2306 evicted_tokens_total; "
            "hicache_telemetry.avoidable_recompute_tokens"),
        row("Runtime", "actual running concurrency", "Prometheus num_running_reqs", has_prom,
            "metrics_collector.py:299"),
        row("Runtime", "decode batch size",
            "Prometheus sglang:decode_batch_size gauge",
            has_prom,
            "metrics_collector.py:335-340"),
        row("Runtime", "KV free/used", "Prometheus kv_available/used_tokens", has_prom,
            "metrics_collector.py:373-385"),
        row("Runtime", "Mamba slots free/used", "Prometheus mamba_available/used_tokens", has_prom,
            "metrics_collector.py:409-421"),
        row("Runtime", "retractions", "server JSONL num_retractions / Prometheus",
            has_server or has_prom, "metrics_collector.py:487; JSONL num_retractions"),
        row("Runtime", "CUDA Graph hit/fallback", "Prometheus is_cuda_graph / passes_total", has_prom,
            "metrics_collector.py:622-629"),
    ]


# --------------------------------------------------------------------------- #
# rendering
# --------------------------------------------------------------------------- #
def render_section(name, metrics):
    lines = [f"{name}:"]
    width = max(len(k) for k in metrics) if metrics else 0
    for key in BASE_TABLE[name]:
        cell = metrics.get(key)
        if cell is None:
            lines.append(f"  {key:<{width}} : {UNAVAILABLE}")
            continue
        lines.append(f"  {key:<{width}} : {fmt(cell['value'])}  [{cell['source']}]")
    return "\n".join(lines)


def render_table(title, sections):
    parts = [f"===== SCORECARD: {title} ====="]
    for name in BASE_TABLE:
        parts.append(render_section(name, sections[name]))
    return "\n".join(parts)


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def parse_args(argv=None):
    ap = argparse.ArgumentParser(
        description="Offline perf scorecard collector (owner fixed base table).")
    ap.add_argument("--run-tag", required=True, help="run tag; default efficiency json is efficiency-<tag>.json")
    ap.add_argument("--url", default=None, help="chat completions endpoint (recorded for provenance only)")
    ap.add_argument("--model", default=None, help="model identifier (recorded for provenance only)")
    ap.add_argument("--efficiency-json", default=None,
                    help="client efficiency JSON (default efficiency-<run-tag>.json)")
    ap.add_argument("--metrics-dir", default=None,
                    help="directory containing server per-request JSONL (*.log)")
    ap.add_argument("--metrics-url", default=None,
                    help="Prometheus scrape URL; file:// replays already captured text "
                         "offline, http(s):// contacts the live server (opt-in)")
    ap.add_argument("--levels", default=DEFAULT_LEVELS, help="recorded concurrency levels")
    ap.add_argument("--count-per-level", type=int, default=DEFAULT_COUNT_PER_LEVEL,
                    help="recorded requests per level")
    ap.add_argument("--out-tokens", type=int, default=DEFAULT_OUT_TOKENS,
                    help="recorded max_tokens per request")
    ap.add_argument("--mode", default=DEFAULT_MODE, help="recorded case mode")
    ap.add_argument("--out", default=None, help="write structured scorecard JSON to this path")
    return ap.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)

    efficiency_path = args.efficiency_json or f"efficiency-{args.run_tag}.json"
    eff = load_efficiency(efficiency_path)
    server_rows, server_files = load_server_rows(args.metrics_dir)
    server = aggregate_server(server_rows) if server_rows else aggregate_server([])

    prom_sums, prom_raw = {}, {}
    prom_hists, prom_error = {}, None
    if args.metrics_url:
        try:
            prom_text = fetch_text(args.metrics_url)
            prom_sums, prom_raw = parse_prometheus(prom_text)
            prom_hists = parse_prometheus_histograms(prom_text)
        except Exception as e:  # noqa: BLE001 - recorded, never fatal
            prom_error = f"{type(e).__name__}: {e}"
            print(f"[warn] metrics-url unavailable: {prom_error}", file=sys.stderr)

    has_client = bool(eff and eff["levels"])
    has_server = bool(server_rows)
    has_prom = bool(prom_sums)

    if not (has_client or has_server or has_prom):
        print("ERROR: no inputs supplied (need --efficiency-json, --metrics-dir, "
              "or --metrics-url)", file=sys.stderr)
        return 2

    itl = itl_from_histograms(prom_hists)
    tpot_ok = pct(server["tpot_per_request"], 0.5) is not None
    itl_ok = itl is not None

    levels = eff["levels"] if has_client else [{"concurrency": None, "case": None}]
    level_tables = []
    for lvl in levels:
        sections = build_level_sections(lvl, server, prom_sums, prom_hists)
        level_tables.append({"case": lvl.get("case"), "concurrency": lvl.get("concurrency"),
                             "sections": sections})

    coverage = build_coverage(has_client, has_server, has_prom,
                              itl_ok=itl_ok, tpot_ok=tpot_ok)
    unavailable = sorted({f"{c['section']}::{c['metric']}" for c in coverage if not c["available"]})

    result = {
        "schema": "perf-scorecard.v1",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "config": {
            "run_tag": args.run_tag,
            "url": args.url,
            "model": args.model,
            "efficiency_json": efficiency_path,
            "metrics_dir": args.metrics_dir,
            "metrics_url": args.metrics_url,
            "levels": args.levels,
            "count_per_level": args.count_per_level,
            "out_tokens": args.out_tokens,
            "mode": args.mode,
            "offline": not (args.metrics_url and args.metrics_url.startswith(("http://", "https://"))),
        },
        "sources": {
            "client": efficiency_path if eff else None,
            "server_files": server_files,
            "prometheus_url": args.metrics_url,
            "prometheus_error": prom_error,
        },
        "base_table": BASE_TABLE,
        "discipline_notes": DISCIPLINE_NOTES,
        "notes": [
            "Client-sourced cells are level-scoped; server/Prometheus cells are "
            "window-scoped and repeated per level (JSONL carries no concurrency label).",
            "If --efficiency-json and --metrics-dir come from different runs/windows, "
            "the merged table mixes windows; alignment is the caller's responsibility.",
            "`aggregate decode TPS` is the F39 relative definition, NOT the spec "
            "output_tokens/wall_time.",
            "`ITL/TPOT`: ITL is window-scoped (Prometheus histogram "
            "sglang:inter_token_latency_seconds, source=prometheus, scope=window) "
            "and must NOT be read as a per-request inter-token latency. TPOT is "
            "per-request scoped (source=server, scope=per-request) and is the "
            "upper-bound approximation `e2e_latency / completion_tokens` of the "
            "owner definition `(E2E - TTFT) / output_tokens`, because the JSONL "
            "has no independent TTFT field.",
        ],
        "levels": level_tables,
        "window": {
            "n_requests": server["n_requests"],
            "server": {
                "prompt_tokens": {"p50": pct(server["prompt_tokens"], .5),
                                  "p95": pct(server["prompt_tokens"], .95)},
                "output_tokens": {"p50": pct(server["output_tokens"], .5),
                                  "p95": pct(server["output_tokens"], .95)},
                "queue_time": {"p50": pct(server["queue_time"], .5),
                               "p95": pct(server["queue_time"], .95)},
                "e2e_latency": {"p50": pct(server["e2e_latency"], .5),
                                "p95": pct(server["e2e_latency"], .95)},
                "newly_prefilled": {"p50": pct(server["newly_prefilled"], .5),
                                    "p95": pct(server["newly_prefilled"], .95)},
                "cached_tokens": {"p50": pct(server["cached_tokens"], .5),
                                  "mean": (sum(server["cached_tokens"]) / len(server["cached_tokens"]))
                                          if server["cached_tokens"] else None},
                "prefix_hit_rate": server["prefix_hit_rate"],
                "prefill_time": {"p50": pct(server["prefill_time"], .5),
                                 "p95": pct(server["prefill_time"], .95)},
                "prefill_tps_window": server["prefill_tps_window"],
                "prefill_tps_p50": pct(server["prefill_tps_per_request"], .5),
                "l1_tokens_p50": pct(server["l1_tokens"], .5),
                "l2_tokens_p50": pct(server["l2_tokens"], .5),
                "l3_tokens_p50": pct(server["l3_tokens"], .5),
                "avoidable_recompute_tokens_p50": pct(server["avoidable_recompute_tokens"], .5),
                "num_retractions_sum": int(sum(server["num_retractions"])) if server["num_retractions"] else 0,
                # Transparency: server decode_throughput has shown anomalous values
                # (recon report defect #7). Recorded but NOT used in the table.
                "decode_throughput_server_p50_flagged_anomalous":
                    pct(server["decode_throughput_server"], .5),
                # ITL/TPOT provenance and scope (see notes[] above).
                "tpot": {
                    "p50": pct(server["tpot_per_request"], .5),
                    "p95": pct(server["tpot_per_request"], .95),
                    "source": "server" if tpot_ok else "UNAVAILABLE",
                    "scope": "per-request",
                    "definition": "e2e_latency / completion_tokens "
                                  "(upper-bound approximation of (E2E-TTFT)/N)",
                },
            },
            "prometheus_itl": {
                "metric": "sglang:inter_token_latency_seconds",
                "mean": itl.get("mean") if itl else None,
                "p50": itl.get("p50") if itl else None,
                "p95": itl.get("p95") if itl else None,
                "source": "prometheus" if itl_ok else "UNAVAILABLE",
                "scope": "window",
            },
            "prometheus": prom_sums,
        },
        "coverage": coverage,
        "unavailable": unavailable,
    }

    for table in level_tables:
        title = f"{args.run_tag} / {table['case']} / c={table['concurrency']}"
        print(render_table(title, table["sections"]))
        print()

    print("口径纪律 / output discipline:")
    for note in DISCIPLINE_NOTES:
        print(f"  - {note}")
    print("notes:")
    for note in result["notes"]:
        print(f"  - {note}")
    print("UNAVAILABLE fields:")
    if unavailable:
        for u in unavailable:
            print(f"  - {u}")
    else:
        print("  (none)")
    if prom_error:
        print(f"  - prometheus fetch failed: {prom_error}")

    if args.out:
        with open(args.out, "w") as fh:
            json.dump(result, fh, indent=2, ensure_ascii=False)
        print(f"\nWROTE {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
