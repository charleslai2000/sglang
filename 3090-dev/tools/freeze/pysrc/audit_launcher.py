#!/usr/bin/env python3
"""Static audit of a rendered launcher for the LOCAL-PROD identity line.

Purpose: make the v1 -> v1.1 failure mode (a launcher that is a byte copy of an
older tree's launcher and therefore silently binds the OLD tree) impossible.

Checks
  1. every /opt/sglang/<tree> literal in the file resolves to exactly the
     intended tree (component-boundary aware: /opt/sglang/local-prod-v1.1 is NOT
     accepted as a prefix of the intended /opt/sglang/local-prod-v1.1.2-candidate)
  2. every LOCAL-PROD-* identity string in the file equals the intended identity
  3. EXPECTED_SRC_STREAM_SHA256 equals the computed stream digest
  4. the serving-flag token list after `sglang.launch_server` is exactly the
     reference (v1.1) token list, with approved deltas for the v1.2 profile,
     the approved v1.2.x bind host and exactly one approved --served-model-name
  5. the ARGS array + dry-run guard exist, the guard precedes mkdir/exec, and
     exec uses "${ARGS[@]}" (so the dry-run argv cannot diverge from the exec)
  6. the run-namespace guard refuses reserved/shared ids before anything runs

Exit 0 = all checks pass, 1 = audit failure, 2 = usage/IO error.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

TREE_RE = re.compile(r"/opt/sglang/[A-Za-z0-9._\-]+")
IDENT_RE = re.compile(r"LOCAL-PROD-[A-Za-z0-9._\-]+")
STREAM_RE = re.compile(r'^EXPECTED_SRC_STREAM_SHA256="([0-9a-f]{64})"$', re.MULTILINE)

# ---------------------------------------------------------------------------
# Serving-profile firewall (check 4).
#
# The launcher's serving flags are compared against the v1.1 reference launcher
# so that an accidental change (wrong context size, wrong backend, a silently
# dropped flag, an injected flag) cannot reach a frozen production candidate.
#
# The v1.2 production profile is an INTENTIONAL, MEASURED delta from v1.1.  It
# is declared here as the smallest possible explicit exception: the exact
# production-required flag tokens, and the one reference value they replace.
# Anything else -- any flag or value that is neither in the reference nor in
# this exact set -- remains a hard failure.
#
# Source of truth for these values: the measured 128K / C8 profile served by
# the frozen launcher (3090-dev/deploy/conf/provider.env, commit 116afefbbe):
#   context-length 131072 | max-running-requests 8 | max-mamba-cache-size 48
#   max-total-tokens 524288 (replaces the v1.1 value 65536)
# This list is NOT a whitelist for convenience.  Growing it changes the frozen
# serving profile and is a reviewed production decision, not a tooling tweak.
PRODUCTION_REQUIRED_SERVING_TOKENS: frozenset[str] = frozenset({
    "--context-length", "131072",
    "--max-running-requests", "8",
    "--max-mamba-cache-size", "48",
})
PRODUCTION_REQUIRED_SERVING_REPLACEMENTS: dict[str, str] = {
    "65536": "524288",
}
# AUTH is OFF for this private LAN deployment: the launch path must NOT carry
# an API key.  Its presence is a security regression, not a profile choice.
# Recorded ruling: .memory/phase2-hicache-design/HANDOFF-20260917-PRODUCTION-PRIORITY.md
# section 5 ("AUTH"): private-LAN deployment does not require an API key, and
# the launch path must not pass --api-key.
FORBIDDEN_SERVING_TOKENS: frozenset[str] = frozenset({"--api-key"})

# Approved bind hosts (explicit allowlist per owner ruling, match allowed host -> replacement value):
# - The v1.1 reference hard-codes 127.0.0.1; v1.2.x production uses 192.168.20.250.
# This replacement is declared to allow the v1.1 -> v1.2 bind host drift while keeping
# --api-key forbidden and enforcing the exact approved replacement.
PRODUCTION_BIND_HOST_APPROVED: dict[str, str] = {
    "127.0.0.1": "192.168.20.250",
}

# Approved served-model-name values (explicit allowlist per owner ruling):
# - The frozen prod service advertises qwen35-9b-local.  This is the only
#   allowed value for --served-model-name in any v1.2.x candidate.
#   Any other value (including the model path qwen35-9b-w4a16) FAILS the audit.
PRODUCTION_SERVED_MODEL_NAME_APPROVED: frozenset[str] = frozenset({
    "qwen35-9b-local",
})


def strip_code(text: str) -> list[str]:
    """Return code tokens with comments, backslash continuations and quotes
    normalised away enough for structural comparison."""
    tokens: list[str] = []
    for raw in text.splitlines():
        line = raw.split("#", 1)[0] if raw.lstrip().startswith("#") else raw
        line = line.replace("\\", " ")
        # drop inline comments that follow code (none expected, but be safe)
        if line.lstrip().startswith("#"):
            continue
        tokens.extend(line.split())
    return tokens


def serving_flags(tokens: list[str]) -> list[str] | None:
    try:
        idx = tokens.index("sglang.launch_server")
    except ValueError:
        return None
    out: list[str] = []
    for tok in tokens[idx + 1 :]:
        if tok == ")":
            break
        if tok == "exec" or tok.endswith(")") and "(" in tok:
            break
        out.append(tok)
    return out


def tree_roots(text: str) -> list[str]:
    return sorted(set(TREE_RE.findall(text)))


def audit(
    launcher: Path,
    tree: str,
    identity: str,
    expect_stream: str | None,
    ref_launcher: Path | None,
) -> dict:
    text = launcher.read_text()
    failures: list[str] = []
    details: dict = {"launcher": str(launcher), "sha256_note": "hash computed by caller"}

    # 1. path literals.  Any /opt/sglang/<tree> literal must be exactly the
    # intended tree; if the intended tree lives elsewhere (throwaway dry-run
    # tree), then *any* such literal is a foreign reference.
    roots = tree_roots(text)
    details["tree_roots_referenced"] = roots
    bad_roots = [r for r in roots if r.rstrip("/") != tree.rstrip("/")]
    if bad_roots:
        failures.append(f"foreign tree literal(s) referenced: {bad_roots}")
    if tree.rstrip("/") not in text:
        failures.append(f"intended tree never referenced by the launcher: {tree}")

    # explicit legacy-tree guard (component boundary safe because roots are exact)
    for legacy in ("/opt/sglang/local-prod-v1", "/opt/sglang/local-prod-v1.1-candidate"):
        if legacy in roots and legacy != tree.rstrip("/"):
            failures.append(f"legacy tree literal present: {legacy}")

    # 2. identity strings
    idents = sorted(set(IDENT_RE.findall(text)))
    details["identity_strings"] = idents
    bad_idents = [i for i in idents if i != identity]
    if bad_idents:
        failures.append(f"foreign identity string(s): {bad_idents}")
    if identity not in idents:
        failures.append(f"intended identity {identity!r} not branded in the launcher")

    # 3. stream digest
    m = STREAM_RE.search(text)
    embedded = m.group(1) if m else None
    details["embedded_src_stream_sha256"] = embedded
    if embedded is None:
        failures.append("EXPECTED_SRC_STREAM_SHA256 not found")
    elif expect_stream and embedded != expect_stream:
        failures.append(
            f"embedded stream digest {embedded} != computed {expect_stream}"
        )

    # 4. serving-profile firewall vs the v1.1 reference launcher.  The v1.2.x
    # profile is an INTENTIONAL declared delta: the measured profile tokens, the
    # approved bind host, and exactly one approved --served-model-name.  Any
    # other flag/value, or a silently dropped reference flag, fails closed.
    tokens = strip_code(text)
    flags = serving_flags(tokens)
    details["serving_flags"] = flags
    _sub = dict(PRODUCTION_REQUIRED_SERVING_REPLACEMENTS)
    # approved v1.1 -> v1.2.x bind host drift (owner ruling Option A)
    _sub.update(PRODUCTION_BIND_HOST_APPROVED)
    _allowed_new = (
        set(PRODUCTION_REQUIRED_SERVING_TOKENS)
        | set(_sub.values())
        | {"--served-model-name"}
        | set(PRODUCTION_SERVED_MODEL_NAME_APPROVED)
    )
    if flags is None:
        failures.append("no sglang.launch_server invocation found")
    elif ref_launcher is not None:
        ref_flags = serving_flags(strip_code(ref_launcher.read_text()))
        details["reference_serving_flags"] = ref_flags
        if ref_flags is None:
            failures.append(f"reference launcher {ref_launcher} has no flags to compare")
        elif flags != ref_flags:
            only_new = [t for t in flags if t not in ref_flags]
            only_ref = [t for t in ref_flags if t not in flags]
            unapproved_new = [t for t in only_new if t not in _allowed_new]
            unapproved_dropped = [t for t in only_ref if t not in _sub]
            missing_replacements = sorted(
                new for old, new in _sub.items()
                if old in only_ref and new not in flags
            )
            details["serving_delta_allowance"] = {
                "declared_tokens": sorted(_allowed_new),
                "declared_replacements": _sub,
                "unapproved_new": unapproved_new,
                "unapproved_dropped": unapproved_dropped,
                "missing_replacements": missing_replacements,
            }
            if unapproved_new or unapproved_dropped or missing_replacements:
                failures.append(
                    "serving flags differ from reference beyond the exact "
                    f"production profile delta: only-in-new={only_new} "
                    f"only-in-reference={only_ref} "
                    f"unapproved_new={unapproved_new} "
                    f"unapproved_dropped={unapproved_dropped} "
                    f"missing_replacements={missing_replacements}"
                )

    # 4a. bind host validation (v1.1 reference -> v1.2 approved replacement).
    # Fail closed: --host MUST appear exactly once and its value MUST be the
    # approved v1.2 production host; unknown/other values are hard failures.
    host_values = [
        tokens[i + 1] if i + 1 < len(tokens) else ""
        for i, tok in enumerate(tokens)
        if tok == "--host"
    ]
    approved_hosts = sorted(set(PRODUCTION_BIND_HOST_APPROVED.values()))
    if not host_values:
        failures.append("no --host flag found in launcher")
    else:
        if len(host_values) > 1:
            failures.append(
                f"--host appears {len(host_values)} times; exactly one is allowed"
            )
        for _h in host_values:
            if _h not in approved_hosts:
                failures.append(
                    f"bind host must be one of the approved v1.2 hosts "
                    f"{approved_hosts!r}, found {_h!r}"
                )
    details["bind_host"] = host_values[0] if host_values else None
    details["bind_host_approved"] = bool(
        len(host_values) == 1 and host_values[0] in approved_hosts
    )

    # 4b. served-model-name validation (owner ruling Option A: exactly one
    # approved value is REQUIRED; missing or unknown values fail closed).
    served_names: list[str] = []
    for i, tok in enumerate(tokens):
        if tok == "--served-model-name":
            _served_name = tokens[i + 1] if i + 1 < len(tokens) else ""
            served_names.append(_served_name)
            if _served_name not in PRODUCTION_SERVED_MODEL_NAME_APPROVED:
                failures.append(
                    f"--served-model-name must be one of "
                    f"{sorted(PRODUCTION_SERVED_MODEL_NAME_APPROVED)!r}, "
                    f"found {_served_name!r}"
                )
    if not served_names:
        failures.append("--served-model-name missing (exactly one approved value is required)")
    elif len(served_names) > 1:
        failures.append(
            f"--served-model-name appears {len(served_names)} times; exactly one is allowed"
        )
    details["served_model_names"] = served_names

    # 5. ARGS array + dry-run guard ordering
    has_args = re.search(r"^ARGS=\($", text, re.MULTILINE) is not None

    # 5b. AUTH is OFF for this deployment: no API-key token may appear in the
    # serving flags.  A key on the launch path is a security regression.
    forbidden = sorted(t for t in (flags or []) if t in FORBIDDEN_SERVING_TOKENS)
    details["forbidden_serving_tokens_present"] = forbidden
    if forbidden:
        failures.append(
            f"forbidden serving token(s) present (AUTH must be OFF): {forbidden}"
        )

    guard_m = re.search(r'^if \[ "\$\{SGLANG_LAUNCH_DRY_RUN:-0\}" = "1" \]; then$', text, re.MULTILINE)
    mkdir_m = re.search(r"^mkdir -p ", text, re.MULTILINE)
    exec_m = re.search(r'^exec "\$PY" -u "\$\{ARGS\[@\]\}"$', text, re.MULTILINE)
    dry_prints_argv = re.search(r'printf \' %q\' "\$PY" -u "\$\{ARGS\[@\]\}"', text) is not None
    details["has_args_array"] = has_args
    details["has_dry_run_guard"] = guard_m is not None
    details["dry_run_prints_exec_argv"] = dry_prints_argv
    details["exec_uses_args_array"] = exec_m is not None
    if not has_args:
        failures.append("ARGS array missing")
    if guard_m is None:
        failures.append("dry-run guard missing")
    if exec_m is None:
        failures.append('exec does not use "${ARGS[@]}"')
    if not dry_prints_argv:
        failures.append("dry-run does not print the exact exec argv")
    if guard_m and mkdir_m and guard_m.start() > mkdir_m.start():
        failures.append("dry-run guard appears AFTER mkdir -p (dry-run would create state)")
    if guard_m and exec_m and guard_m.start() > exec_m.start():
        failures.append("dry-run guard appears AFTER exec")
    if mkdir_m and exec_m and mkdir_m.start() > exec_m.start():
        failures.append("mkdir -p appears after exec")

    # 6. namespace guard
    details["refuses_shared_namespace"] = "local-prod-*" in text
    if "local-prod-*" not in text:
        failures.append("launcher does not explicitly refuse local-prod-* (shared) namespaces")
    if "SGLANG_RUN_ID" not in text:
        failures.append("launcher does not require SGLANG_RUN_ID")

    return {"ok": not failures, "failures": failures, "details": details}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--launcher", required=True)
    parser.add_argument("--tree", required=True)
    parser.add_argument("--identity", required=True)
    parser.add_argument("--expect-stream", default=None)
    parser.add_argument("--ref-launcher", default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    launcher = Path(args.launcher)
    if not launcher.is_file():
        print(f"audit: launcher not found: {launcher}", file=sys.stderr)
        return 2
    report = audit(
        launcher,
        args.tree,
        args.identity,
        args.expect_stream,
        Path(args.ref_launcher) if args.ref_launcher else None,
    )
    report["exit_code"] = 0 if report["ok"] else 1
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    elif report["ok"]:
        print(f"LAUNCHER-AUDIT PASS: {launcher}")
    else:
        print(f"LAUNCHER-AUDIT FAIL: {launcher}", file=sys.stderr)
        for f in report["failures"]:
            print(f"  - {f}", file=sys.stderr)
    return report["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
