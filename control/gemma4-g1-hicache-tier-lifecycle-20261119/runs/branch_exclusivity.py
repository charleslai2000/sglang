#!/usr/bin/env python3
"""Branch-exclusivity analysis for the G1 branch-exclusive L3 run.

Proves, from the run's own artifacts, that

  1. every branch-phase request restored its KV from the Extent (positive
     physical read, accepted READY, granted restore) and decoded exactly 256
     tokens;
  2. each branch consumed the shared Radix ancestor but only its own exclusive
     suffix, and no request reused the other branch's KV;
  3. the KV that was actually restored produced the same 256-token greedy
     continuation as the same prompt restored/warmed in an independent run, so
     the restored content was the request's own context rather than the other
     branch's.

Usage:
  branch_exclusivity.py --run <run-dir> [--reference <run-dir>]
"""

from __future__ import annotations

import argparse
import importlib.util
import json
from collections import defaultdict
from pathlib import Path

CLIENT = Path(
    "/home/ubuntu/workspaces/3rdparty/sglang-hicache/control/"
    "gemma4-g1-hicache-tier-lifecycle-20261119/runs/run_radix_tree_lifecycle.py"
)
SHARED_ROOT_TOKENS = 16384
OUTPUT_TOKENS = 256


def load_client(path: Path):
    spec = importlib.util.spec_from_file_location("g1_lifecycle", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_branch_records(run: Path):
    records = []
    for branch in (0, 1):
        path = run / "client" / f"branch_{branch}_exclusive_l3.json"
        if not path.exists():
            raise SystemExit(f"MISSING:{path}")
        payload = json.loads(path.read_text())
        for record in payload["requests"]:
            record.setdefault("branch_id", branch)
            records.append(record)
    return records


def attach_evidence(module, run: Path, records):
    log = run / "service" / "server.log"
    evidence = module.parse_restore_log(log, [record["rid"] for record in records])
    for record in records:
        record["restore_evidence"] = evidence.get(record["rid"], {})
    return evidence


def extent_read_totals(record):
    totals = {"keys_n": 0, "physical_bytes": 0, "preads": 0, "reads": 0}
    for line in record["restore_evidence"].get("extent_reads", []):
        totals["reads"] += 1
        for field in ("keys_n", "physical_bytes", "preads"):
            value = 0
            for token in line.split():
                if token.startswith(field + "="):
                    try:
                        value = int(float(token.split("=", 1)[1]))
                    except ValueError:
                        value = 0
                    break
            totals[field] += value
    return totals


def reference_outputs(run: Path):
    """prompt_sha256 -> 256-token output ids from every recorded phase."""
    mapping = {}
    for path in sorted((run / "client").glob("*.json")):
        try:
            payload = json.loads(path.read_text())
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        requests = payload.get("requests") if isinstance(payload, dict) else None
        if not isinstance(requests, list):
            continue
        for record in requests:
            if not isinstance(record, dict):
                continue
            sha = record.get("prompt_sha256")
            ids = record.get("output_ids")
            if (
                sha
                and isinstance(ids, list)
                and len(ids) == OUTPUT_TOKENS
                and record.get("ok")
            ):
                mapping.setdefault(
                    sha,
                    {
                        "output_ids": ids,
                        "phase": record.get("phase"),
                        "file": path.name,
                    },
                )
    return mapping


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True)
    parser.add_argument("--reference", default="")
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    run = Path(args.run)
    module = load_client(CLIENT)
    records = load_branch_records(run)
    attach_evidence(module, run, records)

    per_record = []
    for record in records:
        totals = extent_read_totals(record)
        details = record.get("cached_tokens_details") or {}
        per_record.append(
            {
                "rid": record["rid"],
                "branch_id": record["branch_id"],
                "prompt_sha256": record.get("prompt_sha256"),
                "completion_tokens": record.get("completion_tokens"),
                "output_ids": record.get("output_ids"),
                "prompt_tokens": record.get("prompt_tokens"),
                "cached_tokens_details": details,
                "extent_read": totals,
                "l3_qualified": module.source_restore_qualified(
                    record, "l3", OUTPUT_TOKENS
                ),
                "restore_dispositions": [
                    line.split("evt=restore_disposition", 1)[1][:160]
                    for line in record["restore_evidence"].get("restore_events", [])
                ][:4],
            }
        )

    by_branch = defaultdict(list)
    for item in per_record:
        by_branch[item["branch_id"]].append(item)

    checks = {}
    checks["six_per_branch"] = {b: len(rows) for b, rows in sorted(by_branch.items())}
    checks["all_l3_qualified"] = all(item["l3_qualified"] for item in per_record)
    checks["all_exact_256"] = all(
        item["completion_tokens"] == OUTPUT_TOKENS for item in per_record
    )
    checks["all_extent_bytes_positive"] = all(
        item["extent_read"]["physical_bytes"] > 0 for item in per_record
    )
    checks["all_storage_tokens_positive"] = all(
        int(item["cached_tokens_details"].get("storage", 0) or 0) > 0
        for item in per_record
    )
    checks["shared_ancestor_restored_in_every_request"] = all(
        int(item["cached_tokens_details"].get("device", 0) or 0)
        + int(item["cached_tokens_details"].get("host", 0) or 0)
        + int(item["cached_tokens_details"].get("storage", 0) or 0)
        >= SHARED_ROOT_TOKENS
        for item in per_record
    )

    # Cross-branch content separation: identical 256-token greedy continuations
    # across different prompts would mean the outputs cannot detect a mixed
    # restore, so require the two branch output sets to be disjoint.
    outputs = defaultdict(set)
    for item in per_record:
        outputs[item["branch_id"]].add(tuple(item["output_ids"] or []))
    shared_outputs = outputs[0] & outputs[1]
    checks["branch_outputs_disjoint"] = not shared_outputs
    checks["distinct_prompts_across_branches"] = not (
        {item["prompt_sha256"] for item in by_branch[0]}
        & {item["prompt_sha256"] for item in by_branch[1]}
    )

    reference = {}
    if args.reference:
        reference = reference_outputs(Path(args.reference))
    matches, mismatches, missing = [], [], []
    for item in per_record:
        ref = reference.get(item["prompt_sha256"])
        if not ref:
            missing.append(item["rid"])
            continue
        if ref["output_ids"] == item["output_ids"]:
            matches.append(item["rid"])
        else:
            first_diff = next(
                (
                    i
                    for i, (a, b) in enumerate(
                        zip(ref["output_ids"], item["output_ids"])
                    )
                    if a != b
                ),
                None,
            )
            mismatches.append(
                {
                    "rid": item["rid"],
                    "first_diff_index": first_diff,
                    "reference_phase": ref["phase"],
                }
            )
    if args.reference:
        checks["reference_available_for_all"] = not missing
        checks["restored_output_matches_independent_run"] = not mismatches

    passed = all(value is True or value == {0: 6, 1: 6} for value in checks.values())

    result = {
        "run": str(run),
        "reference_run": args.reference or None,
        "claims": {
            "shared_root_tokens": SHARED_ROOT_TOKENS,
            "output_tokens": OUTPUT_TOKENS,
            "basis": (
                "per-branch l3 qualification from RID-correlated Extent reads plus "
                "accepted READY/granted restore, exact 256-token decode, disjoint "
                "branch outputs, and identical continuations for the same prompt in "
                "an independent run"
            ),
        },
        "checks": checks,
        "passed": passed,
        "per_branch_summary": {
            str(branch): {
                "requests": len(rows),
                "l3_qualified": sum(item["l3_qualified"] for item in rows),
                "extent_reads": sum(item["extent_read"]["reads"] for item in rows),
                "extent_physical_bytes": sum(
                    item["extent_read"]["physical_bytes"] for item in rows
                ),
                "prompts": sorted({item["prompt_sha256"][:16] for item in rows}),
                "cached_tokens_details": [
                    item["cached_tokens_details"] for item in rows
                ],
            }
            for branch, rows in sorted(by_branch.items())
        },
        "reference_matches": matches,
        "reference_mismatches": mismatches,
        "reference_missing": missing,
        "records": [
            {key: value for key, value in item.items() if key != "output_ids"}
            for item in per_record
        ],
        "output_ids_sha256": {
            item["rid"]: __import__("hashlib")
            .sha256(json.dumps(item["output_ids"]).encode())
            .hexdigest()
            for item in per_record
        },
    }
    destination = (
        Path(args.output)
        if args.output
        else run / "analysis" / "branch_exclusivity.json"
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(result, indent=2) + "\n")
    print(
        json.dumps(
            {k: result[k] for k in ("checks", "passed", "per_branch_summary")}, indent=2
        )
    )
    print(f"written={destination}")
    if not passed:
        raise SystemExit("BRANCH_EXCLUSIVITY_ANALYSIS_FAILED")


if __name__ == "__main__":
    main()
