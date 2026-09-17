#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Run every independent oracle and aggregate the review verdict.

Expected outcomes:
  --mode frozen-control : the relocation-dependent oracles MUST report FAIL
                          (the frozen allocator recycles live victim slots).
                          A frozen-control PASS on such an oracle means the
                          oracle is vacuous and must be re-examined.
  --mode candidate      : every oracle MUST report PASS, or INVALID with an
                          explicit un-exercised-window reason.  Any FAIL is a
                          candidate defect; INVALID is reported separately.

Exit codes: 0 all expected; 1 unexpected oracle outcome(s); 2 INVALID present
under --mode candidate; 3 harness error.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))

ORACLES = [
    "oracle_payload_bytes.py",
    "oracle_generation.py",
    "oracle_live_dead.py",
    "oracle_no_capacity.py",
    "oracle_crash_matrix.py",
    "oracle_restart_replay.py",
]

# oracles whose safety checks must FAIL on the frozen tree
FROZEN_EXPECT_FAIL = set(ORACLES)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tree", default="/opt/sglang/local-prod-v1.1-candidate")
    parser.add_argument("--mode", choices=["candidate", "frozen-control"], required=True)
    parser.add_argument("--outdir", default=os.path.join(os.path.dirname(_HERE), "results"))
    parser.add_argument("--python", default=sys.executable)
    args = parser.parse_args(argv)
    os.makedirs(args.outdir, exist_ok=True)

    env = dict(os.environ)
    env.setdefault("CUDA_VISIBLE_DEVICES", "999")

    rows = []
    overall = 0
    for name in ORACLES:
        out = os.path.join(args.outdir, f"{args.mode}-{name.replace('.py', '')}.json")
        cmd = [
            args.python,
            os.path.join(_HERE, name),
            "--tree",
            args.tree,
            "--mode",
            args.mode,
            "--out",
            out,
        ]
        proc = subprocess.run(cmd, env=env, capture_output=True, text=True)
        status = "ERROR"
        failed = []
        invalid = []
        if os.path.exists(out):
            with open(out) as fh:
                payload = json.load(fh)
            status = payload.get("status", "ERROR")
            failed = payload.get("failed_checks", [])
            invalid = payload.get("invalid_checks", [])
        row = {
            "oracle": name,
            "rc": proc.returncode,
            "status": status,
            "failed_checks": failed,
            "invalid_checks": invalid,
            "result_json": out,
        }
        rows.append(row)

        if args.mode == "frozen-control":
            # Detect vacuous oracles: a relocation oracle must not PASS.
            if status == "PASS" and name in FROZEN_EXPECT_FAIL:
                row["unexpected"] = "PASS on frozen control"
                overall = 1
            elif status == "ERROR":
                overall = 3
        else:
            if status == "FAIL":
                overall = 1
            elif status == "INVALID" and overall == 0:
                overall = 2
            elif status == "ERROR":
                overall = 3

    summary = {
        "mode": args.mode,
        "tree": os.path.abspath(args.tree),
        "overall_exit": overall,
        "rows": rows,
    }
    summary_path = os.path.join(args.outdir, f"{args.mode}-SUMMARY.json")
    with open(summary_path, "w") as fh:
        json.dump(summary, fh, indent=2, sort_keys=True)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return overall


if __name__ == "__main__":
    sys.exit(main())
