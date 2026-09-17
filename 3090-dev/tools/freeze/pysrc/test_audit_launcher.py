#!/usr/bin/env python3
"""Focused tests for the launcher serving-profile firewall (check 4).

Required by the release-governance adjudication:
  * the CURRENT production launcher PASSES the audit;
  * ONE unknown serving flag FAILS it.

CPU-only; no GPU, no server.

Run:  python3 3090-dev/tools/freeze/pysrc/test_audit_launcher.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import audit_launcher as A  # noqa: E402

PROD_LAUNCHER = Path("/opt/sglang/local-prod-v1.2-candidate/launcher/launch.sh")
REF_LAUNCHER = Path("/opt/sglang/local-prod-v1.1-candidate/launcher/launch.sh")

PROD_TREE = "/opt/sglang/local-prod-v1.2-candidate"
PROD_IDENTITY = "LOCAL-PROD-v1.2"

_passed = 0
_failed = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"[PASS] {name}")
    else:
        _failed += 1
        print(f"[FAIL] {name}  :: {detail}")


def _strip_to_flags(text: str) -> list[str]:
    return A.serving_flags(A.strip_code(text)) or []


def main() -> int:
    if not PROD_LAUNCHER.is_file():
        print(f"SKIP: production launcher not present: {PROD_LAUNCHER}", file=sys.stderr)
        return 2
    if not REF_LAUNCHER.is_file():
        print(f"SKIP: reference launcher not present: {REF_LAUNCHER}", file=sys.stderr)
        return 2

    text = PROD_LAUNCHER.read_text()

    # --- 1. the real production launcher must pass ------------------------
    report = A.audit(
        PROD_LAUNCHER, PROD_TREE, PROD_IDENTITY,
        expect_stream=None, ref_launcher=REF_LAUNCHER,
    )
    check("current_production_launcher_passes", report["ok"],
          f"failures={report.get('failures')}")

    # the declared production profile must actually be present
    flags = _strip_to_flags(text)
    for tok in ("--context-length", "131072", "--max-running-requests", "8",
                "--max-mamba-cache-size", "48", "--max-total-tokens", "524288"):
        check(f"production_profile_token_present::{tok}", tok in flags)

    # AUTH OFF: no api-key token
    check("no_api_key_token", "--api-key" not in flags)

    # --- 2. ONE unknown serving flag must fail ----------------------------
    mutants = {
        "unknown_flag_injected": "--totally-unknown-serving-flag 7",
        "unknown_value_changed": None,  # handled below
        "api_key_injected": "--api-key SECRET123",
    }

    injected = text.replace(
        "  --kv-cache-dtype fp8_e4m3",
        "  --totally-unknown-serving-flag 7\n  --kv-cache-dtype fp8_e4m3",
        1,
    )
    check("mutation_applied::unknown_flag", injected != text)
    mut_path = Path("/tmp/opencode/_audit_mut_unknown.sh")
    mut_path.write_text(injected)
    rep = A.audit(mut_path, PROD_TREE, PROD_IDENTITY,
                  expect_stream=None, ref_launcher=REF_LAUNCHER)
    check("unknown_serving_flag_FAILS", not rep["ok"],
          f"audit unexpectedly passed an injected unknown flag")

    # value drift on an approved flag must also fail
    drifted = text.replace("--max-running-requests 8",
                           "--max-running-requests 11", 1)
    check("mutation_applied::value_drift", drifted != text)
    mut_path2 = Path("/tmp/opencode/_audit_mut_drift.sh")
    mut_path2.write_text(drifted)
    rep2 = A.audit(mut_path2, PROD_TREE, PROD_IDENTITY,
                   expect_stream=None, ref_launcher=REF_LAUNCHER)
    check("unapproved_value_drift_FAILS", not rep2["ok"],
          "audit unexpectedly passed an unapproved value change")

    # api-key injection must fail (AUTH OFF)
    apikey = text.replace("  --kv-cache-dtype fp8_e4m3",
                          "  --api-key SECRET123\n  --kv-cache-dtype fp8_e4m3", 1)
    check("mutation_applied::api_key", apikey != text)
    mut_path3 = Path("/tmp/opencode/_audit_mut_apikey.sh")
    mut_path3.write_text(apikey)
    rep3 = A.audit(mut_path3, PROD_TREE, PROD_IDENTITY,
                   expect_stream=None, ref_launcher=REF_LAUNCHER)
    check("api_key_injection_FAILS", not rep3["ok"],
          "audit unexpectedly passed an injected --api-key")

    print(f"\n==== test_audit_launcher: {_passed} passed, {_failed} failed ====")
    return 1 if _failed else 0


if __name__ == "__main__":
    sys.exit(main())
