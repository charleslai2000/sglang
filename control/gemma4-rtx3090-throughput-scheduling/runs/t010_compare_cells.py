#!/usr/bin/env python3
"""T010: side-by-side tier-cell comparison from the existing run artifacts.

Reads only files the wrapper already produces (official-summary.txt,
metrics-at-end.prom, pool-series.jsonl, server.log) — no new telemetry.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

SOURCES = ("l1", "l2", "l3", "newly_prefilled")


def prom(path: Path) -> dict[str, float]:
    out: dict[str, float] = {}
    if not path.exists():
        return out
    for line in path.read_text().splitlines():
        if not line or line.startswith("#"):
            continue
        key, _, val = line.rpartition(" ")
        try:
            out[key] = float(val)
        except ValueError:
            pass
    return out


def pick(m: dict[str, float], name: str, **labels) -> float:
    total = 0.0
    for k, v in m.items():
        if not k.startswith(name):
            continue
        if all(f'{lk}="{lv}"' in k for lk, lv in labels.items()):
            total += v
    return total


def series_stats(path: Path) -> dict[str, float]:
    stats: dict[str, float] = {}
    if not path.exists():
        return stats
    for line in path.read_text().splitlines():
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if "error" in rec:
            continue
        for k, v in rec.items():
            if not isinstance(v, (int, float)):
                continue
            stats[f"max:{k}"] = max(stats.get(f"max:{k}", 0.0), float(v))
    return stats


def cell(run: Path) -> dict[str, object]:
    summary = {}
    txt = run / "official-summary.txt"
    if txt.exists():
        for line in txt.read_text().splitlines():
            m = re.match(r"(\w+)=([-\d.eE+]+)", line.strip())
            if m:
                key, val = m.group(1), m.group(2)
                try:
                    summary[key] = float(val)
                except ValueError:
                    summary[key] = val
    m = prom(run / "metrics-at-end.prom")
    stats = series_stats(run / "pool-series.jsonl")
    log = run / "server.log"
    log_text = log.read_text(errors="ignore") if log.exists() else ""
    row = {
        "run": run.name,
        "tps": summary.get("official_tps"),
        "duty": summary.get("duty_pct"),
        "bench_s": summary.get("bench_s"),
        "completed": f"{summary.get('completed')}/{summary.get('failed')}",
        "l1": pick(m, "sglang:hicache_prompt_tokens_total", source="l1"),
        "l2": pick(m, "sglang:hicache_prompt_tokens_total", source="l2"),
        "l3": pick(m, "sglang:hicache_prompt_tokens_total", source="l3"),
        "new": pick(m, "sglang:hicache_prompt_tokens_total", source="newly_prefilled"),
        "extend_s": pick(
            m, "sglang:forward_execution_seconds_total", category="extend"
        ),
        "decode_s": pick(
            m, "sglang:forward_execution_seconds_total", category="decode"
        ),
        "d2h_tokens": pick(m, "sglang:hicache_backup_tokens_total"),
        "d2h_bytes": pick(m, "sglang:hicache_backup_bytes_total"),
        "d2h_s": pick(m, "sglang:hicache_backup_duration_seconds_sum"),
        "l3_write_tokens": pick(m, "sglang:backuped_tokens_total"),
        "evicted_tokens": pick(m, "sglang:evicted_tokens_total"),
        "evict_s": pick(m, "sglang:eviction_duration_seconds_sum"),
        "hit_rate": pick(m, "sglang:cache_hit_rate"),
        "host_peak": stats.get("max:sglang:hicache_host_used_tokens", 0.0),
        "kv_peak": stats.get("max:sglang:kv_used_tokens", 0.0),
        "save_tokens": len(
            re.findall(r'"evt": "extent_write"|evt=extent_write', log_text)
        ),
        "restore": len(
            re.findall(r"disposition=RESTORE|disposition=PARTIAL", log_text)
        ),
        "recompute": len(re.findall(r"disposition=RECOMPUTE", log_text)),
        "prefetch_issued": len(re.findall(r"evt=prefetch_issued", log_text)),
        "frontier_wait": len(re.findall(r"evt=frontier_wait", log_text)),
        "graph_true": log_text.count("cuda graph: True"),
        "graph_false": log_text.count("cuda graph: False"),
    }
    return row


def main() -> int:
    runs = [Path(p) for p in sys.argv[1:]]
    rows = [cell(r) for r in runs]
    keys = [
        "run",
        "tps",
        "duty",
        "bench_s",
        "completed",
        "hit_rate",
        "l1",
        "l2",
        "l3",
        "new",
        "extend_s",
        "decode_s",
        "d2h_tokens",
        "d2h_bytes",
        "d2h_s",
        "l3_write_tokens",
        "evicted_tokens",
        "evict_s",
        "host_peak",
        "kv_peak",
        "restore",
        "recompute",
        "prefetch_issued",
        "frontier_wait",
        "graph_true",
        "graph_false",
    ]
    width = max(len(k) for k in keys)
    header = " " * (width + 2) + "".join(f"{r['run'][-24:]:>26}" for r in rows)
    print(header)
    for k in keys:
        if k == "run":
            continue
        vals = []
        for r in rows:
            v = r.get(k)
            if isinstance(v, float):
                vals.append(f"{v:>26,.1f}")
            else:
                vals.append(f"{str(v):>26}")
        print(f"{k:<{width}}  " + "".join(vals))

    # Derived: extend time actually spent per newly-prefilled token, and the
    # prefill time the tiers saved relative to recomputing every prompt token.
    print()
    for r in rows:
        total_prompt = sum(r[k] or 0 for k in ("l1", "l2", "l3", "new"))
        new = r["new"] or 0
        if not new:
            continue
        per_tok_ms = (r["extend_s"] or 0) * 1e3 / new
        print(
            f"{r['run'][-28:]:>30}: prompt={total_prompt:,.0f} "
            f"cached={total_prompt - new:,.0f} ({(total_prompt - new) / max(total_prompt, 1) * 100:.1f}%) "
            f"extend/new-token={per_tok_ms:.2f} ms  "
            f"L2={r['l2']:,.0f} L3={r['l3']:,.0f}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
