"""T012 conditional three-tier check: the production L1+L2+L3 stack under Humming."""

import json
import os
import re
import sys

COUNTERS = (
    "sglang:cached_tokens_total",
    "sglang:backuped_tokens_total",
    "sglang:evicted_tokens_total",
    "sglang:hicache_backup_tokens_total",
    "sglang:hicache_prompt_tokens_total",
    "sglang:max_total_num_tokens",
    "sglang:max_total_num_tokens_swa",
    "sglang:cache_hit_rate",
)


def prom(path):
    values = {}
    if not os.path.exists(path):
        return values
    with open(path) as f:
        for line in f:
            if line.startswith("#") or not line.strip():
                continue
            name, _, rest = line.partition("{")
            if not rest:
                name, _, value = line.rpartition(" ")
            else:
                value = line.rsplit(" ", 1)[1]
            try:
                values[name.strip()] = values.get(name.strip(), 0.0) + float(value)
            except ValueError:
                continue
    return values


def cell(root, name):
    directory = os.path.join(root, f"tiers-{name}")
    summary = json.load(open(os.path.join(directory, "official-summary.json")))
    metrics = prom(os.path.join(directory, "metrics-at-end.prom"))
    log = os.path.join(directory, "server.log")
    text = open(log, errors="ignore").read() if os.path.exists(log) else ""
    payloads = []
    hashes = os.path.join(directory, "hashes.jsonl")
    if os.path.exists(hashes):
        for line in open(hashes):
            line = line.strip()
            if line:
                payloads.append(json.loads(line).get("sha") or line)
    return {
        "summary": summary,
        "counters": {key: metrics.get(key) for key in COUNTERS},
        "extent_events": len(re.findall(r"extent_(read|write)", text)),
        "host_backup_events": len(re.findall(r"hicache.*backup", text, re.I)),
        "payloads": sorted(payloads),
    }


def main(root):
    off = cell(root, "off")
    on = cell(root, "on")
    tps = {
        "off": off["summary"]["official_output_token_throughput"],
        "on": on["summary"]["official_output_token_throughput"],
    }
    tps_delta = 100.0 * (tps["on"] / tps["off"] - 1.0)
    checks = {
        "cells": {
            "off": {
                "tps": tps["off"],
                "bench_s": off["summary"]["bench_duration_seconds"],
                "completed": off["summary"]["completed_requests"],
                "total": off["summary"]["total_requests"],
                "failed": off["summary"]["failed_requests"],
                "counters": off["counters"],
                "extent_events": off["extent_events"],
                "host_backup_events": off["host_backup_events"],
            },
            "on": {
                "tps": tps["on"],
                "bench_s": on["summary"]["bench_duration_seconds"],
                "completed": on["summary"]["completed_requests"],
                "total": on["summary"]["total_requests"],
                "failed": on["summary"]["failed_requests"],
                "counters": on["counters"],
                "extent_events": on["extent_events"],
                "host_backup_events": on["host_backup_events"],
            },
        },
        "tps_delta_pct": tps_delta,
        "payload_multiset_identical": off["payloads"] == on["payloads"],
        "payload_counts": {"off": len(off["payloads"]), "on": len(on["payloads"])},
        "capacity_ratio": {
            key: (
                None
                if not off["counters"].get(key)
                else on["counters"][key] / off["counters"][key]
            )
            for key in (
                "sglang:max_total_num_tokens",
                "sglang:max_total_num_tokens_swa",
            )
        },
        "host_tier_used_both_arms": bool(
            (off["counters"].get("sglang:backuped_tokens_total") or 0) > 0
            and (on["counters"].get("sglang:backuped_tokens_total") or 0) > 0
        ),
        "extent_tier_used_both_arms": off["extent_events"] > 0
        and on["extent_events"] > 0,
    }
    gates = {
        "all_cells_complete": not (
            off["summary"]["completed_requests"] == off["summary"]["total_requests"]
            and on["summary"]["completed_requests"] == on["summary"]["total_requests"]
            and not off["summary"]["failed_requests"]
            and not on["summary"]["failed_requests"]
        ),
        "payload_multiset_identical": not checks["payload_multiset_identical"],
        "capacity_not_reduced": any(
            ratio is not None and ratio < 0.98
            for ratio in checks["capacity_ratio"].values()
        ),
        "host_tier_active_in_both": not checks["host_tier_used_both_arms"],
        "extent_tier_active_in_both": not checks["extent_tier_used_both_arms"],
        "no_throughput_regression": tps_delta < -1.0,
    }
    failed = sorted(name for name, bad in gates.items() if bad)
    verdict = "PASS" if not failed else "FAIL"
    result = {
        "verdict": verdict,
        "failed_gates": failed,
        "checks": checks,
        "gates": gates,
    }
    with open(os.path.join(root, "tiers-verdict.json"), "w") as f:
        json.dump(result, f, indent=1, sort_keys=True)
    print(json.dumps({"verdict": verdict, "failed": failed}, indent=1))
    print(json.dumps(checks, indent=1, sort_keys=True))
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
