#!/usr/bin/env python3
"""
sample_blind_round1.py -- deterministic stratified sampling of the BLIND ROUND-1 corpus.

Owner ruling 1 (R2, 2026-09-16):
  1. start from the official SWE-bench Verified test split
  2. pin an exact dataset revision
  3. remove the 25 contaminated (calibration) instance IDs
  4. deterministic stratified sample by the REMAINING corpus's repo distribution
     (NOT the old contaminated proportions)
  5. fixed random seed
  6. freeze instance ids + base_commit (+ image digest, added later)

Inputs (frozen):
  --instances  JSON list of {instance_id, repo, base_commit} dumped from the pinned
               SWE-bench_Verified test parquet (500 rows).
  --exclusions JSON list of the 25 contaminated instance ids (or the prior manifest).

Output: JSON with the algorithm, seed, per-repo quotas, and the 24 selected cases.

DETERMINISM CONTRACT
  * Allocation: largest-remainder (Hamilton) apportionment of N=24 seats over the
    per-repo counts of the remaining corpus. Repos are processed in ascending
    lexicographic order; ties on remainder are broken by ascending repo name.
  * Selection: a single `random.Random(SEED)` Mersenne-Twister stream. Repos are
    visited in ascending lexicographic order; for each repo the sorted instance-id
    list is shuffled and the first `quota` ids are taken.
  * Python `random` shuffle is stable across CPython 3.10/3.12 (verified by running
    this script on both and diffing the output).
"""

import argparse
import hashlib
import json
import random
import sys
from collections import Counter, OrderedDict


SEED = 20260916
N_SELECT = 24


def largest_remainder(counts: "OrderedDict[str,int]", n_select: int):
    """Hamilton apportionment. Returns (quota_dict, diagnostics)."""
    total = sum(counts.values())
    raw = {r: c * n_select / total for r, c in counts.items()}
    floor = {r: int(raw[r]) for r in counts}
    assigned = sum(floor.values())
    remainder = n_select - assigned
    # deterministic order: remainder desc, then repo name asc
    order = sorted(counts, key=lambda r: (-(raw[r] - floor[r]), r))
    for r in order[:remainder]:
        floor[r] += 1
    diag = {
        "remaining_total": total,
        "raw_share": {r: round(raw[r], 6) for r in counts},
        "floor_sum_before_remainder": assigned,
        "remainder_seats": remainder,
        "remainder_order": order,
    }
    return floor, diag


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--instances", required=True)
    ap.add_argument("--exclusions", required=True,
                    help="JSON list of contaminated instance ids, or a prior corpus-manifest.json")
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--n", type=int, default=N_SELECT)
    args = ap.parse_args()

    with open(args.instances) as f:
        data = json.load(f)
    if isinstance(data, dict) and "instances" in data:
        data = data["instances"]
    universe = {d["instance_id"]: d for d in data}

    with open(args.exclusions) as f:
        ex = json.load(f)
    if isinstance(ex, dict):
        ex = ex.get("dev_exclusion_set", ex).get("instances", [])
    excl = set()
    for e in ex:
        excl.add(e["instance_id"] if isinstance(e, dict) else e)

    remaining = {i: d for i, d in universe.items() if i not in excl}
    by_repo = {}
    for i, d in remaining.items():
        by_repo.setdefault(d["repo"], []).append(i)
    counts = OrderedDict((r, len(v)) for r, v in sorted(by_repo.items()))

    quota, diag = largest_remainder(counts, args.n)

    rng = random.Random(args.seed)
    selected = []
    for repo in sorted(by_repo):
        ids = sorted(by_repo[repo])
        rng.shuffle(ids)
        selected.extend((i, repo) for i in ids[:quota[repo]])
    selected.sort(key=lambda t: t[1])  # keep readable grouping; order is not semantic

    out = {
        "dataset": "SWE-bench/SWE-bench_Verified",
        "revision": "78f471bf655a3137b2e8a75af1501690ec009ec3",
        "split": "test",
        "universe_size": len(universe),
        "exclusions_count": len(excl),
        "exclusions": sorted(excl),
        "remaining_size": len(remaining),
        "n_select": args.n,
        "seed": args.seed,
        "algorithm": {
            "name": "deterministic-stratified-largest-remainder",
            "allocation": "Hamilton largest-remainder over remaining-corpus repo counts; ties by repo name",
            "selection": "single random.Random(seed) stream, repos ascending, sorted ids shuffled, take quota",
            "python": sys.version,
        },
        "repo_quotas": dict(quota),
        "remaining_repo_counts": dict(counts),
        "allocation_diagnostics": diag,
        "selected_count": len(selected),
        "selected": [
            {
                "instance_id": i,
                "repo": r,
                "base_commit": remaining[i]["base_commit"],
            }
            for i, r in selected
        ],
    }
    with open(args.out, "w") as f:
        json.dump(out, f, indent=2)
        f.write("\n")

    print(f"universe={len(universe)} exclusions={len(excl)} remaining={len(remaining)} selected={len(selected)}")
    print("repo_quotas:", json.dumps(dict(quota)))
    print("selection_sha256:", hashlib.sha256(
        ",".join(sorted(i for i, _ in selected)).encode()).hexdigest())
    for i, r in selected:
        print(f"  {i}  {remaining[i]['base_commit']}")


if __name__ == "__main__":
    main()
