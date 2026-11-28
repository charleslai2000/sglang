#!/usr/bin/env python3
"""T015: compare the acceptance cells against the T013 accepted baseline.

Reports, per workload: official TPS, duty, completions, KV capacity, payload
multiset identity, peak memory and the FA2 coverage counters (including how much
of the previously skipped work the sub-batch path now covers).

Usage: t015_compare.py <cells-dir> [--baseline path/to/T013-MERGE-ACCEPTANCE.json]
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import pathlib

T013_ACCEPTED = {
    "c8": {"triton": 737.55, "fa2": 760.17},
    "tiers": {"triton": 624.85, "fa2": 644.21},
    "long": {"triton": 116.51, "fa2": 135.22},
}


def parse_summary(path: pathlib.Path) -> dict:
    text = path.read_text().strip()
    out = {}
    for token in text.split():
        if "=" in token:
            key, value = token.split("=", 1)
            out[key] = value
    return out


def payload_digest(path: pathlib.Path) -> dict | None:
    if not path.exists():
        return None
    counts = collections.Counter()
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        text = record.get("text") or record.get("output") or ""
        counts[hashlib.sha1(text.encode()).hexdigest()] += 1
    ordered = sorted(counts.items())
    digest = hashlib.sha1(repr(ordered).encode()).hexdigest()[:16]
    return {"records": sum(counts.values()), "distinct": len(counts), "digest": digest}


def capacity(path: pathlib.Path) -> dict | None:
    if not path.exists():
        return None
    out = {}
    for line in path.read_text().splitlines():
        for key, value in (
            ("max_total_num_tokens", "max_total_num_tokens"),
            ("max_total_num_tokens_swa", "max_total_num_tokens_swa"),
        ):
            if line.startswith(key):
                out[key] = line.split()[-1]
    return out or None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("cells_dir")
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    cells_dir = pathlib.Path(args.cells_dir)
    report = {}
    for cell in sorted(cells_dir.iterdir()):
        if not cell.is_dir():
            continue
        summary_file = cell / "official-summary.txt"
        if not summary_file.exists():
            continue
        summary = parse_summary(summary_file)
        workload, arm = cell.name.split("-")[:2]
        entry = {
            "cell": cell.name,
            "workload": workload,
            "arm": arm,
            "tps": float(summary.get("official_tps", "nan")),
            "duty_pct": float(summary.get("duty_pct", "nan")),
            "completed": summary.get("completed"),
            "failed": summary.get("failed"),
            "accepted_baseline_tps": T013_ACCEPTED.get(workload, {}).get(arm),
            "payloads": payload_digest(cell / "hashes.jsonl"),
            "capacity": capacity(cell / "capacity-at-end.metrics"),
        }
        coverage_file = cell / "ragged-coverage.json"
        if coverage_file.exists():
            coverage = json.loads(coverage_file.read_text())
            entry["coverage"] = coverage.get("coverage")
            entry["forwards_seen"] = coverage.get("forwards_seen")
        peaks = cell / "gpu-samples.csv"
        if peaks.exists():
            peak = 0
            for line in peaks.read_text().splitlines()[1:]:
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 3:
                    try:
                        peak = max(peak, float(parts[2].split()[0]))
                    except ValueError:
                        continue
            entry["peak_vram_mib"] = peak
        report[cell.name] = entry

    text = json.dumps(report, indent=2)
    print(text)
    out = pathlib.Path(args.out) if args.out else cells_dir / "comparison.json"
    out.write_text(text + "\n")
    print(f"wrote {out}")

    print("\n== TPS vs T013 accepted")
    for name, entry in report.items():
        base = entry["accepted_baseline_tps"]
        if base:
            print(
                f"{name:24s} tps={entry['tps']:7.2f} base={base:7.2f} "
                f"delta={100 * (entry['tps'] / base - 1):+6.2f}% "
                f"payloads={entry['payloads']['digest'] if entry['payloads'] else '-'}"
            )


if __name__ == "__main__":
    main()
