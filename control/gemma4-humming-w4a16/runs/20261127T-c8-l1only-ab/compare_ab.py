"""T012 C-8 L1-only A/B verdict: Marlin control vs Humming post-load cells."""

import json
import os
import sys

MIN_MEAN_GAIN_PCT = 2.0
CELLS = ("off", "on1", "on2")


def load_cell(root, cell):
    path = os.path.join(root, f"c8-{cell}", "official-summary.json")
    with open(path) as f:
        summary = json.load(f)
    hashes = os.path.join(root, f"c8-{cell}", "hashes.jsonl")
    payloads = []
    if os.path.exists(hashes):
        with open(hashes) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                payloads.append(
                    record.get("sha") or line
                )
    return summary, sorted(payloads)


def main(root):
    data = {}
    for cell in CELLS:
        summary, payloads = load_cell(root, cell)
        data[cell] = {"summary": summary, "payloads": payloads}

    def tps(cell):
        return data[cell]["summary"]["official_output_token_throughput"]

    gains = {cell: 100.0 * (tps(cell) / tps("off") - 1.0) for cell in ("on1", "on2")}
    mean_gain = sum(gains.values()) / len(gains)
    payloads = {cell: data[cell]["payloads"] for cell in CELLS}
    complete = {
        cell: bool(
            data[cell]["summary"]["bench_complete"]
            and data[cell]["summary"]["completed_requests"]
            == data[cell]["summary"]["total_requests"]
        )
        for cell in CELLS
    }

    checks = {
        "cells": {
            cell: {
                "tps": tps(cell),
                "bench_s": data[cell]["summary"]["bench_duration_seconds"],
                "client_wall_s": data[cell]["summary"]["client_wall_seconds"],
                "extend_s": data[cell]["summary"]["extend_forward_seconds"],
                "decode_s": data[cell]["summary"]["decode_forward_seconds"],
                "duty_pct": data[cell]["summary"]["forward_duty_pct_vs_bench_window"],
                "completed": data[cell]["summary"]["completed_requests"],
                "total": data[cell]["summary"]["total_requests"],
                "failed": data[cell]["summary"]["failed_requests"],
                "ttft_s": data[cell]["summary"]["average_ttft_s"],
                "itl_s": data[cell]["summary"]["average_itl_s"],
            }
            for cell in CELLS
        },
        "tps_gain_pct": gains,
        "tps_gain_mean_pct": mean_gain,
        "payload_multiset_identical": len({tuple(v) for v in payloads.values()}) == 1,
        "payload_counts": {cell: len(payloads[cell]) for cell in CELLS},
        "bench_complete": complete,
        "decode_time_delta_pct": {
            cell: 100.0
            * (
                data[cell]["summary"]["decode_forward_seconds"]
                / data["off"]["summary"]["decode_forward_seconds"]
                - 1.0
            )
            for cell in ("on1", "on2")
        },
    }

    gates = {
        "all_cells_complete": not all(complete.values()),
        "payload_multiset_identical": not checks["payload_multiset_identical"],
        "candidate_beats_control_both_reps": not (
            gains["on1"] > 0 and gains["on2"] > 0
        ),
        "mean_gain_at_least_threshold": mean_gain < MIN_MEAN_GAIN_PCT,
    }
    failed = sorted(name for name, bad in gates.items() if bad)
    verdict = "PASS" if not failed else "FAIL"
    result = {
        "verdict": verdict,
        "failed_gates": failed,
        "min_mean_gain_pct": MIN_MEAN_GAIN_PCT,
        "checks": checks,
        "gates": gates,
    }
    with open(os.path.join(root, "ab-verdict.json"), "w") as f:
        json.dump(result, f, indent=1, sort_keys=True)
    print(json.dumps({"verdict": verdict, "failed": failed}, indent=1))
    print(json.dumps(checks, indent=1, sort_keys=True))
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
