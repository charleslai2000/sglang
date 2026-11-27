"""T013 combo comparison: (Humming + Triton) vs (Humming + FA2) per workload."""

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
    "sglang:cuda_graph_passes_total",
    "sglang:extend_device_time_total",
)
CC_TAG = re.compile(
    r", 'CACHE_HIT_METRIC': 'data:([0-9]+), sa:([0-9]+), fo:([0-9]+), sv:([0-9]+)'"
)


def prom(path):
    values = {}
    if not os.path.exists(path):
        return values
    for line in open(path):
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
            pass
    return values


def peak_mem(path):
    best = None
    if not os.path.exists(path):
        return None
    for index, line in enumerate(open(path)):
        if index == 0:
            continue
        parts = line.rsplit(",", 3)
        if len(parts) < 4:
            continue
        try:
            used = float(parts[2].strip().split()[0])
        except (ValueError, IndexError):
            continue
        best = used if best is None else max(best, used)
    return best


def cell(root, name):
    directory = os.path.join(root, "cells", name)
    summary = json.load(open(os.path.join(directory, "official-summary.json")))
    metrics = prom(os.path.join(directory, "metrics-at-end.prom"))
    coverage = None
    coverage_path = os.path.join(directory, "ragged-coverage.json")
    if os.path.exists(coverage_path):
        coverage = json.load(open(coverage_path))
    hashes = []
    hash_path = os.path.join(directory, "hashes.jsonl")
    if os.path.exists(hash_path):
        for line in open(hash_path):
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            hashes.append(row.get("request_payload_sha256") or row.get("sha") or line)
    log_path = os.path.join(directory, "server.log")
    log = open(log_path, errors="ignore").read() if os.path.exists(log_path) else ""
    return {
        "tps": summary["official_output_token_throughput"],
        "bench_s": summary["bench_duration_seconds"],
        "client_wall_s": summary["client_wall_seconds"],
        "extend_s": summary["extend_forward_seconds"],
        "decode_s": summary["decode_forward_seconds"],
        "ttft_s": summary["average_ttft_s"],
        "itl_s": summary["average_itl_s"],
        "duty": summary["forward_duty_pct_vs_bench_window"],
        "completed": summary["completed_requests"],
        "total": summary["total_requests"],
        "failed": summary["failed_requests"],
        "git_head": summary["git_head"],
        "peak_mem_mib": peak_mem(os.path.join(directory, "gpu-samples.csv")),
        "counters": {key: metrics.get(key) for key in COUNTERS},
        "coverage": coverage,
        "decode_graph_captured": "Capture target decode CUDA graph end" in log,
        "humming_dispatch": len(
            re.findall(r"humming::humming_gemm|void humming<", log)
        ),
        "payloads": sorted(hashes),
    }


def mean(values):
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else None


def workload(root, prefix, tag):
    triton = [
        name
        for name in sorted(os.listdir(os.path.join(root, "cells")))
        if name.startswith(f"{prefix}-triton-")
    ]
    fa2 = [
        name
        for name in sorted(os.listdir(os.path.join(root, "cells")))
        if name.startswith(f"{prefix}-fa2-")
    ]
    arms = {
        "triton": [cell(root, name) for name in triton],
        "fa2": [cell(root, name) for name in fa2],
    }
    measured = {name: value for name, value in zip(triton + fa2, arms["triton"] + arms["fa2"])}
    if not arms["triton"] or not arms["fa2"]:
        return {
            "tag": tag,
            "skipped": "missing arm",
            "cells": {k: len(v) for k, v in arms.items()},
        }
    a, b = arms["triton"], arms["fa2"]
    a_tps, b_tps = mean([c["tps"] for c in a]), mean([c["tps"] for c in b])
    payload_sets = {tuple(c["payloads"]) for c in a + b}
    coverage = [c["coverage"]["coverage"] for c in b if c["coverage"]]
    result = {
        "tag": tag,
        "cells": {
            name: {
                "tps": round(c["tps"], 2),
                "bench_s": round(c["bench_s"], 1),
                "extend_s": round(c["extend_s"], 1),
                "decode_s": round(c["decode_s"], 1),
                "ttft_s": round(c["ttft_s"], 3),
                "duty": round(c["duty"], 2),
                "completed": f"{c['completed']}/{c['total']}",
                "failed": c["failed"],
                "peak_mem_mib": c["peak_mem_mib"],
                "decode_graph_captured": c["decode_graph_captured"],
                "counters": c["counters"],
                "coverage": c["coverage"],
            }
            for name, c in measured.items()
        },
        "tps": {
            "triton_mean": round(a_tps, 2),
            "fa2_mean": round(b_tps, 2),
            "delta_pct": round(100.0 * (b_tps / a_tps - 1.0), 2),
            "fa2_spread_pct": round(
                100.0 * (max(c["tps"] for c in b) / min(c["tps"] for c in b) - 1.0), 2
            ),
        },
        "all_cells_complete": all(
            c["completed"] == c["total"] and not c["failed"] for c in a + b
        ),
        "payload_multiset_identical": len(payload_sets) == 1,
        "payload_counts": [len(c["payloads"]) for c in a + b],
        "peak_mem_mib": {
            "triton": [c["peak_mem_mib"] for c in a],
            "fa2": [c["peak_mem_mib"] for c in b],
        },
        "decode_graph_captured": all(c["decode_graph_captured"] for c in a + b),
        "fa2_coverage": {
            "plans": [c.get("plans") for c in coverage],
            "skip_no_prefix": [c.get("skip_no_prefix") for c in coverage],
            "skip_over_budget": [c.get("skip_over_budget") for c in coverage],
            "max_prefix_bytes": [c.get("max_prefix_bytes") for c in coverage],
            "owner_conversions": [c.get("owner_conversions") for c in coverage],
            "shared_reuses": [c.get("shared_reuses") for c in coverage],
        },
        "capacity": {
            "triton": [c["counters"].get("sglang:max_total_num_tokens") for c in a],
            "fa2": [c["counters"].get("sglang:max_total_num_tokens") for c in b],
        },
        "tiers": {
            name: {
                "l1_cached_tokens": c["counters"].get("sglang:cached_tokens_total"),
                "l2_backup_tokens": c["counters"].get(
                    "sglang:hicache_backup_tokens_total"
                ),
                "prompt_tokens": c["counters"].get(
                    "sglang:hicache_prompt_tokens_total"
                ),
            }
            for name, c in measured.items()
        }
        if prefix in ("tiers", "long")
        else None,
    }
    return result


def main(root):
    workloads = {
        "c8": workload(root, "c8", "original C-8 L1-only"),
        "tiers": workload(root, "tiers", "production three-tier HiCache"),
        "long": workload(root, "long", "T010 long-context three-tier"),
    }
    payload = {"workloads": workloads}
    payload["failures"] = [
        f"{key}: {reason}"
        for key, value in workloads.items()
        for reason in (
            ["missing arm"]
            if value.get("skipped")
            else ([] if value["all_cells_complete"] else ["incomplete cells"])
            + (
                []
                if value["payload_multiset_identical"]
                else ["payload multiset differs"]
            )
            + ([] if value["decode_graph_captured"] else ["decode graph missing"])
        )
    ]
    path = os.path.join(root, "combo-verdict.json")
    json.dump(payload, open(path, "w"), indent=1, sort_keys=True)
    print(json.dumps(payload, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
