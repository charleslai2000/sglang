#!/usr/bin/env python3
"""Focused tests for the launcher serving-profile firewall (check 4).

Release-governance + owner ruling "Option A" (v1.2.2 production candidate):
  * the intended v1.2.2 profile PASSES the audit
    (bind 192.168.20.250, `--served-model-name qwen35-9b-local`, AUTH OFF,
    plus the measured 128K/C8 profile flags);
  * the installed v1.2.2 launcher, when present, PASSES the audit;
  * ANY other bind host FAILS the audit (fail closed: 3.1.2.4 / 0.0.0.0 /
    127.0.0.1 / 10.0.0.1, and a missing `--host`);
  * ANY other `--served-model-name` value FAILS the audit (fail closed);
  * a launcher with NO `--served-model-name` FAILS the audit.  Intended design
    (audit_launcher.py check 4b): exactly ONE approved value is REQUIRED;
    missing is a hard failure, not an implicit default;
  * duplicate `--served-model-name` FAILS ("exactly one is allowed");
  * `--api-key` is STILL rejected (FORBIDDEN_SERVING_TOKENS unchanged);
  * NO blanket rule: the bind-host and served-model-name allowlists are exact,
    an unknown serving flag and an unapproved value drift still FAIL, and the
    v1.1 reference launcher does not pass the new firewall.

Model-aware launcher profiles (M2-TOOLING-AUDIT-PROFILE-20260918 / design D3):
  * the OLD (pre-change, no-HiCache) installed M2 launcher FAILS the M2 profile;
  * a launcher with an injected `--hicache-storage-backend` FAILS closed;
  * the NEW M2 launcher (D1 HiCache trio) PASSES the M2 profile, by explicit
    `--profile` and by auto-selection from `--identity`;
  * a changed `--hicache-size` value FAILS, an unknown profile FAILS, and the
    installed M1 launcher PASSES the M1 profile (`0.0.0.0`, no
    `--served-model-name`, extent L3 args preserved).

The positive case renders the repository template exactly like
``bin/launcher-repin.sh`` renders it, into a scratch file under /tmp/opencode;
the real audit functions are then called on real files.  Nothing under /opt is
written and no server or GPU is used.

CPU-only; no GPU, no server.

Run:  python3 3090-dev/tools/freeze/pysrc/test_audit_launcher.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import audit_launcher as A  # noqa: E402

PYSRC = Path(__file__).resolve().parent
TEMPLATE = PYSRC.parent / "templates" / "launch.sh.tmpl"
REF_LAUNCHER = Path("/opt/sglang/local-prod-v1.1-candidate/launcher/launch.sh")
V122_LAUNCHER = Path("/opt/sglang/local-prod-v1.2.2-candidate/launcher/launch.sh")

V122_TREE = "/opt/sglang/local-prod-v1.2.2-candidate"
V122_IDENTITY = "LOCAL-PROD-v1.2.2"
V122_STREAM = "0" * 64  # substitution value; the audit compares it only if asked

# Model-aware M1/M2 installed launchers (design D3).  Read-only fixtures.
M1_LAUNCHER = Path("/opt/sglang/local-prod-v1.2.1-candidate/launcher/launch.sh")
M2_LAUNCHER = Path("/opt/sglang/local-prod-v1.2.1-candidate-M2/launcher/launch.sh")
M1_TREE = "/opt/sglang/local-prod-v1.2.1-candidate"
M1_IDENTITY = "LOCAL-PROD-v1.2.1"
M2_TREE = "/opt/sglang/local-prod-v1.2.1-candidate-M2"
M2_IDENTITY = "LOCAL-PROD-v1.2.1-M2"

SCRATCH = Path("/tmp/opencode/v122-toolchain-audit-tests")

_passed = 0
_failed = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"[PASS] {name}")
    else:
        _failed += 1
        print(f"[FAIL] {name} :: {detail}")


def strip_to_flags(text: str) -> list[str]:
    return A.serving_flags(A.strip_code(text)) or []


def render_v122() -> str:
    """Substitute the template tokens the way bin/launcher-repin.sh does."""
    text = TEMPLATE.read_text()
    for token, value in (
        ("@@TREE@@", V122_TREE),
        ("@@IDENTITY@@", V122_IDENTITY),
        ("@@TREE_NAME@@", V122_TREE.rsplit("/", 1)[-1]),
        ("@@SRC_STREAM_SHA256@@", V122_STREAM),
    ):
        text = text.replace(token, value)
    leftovers = [ln for ln in text.splitlines() if "@@" in ln]
    if leftovers:
        raise SystemExit(f"render left unsubstituted tokens: {leftovers}")
    return text


def expect_fail(name: str, baseline: str, mutant: str, reason_substr: str) -> None:
    check(f"mutation_applied::{name}", mutant != baseline)
    SCRATCH.mkdir(parents=True, exist_ok=True)
    p = SCRATCH / f"{name}.sh"
    p.write_text(mutant)
    rep = A.audit(p, V122_TREE, V122_IDENTITY,
                  expect_stream=V122_STREAM, ref_launcher=REF_LAUNCHER)
    check(f"{name}_FAILS", not rep["ok"],
          f"audit unexpectedly passed {name}")
    check(f"{name}_reason_is_specific",
          any(reason_substr in f for f in rep["failures"]),
          f"no failure matching {reason_substr!r}: failures={rep['failures']}")


def main() -> int:
    if not TEMPLATE.is_file():
        print(f"SKIP: launcher template not present: {TEMPLATE}", file=sys.stderr)
        return 2
    if not REF_LAUNCHER.is_file():
        print(f"SKIP: reference launcher not present: {REF_LAUNCHER}", file=sys.stderr)
        return 2

    rendered = render_v122()

    # --- 1. the intended v1.2.2 profile must pass -------------------------
    SCRATCH.mkdir(parents=True, exist_ok=True)
    v122_rendered = SCRATCH / "v122_rendered.sh"
    v122_rendered.write_text(rendered)
    report = A.audit(v122_rendered, V122_TREE, V122_IDENTITY,
                     expect_stream=V122_STREAM, ref_launcher=REF_LAUNCHER)
    check("v122_rendered_profile_passes", report["ok"],
          f"failures={report.get('failures')}")

    flags = strip_to_flags(rendered)
    check("v122_bind_host_present", "192.168.20.250" in flags)
    check("v122_served_model_present",
          "--served-model-name" in flags and "qwen35-9b-local" in flags)
    check("v122_audit_reports_approved_host",
          report["details"].get("bind_host_approved") is True,
          f"details={report['details'].get('bind_host_approved')}")
    check("v122_audit_reports_single_approved_model",
          report["details"].get("served_model_names") == ["qwen35-9b-local"],
          f"details={report['details'].get('served_model_names')}")
    for tok in ("--context-length", "131072", "--max-running-requests", "8",
                "--max-mamba-cache-size", "48", "--max-total-tokens", "524288"):
        check(f"v122_profile_token_present::{tok}", tok in flags)
    check("v122_no_api_key_token", "--api-key" not in flags)

    # --- 2. the INSTALLED v1.2.2 launcher (when present) must pass --------
    if V122_LAUNCHER.is_file():
        rep_inst = A.audit(V122_LAUNCHER, V122_TREE, V122_IDENTITY,
                           expect_stream=None, ref_launcher=REF_LAUNCHER)
        check("installed_v122_launcher_passes", rep_inst["ok"],
              f"failures={rep_inst['failures']}")
        flags_inst = strip_to_flags(V122_LAUNCHER.read_text())
        check("installed_v122_has_approved_host", "192.168.20.250" in flags_inst)
        check("installed_v122_has_approved_model", "qwen35-9b-local" in flags_inst)
    else:
        print(f"[INFO] installed v1.2.2 launcher not present ({V122_LAUNCHER}); "
              f"positive case used the rendered template profile")

    # --- 3. unknown/other bind host values FAIL (fail closed) -------------
    for host in ("3.1.2.4", "0.0.0.0", "127.0.0.1", "10.0.0.1"):
        expect_fail(
            f"unknown_bind_host_{host.replace('.', '_')}",
            rendered,
            rendered.replace("--host 192.168.20.250", f"--host {host}", 1),
            "bind host must be one of the approved v1.2 hosts",
        )

    # a missing --host flag must also fail
    expect_fail(
        "missing_bind_host",
        rendered,
        re.sub(r"--host +[^\s]+ +", "", rendered, count=1),
        "no --host flag found in launcher",
    )

    # --- 4. unknown --served-model-name values FAIL (fail closed) ---------
    for model in ("other-model", "qwen35-9b-w4a16", "Qwen35-9B-Local"):
        expect_fail(
            f"unknown_served_model_{model.replace('.', '_').replace('-', '_')}",
            rendered,
            rendered.replace(
                "--served-model-name qwen35-9b-local",
                f"--served-model-name {model}", 1),
            "--served-model-name must be one of",
        )

    # --- 5. NO --served-model-name FAILS (fail closed by design) ----------
    # audit_launcher.py check 4b intends exactly one approved value to be
    # REQUIRED, so absence must be a hard failure (no implicit default).
    expect_fail(
        "no_served_model_name",
        rendered,
        re.sub(r"[ \t]*--served-model-name +[^\n]+\n", "", rendered),
        "missing (exactly one approved value is required)",
    )

    # --- 6. duplicate --served-model-name FAILS (exactly one) -------------
    expect_fail(
        "duplicate_served_model_name",
        rendered,
        rendered.replace(
            "  --served-model-name qwen35-9b-local\n",
            "  --served-model-name qwen35-9b-local\n"
            "  --served-model-name qwen35-9b-local\n", 1),
        "exactly one is allowed",
    )

    # --- 7. --api-key is STILL rejected (AUTH OFF) ------------------------
    check("forbidden_serving_tokens_unchanged",
          A.FORBIDDEN_SERVING_TOKENS == frozenset({"--api-key"}),
          f"FORBIDDEN_SERVING_TOKENS={sorted(A.FORBIDDEN_SERVING_TOKENS)!r}")
    expect_fail(
        "api_key_injected",
        rendered,
        rendered.replace("  --kv-cache-dtype fp8_e4m3",
                         "  --api-key SECRET123\n  --kv-cache-dtype fp8_e4m3", 1),
        "forbidden serving token",
    )

    # --- 8. no blanket rule: exact allowlists + unapproved deltas still fail
    check("bind_host_allowlist_exact",
          set(A.PRODUCTION_BIND_HOST_APPROVED.values()) == {"192.168.20.250"},
          f"values={sorted(A.PRODUCTION_BIND_HOST_APPROVED.values())!r}")
    check("served_model_allowlist_exact",
          set(A.PRODUCTION_SERVED_MODEL_NAME_APPROVED) == {"qwen35-9b-local"},
          f"values={sorted(A.PRODUCTION_SERVED_MODEL_NAME_APPROVED)!r}")
    expect_fail(
        "unknown_serving_flag_injected",
        rendered,
        rendered.replace("  --kv-cache-dtype fp8_e4m3",
                         "  --totally-unknown-serving-flag 7\n"
                         "  --kv-cache-dtype fp8_e4m3", 1),
        "--totally-unknown-serving-flag",
    )
    expect_fail(
        "unapproved_value_drift",
        rendered,
        rendered.replace("--max-running-requests 8",
                         "--max-running-requests 11", 1),
        "unapproved_new=['11']",
    )

    # the v1.1 reference launcher must NOT pass the new firewall
    rep_ref = A.audit(REF_LAUNCHER, "/opt/sglang/local-prod-v1.1-candidate",
                      "LOCAL-PROD-v1.1", expect_stream=None,
                      ref_launcher=REF_LAUNCHER)
    check("v11_reference_rejected_by_new_firewall", not rep_ref["ok"],
          "v1.1 reference unexpectedly passed the v1.2.x firewall")

    # --- 9. model-aware LAUNCHER_PROFILES (design D3): M1 + M2 ------------
    # The installed M2 launcher (read-only) is the pre-change ("old") fixture:
    # it has no HiCache trio.  The NEW M2 text is derived deterministically by
    # injecting the D1 trio, so this test does not depend on a later re-freeze.
    if not M2_LAUNCHER.is_file():
        print(f"SKIP M2 profile tests: installed launcher not present: "
              f"{M2_LAUNCHER}", file=sys.stderr)
    else:
        trio_lines = (
            "  --enable-hierarchical-cache\n"
            "  --hicache-write-policy write_back\n"
            "  --hicache-size 32\n"
            "  --hicache-host-memory-mode cache\n"
        )
        old_m2 = M2_LAUNCHER.read_text()
        for _line in trio_lines.splitlines(keepends=True):
            old_m2 = old_m2.replace(_line, "")
        new_m2 = old_m2.replace(
            "  --mamba-ssm-dtype float32\n",
            "  --mamba-ssm-dtype float32\n" + trio_lines, 1)

        # (a) the OLD (pre-change) M2 launcher FAILS the audit.
        #     NB: the raw text still contains the HiCache token inside the
        #     GATE 3/3 forbidden-argv loop, so assert against the SERVING flags.
        old_flags = strip_to_flags(old_m2)
        check("m2_old_has_no_hicache_serving_flag",
              "--enable-hierarchical-cache" not in old_flags
              and "--hicache-size" not in old_flags,
              f"old serving flags unexpectedly carry HiCache: {old_flags}")
        old_p = SCRATCH / "m2_old.sh"
        old_p.write_text(old_m2)
        rep_old = A.audit(old_p, M2_TREE, M2_IDENTITY, expect_stream=None,
                          ref_launcher=REF_LAUNCHER, profile=M2_IDENTITY)
        check("m2_old_launcher_FAILS", not rep_old["ok"],
              f"old M2 launcher unexpectedly passed: {rep_old['failures']}")
        check("m2_old_reason_missing_required",
              any("missing_required_tokens" in f for f in rep_old["failures"]),
              f"no missing-required reason: {rep_old['failures']}")
        check("m2_old_reason_unapproved_dropped",
              any("unapproved_dropped" in f for f in rep_old["failures"]),
              f"no unapproved-dropped reason: {rep_old['failures']}")

        # (b) an injected --hicache-storage-backend FAILS closed.
        injected_m2 = new_m2.replace(
            "  --mamba-ssm-dtype float32\n",
            "  --mamba-ssm-dtype float32\n  --hicache-storage-backend extent\n", 1)
        check("m2_injection_applied",
              "--hicache-storage-backend" in injected_m2)
        inj_p = SCRATCH / "m2_injected_storage_backend.sh"
        inj_p.write_text(injected_m2)
        rep_inj = A.audit(inj_p, M2_TREE, M2_IDENTITY, expect_stream=None,
                          ref_launcher=REF_LAUNCHER, profile=M2_IDENTITY)
        check("m2_injected_storage_backend_FAILS", not rep_inj["ok"],
              "injected --hicache-storage-backend unexpectedly passed")
        check("m2_injected_storage_backend_reason_is_specific",
              any("profile-forbidden" in f for f in rep_inj["failures"]),
              f"no profile-forbidden reason: {rep_inj['failures']}")

        # (c) the NEW M2 launcher PASSES (explicit profile and auto-select).
        check("m2_new_has_hicache",
              all(t in new_m2 for t in (
                  "--enable-hierarchical-cache", "--hicache-write-policy",
                  "write_back", "--hicache-size", "32")))
        new_p = SCRATCH / "m2_new.sh"
        new_p.write_text(new_m2)
        rep_new = A.audit(new_p, M2_TREE, M2_IDENTITY, expect_stream=None,
                          ref_launcher=REF_LAUNCHER, profile=M2_IDENTITY)
        check("m2_new_launcher_PASSES", rep_new["ok"],
              f"failures={rep_new['failures']}")
        check("m2_audit_reports_approved_host",
              rep_new["details"].get("bind_host_approved") is True)
        check("m2_audit_reports_no_served_model_name",
              rep_new["details"].get("served_model_names") == []
              and rep_new["details"].get("served_model_name_required") is False)
        rep_auto = A.audit(new_p, M2_TREE, M2_IDENTITY, expect_stream=None,
                           ref_launcher=REF_LAUNCHER, profile=None)
        check("m2_auto_profile_passes", rep_auto["ok"],
              f"auto-selected profile failures={rep_auto['failures']}")
        check("m2_auto_profile_selected",
              rep_auto["details"].get("profile") == M2_IDENTITY,
              f"profile={rep_auto['details'].get('profile')}")

        # fail-closed: a changed HiCache value is NOT accepted.
        bad_value = new_m2.replace("--hicache-size 32", "--hicache-size 64", 1)
        check("m2_bad_value_mutation_applied", bad_value != new_m2)
        bad_p = SCRATCH / "m2_bad_hicache_size.sh"
        bad_p.write_text(bad_value)
        rep_bad = A.audit(bad_p, M2_TREE, M2_IDENTITY, expect_stream=None,
                          ref_launcher=REF_LAUNCHER, profile=M2_IDENTITY)
        check("m2_bad_hicache_size_FAILS", not rep_bad["ok"],
              "changed --hicache-size unexpectedly passed")

        # fail-closed: an unknown profile name is rejected outright.
        rep_unknown = A.audit(new_p, M2_TREE, M2_IDENTITY, expect_stream=None,
                              ref_launcher=REF_LAUNCHER, profile="NOT-A-PROFILE")
        check("unknown_profile_FAILS", not rep_unknown["ok"],
              "unknown profile unexpectedly passed")
        check("unknown_profile_reason_is_specific",
              any("unknown launcher profile" in f
                  for f in rep_unknown["failures"]),
              f"failures={rep_unknown['failures']}")

        # profile table sanity: exact hosts / optional served-model-name.
        check("m2_profile_hosts_include_0000",
              "0.0.0.0" in A.M2_PROFILE.approved_bind_hosts
              and "192.168.20.250" in A.M2_PROFILE.approved_bind_hosts,
              f"hosts={sorted(A.M2_PROFILE.approved_bind_hosts)!r}")
        check("m1_profile_hosts_include_0000",
              "0.0.0.0" in A.M1_PROFILE.approved_bind_hosts
              and "192.168.20.250" in A.M1_PROFILE.approved_bind_hosts,
              f"hosts={sorted(A.M1_PROFILE.approved_bind_hosts)!r}")
        check("m2_profile_served_model_optional",
              A.M2_PROFILE.served_model_name_required is False)
        check("m1_profile_served_model_optional",
              A.M1_PROFILE.served_model_name_required is False)

    # --- 10. installed M1 launcher passes its profile (read-only) ---------
    if not M1_LAUNCHER.is_file():
        print(f"SKIP M1 profile test: installed launcher not present: "
              f"{M1_LAUNCHER}", file=sys.stderr)
    else:
        rep_m1 = A.audit(M1_LAUNCHER, M1_TREE, M1_IDENTITY, expect_stream=None,
                         ref_launcher=REF_LAUNCHER, profile=M1_IDENTITY)
        check("installed_m1_launcher_passes_profile", rep_m1["ok"],
              f"failures={rep_m1['failures']}")
        check("installed_m1_bind_host_is_0000",
              rep_m1["details"].get("bind_host") == "0.0.0.0",
              f"bind_host={rep_m1['details'].get('bind_host')!r}")
        check("installed_m1_has_no_served_model_name",
              rep_m1["details"].get("served_model_names") == [],
              f"served_names={rep_m1['details'].get('served_model_names')!r}")

    print(f"\n==== test_audit_launcher: {_passed} passed, {_failed} failed ====")
    return 1 if _failed else 0


if __name__ == "__main__":
    sys.exit(main())
