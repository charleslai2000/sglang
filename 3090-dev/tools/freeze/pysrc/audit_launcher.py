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
     reference (v1.1) token list, with the declared per-identity profile delta
     (approved bind host, optional/required --served-model-name, required
     replacements, approved-new tokens, allowed-dropped reference tokens).  Any
     token/value outside the selected profile fails closed, and profile
     `forbidden_tokens` may never appear at all.
  5. the ARGS array + dry-run guard exist, the guard precedes mkdir/exec, and
     exec uses "${ARGS[@]}" (so the dry-run argv cannot diverge from the exec)
  6. the run-namespace guard refuses reserved/shared ids before anything runs

Profiles are keyed by the launcher identity (``--profile`` / auto-selected from
``--identity``).  The default (no profile) reproduces the historical v1.2.x
"Option A" firewall byte-for-byte so existing callers are unaffected.

Exit 0 = all checks pass, 1 = audit failure, 2 = usage/IO error.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
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

# ---------------------------------------------------------------------------
# Model-aware launcher profiles (design D3).
#
# `LAUNCHER_PROFILES` keys are the launcher IDENTITY strings.  A profile is the
# complete, explicit firewall for one identity:
#   approved_bind_hosts          -- exact set of allowed --host values
#   approved_served_model_names  -- exact set of allowed --served-model-name values
#   served_model_name_required   -- True: exactly one value REQUIRED;
#                                   False: absence is allowed, presence must be approved
#   required_replacements        -- old reference token -> alternatives; if `old`
#                                   is absent from the launcher at least one
#                                   alternative MUST be present (fail closed)
#   required_tokens              -- tokens that MUST be present (missing => FAIL)
#   approved_new_tokens          -- tokens allowed to appear that are not in the
#                                   reference (anything else => FAIL)
#   allowed_dropped_tokens       -- reference tokens the profile may legitimately
#                                   omit (any other dropped token => FAIL)
#   forbidden_tokens             -- tokens that may NEVER appear, even if they are
#                                   present in the reference (injection => FAIL)
#
# Fail-closed rules: unknown profile, any extra token, any missing required
# token, and any value mismatch are hard failures.  The delta comparison is
# exact set membership against the selected profile, never a blanket allowlist.
# ---------------------------------------------------------------------------


class UnknownProfileError(ValueError):
    """Raised when a caller names a launcher profile that does not exist."""


@dataclass(frozen=True)
class LauncherProfile:
    identity: str
    approved_bind_hosts: frozenset[str]
    approved_served_model_names: frozenset[str]
    served_model_name_required: bool
    required_replacements: dict[str, tuple[str, ...]]
    required_tokens: frozenset[str]
    approved_new_tokens: frozenset[str]
    allowed_dropped_tokens: frozenset[str]
    forbidden_tokens: frozenset[str]


# Legacy "Option A" firewall: the historical behaviour when no model-aware
# profile is selected (identity not in LAUNCHER_PROFILES).  Kept byte-for-byte
# so existing v1.2.x callers/tests are unaffected.
_DEFAULT_ALLOWED_NEW: frozenset[str] = frozenset(
    set(PRODUCTION_REQUIRED_SERVING_TOKENS)
    | set(PRODUCTION_REQUIRED_SERVING_REPLACEMENTS.values())
    | set(PRODUCTION_BIND_HOST_APPROVED.values())
    | {"--served-model-name"}
    | set(PRODUCTION_SERVED_MODEL_NAME_APPROVED)
)

DEFAULT_PROFILE = LauncherProfile(
    identity="",
    approved_bind_hosts=frozenset(PRODUCTION_BIND_HOST_APPROVED.values()),
    approved_served_model_names=frozenset(PRODUCTION_SERVED_MODEL_NAME_APPROVED),
    served_model_name_required=True,
    required_replacements={
        "65536": ("524288",),
        "127.0.0.1": ("192.168.20.250",),
    },
    required_tokens=frozenset(),
    approved_new_tokens=_DEFAULT_ALLOWED_NEW,
    allowed_dropped_tokens=frozenset(),
    forbidden_tokens=frozenset(FORBIDDEN_SERVING_TOKENS),
)

# M1 (LOCAL-PROD-v1.2.1): the installed production contract is bind 0.0.0.0,
# NO --served-model-name, and the extent L3 HiCache args.  `0.0.0.0` is added to
# the approved hosts (alongside 192.168.20.250) so the loopback health probe in
# bin/supervise.sh (http://127.0.0.1:$PORT/health) keeps working and repin does
# not silently rewrite the observable contract.
M1_PROFILE = LauncherProfile(
    identity="LOCAL-PROD-v1.2.1",
    approved_bind_hosts=frozenset({"0.0.0.0", "192.168.20.250"}),
    approved_served_model_names=frozenset(PRODUCTION_SERVED_MODEL_NAME_APPROVED),
    served_model_name_required=False,
    required_replacements={
        "65536": ("524288",),
        "127.0.0.1": ("0.0.0.0", "192.168.20.250"),
    },
    required_tokens=frozenset({
        "--context-length", "131072",
        "--max-running-requests", "8",
        "--max-mamba-cache-size", "48",
        "--max-total-tokens", "524288",
    }),
    approved_new_tokens=frozenset({
        "--context-length", "131072",
        "--max-running-requests", "8",
        "--max-mamba-cache-size", "48",
        "0.0.0.0",
        "192.168.20.250",
        "524288",
        "--served-model-name",
        "qwen35-9b-local",
    }),
    allowed_dropped_tokens=frozenset(),
    forbidden_tokens=frozenset(FORBIDDEN_SERVING_TOKENS),
)

# M2 (LOCAL-PROD-v1.2.1-M2): HiCache host (L2) ON with the X-f-proven trio,
# no L3 storage backend, bind 0.0.0.0, --served-model-name optional and, if
# present, must be the approved value.  The storage/prefetch/ready-horizon
# reference tokens are allowed to be dropped AND forbidden from reappearing.
M2_PROFILE = LauncherProfile(
    identity="LOCAL-PROD-v1.2.1-M2",
    approved_bind_hosts=frozenset({"0.0.0.0", "192.168.20.250"}),
    approved_served_model_names=frozenset(PRODUCTION_SERVED_MODEL_NAME_APPROVED),
    served_model_name_required=False,
    required_replacements={
        "65536": ("262144",),
        "127.0.0.1": ("0.0.0.0", "192.168.20.250"),
        "/data/models/qwen35-9b-w4a16": ('"$MODEL_PATH"',),
    },
    required_tokens=frozenset({
        "--context-length", "131072",
        "--max-running-requests", "8",
        "--max-mamba-cache-size", "48",
        "--max-total-tokens", "262144",
        "--enable-hierarchical-cache",
        "--hicache-write-policy", "write_back",
        "--hicache-size", "32",
    }),
    approved_new_tokens=frozenset({
        "--context-length", "131072",
        "--max-running-requests", "8",
        "--max-mamba-cache-size", "48",
        "0.0.0.0",
        "192.168.20.250",
        '"$MODEL_PATH"',
        "262144",
        "--enable-hierarchical-cache",
        "--hicache-write-policy", "write_back",
        "--hicache-size", "32",
        "--hicache-host-memory-mode", "cache",
        "--served-model-name",
        "qwen35-9b-local",
    }),
    allowed_dropped_tokens=frozenset({
        "--hicache-storage-backend",
        "extent",
        "--hicache-storage-prefetch-policy",
        "wait_complete",
        '"$L2_GB"',
        "--enable-ready-horizon",
    }),
    forbidden_tokens=frozenset(FORBIDDEN_SERVING_TOKENS) | frozenset({
        "--hicache-storage-backend",
        "--hicache-storage-prefetch-policy",
        "--hicache-storage-backend-extra-config",
        "--enable-ready-horizon",
        "--hicache-ratio",
        "--hicache-io-backend",
        "--hicache-mem-layout",
    }),
)

LAUNCHER_PROFILES: dict[str, LauncherProfile] = {
    M1_PROFILE.identity: M1_PROFILE,
    M2_PROFILE.identity: M2_PROFILE,
}


def select_profile(profile: str | None, identity: str) -> LauncherProfile:
    """Resolve the profile for an audit.

    * explicit ``profile`` name: must exist, else UnknownProfileError (fail closed)
    * ``None``: auto-select by identity, else the legacy DEFAULT_PROFILE
    """
    if profile is not None:
        try:
            return LAUNCHER_PROFILES[profile]
        except KeyError:
            raise UnknownProfileError(
                f"unknown launcher profile {profile!r}; known profiles: "
                f"{sorted(LAUNCHER_PROFILES)}"
            ) from None
    return LAUNCHER_PROFILES.get(identity, DEFAULT_PROFILE)


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
    profile: str | None = None,
) -> dict:
    text = launcher.read_text()
    failures: list[str] = []
    details: dict = {"launcher": str(launcher), "sha256_note": "hash computed by caller"}

    # Resolve the model-aware profile up front.  An explicitly named profile
    # that does not exist is fail-closed: nothing else about the launcher is
    # trusted and the audit returns a hard failure.
    try:
        profile_obj = select_profile(profile, identity)
    except UnknownProfileError as exc:
        failures.append(str(exc))
        return {"ok": False, "failures": failures, "details": details}
    details["profile"] = profile_obj.identity or "<<default>>"

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

    # 4. serving-profile firewall vs the v1.1 reference launcher.  The selected
    # profile declares the INTENTIONAL delta exactly: approved bind hosts, the
    # optional/required --served-model-name rule, required replacements, the
    # approved-new token set, and the reference tokens this identity may drop.
    # Any extra token, missing token, or value mismatch is a hard failure.  The
    # comparison is exact set membership (not a blanket whitelist): a token
    # absent from both the reference and the profile is always rejected.
    tokens = strip_code(text)
    flags = serving_flags(tokens)
    details["serving_flags"] = flags
    _sub = dict(profile_obj.required_replacements)
    _allowed_new = set(profile_obj.approved_new_tokens)
    # A reference token that is replaced is by definition allowed to disappear;
    # `missing_replacements` separately guarantees its alternative appears.
    _allowed_dropped = set(profile_obj.allowed_dropped_tokens) | set(_sub)
    # Required tokens are an absolute profile invariant: they must be present
    # whether or not a reference launcher is supplied.
    missing_required = (
        sorted(t for t in profile_obj.required_tokens if t not in flags)
        if flags is not None else []
    )
    details["missing_required_tokens"] = missing_required
    if missing_required:
        failures.append(
            f"required serving token(s) missing for profile "
            f"({profile_obj.identity or 'default'}): {missing_required}"
        )
    if flags is None:
        failures.append("no sglang.launch_server invocation found")
    elif ref_launcher is not None:
        ref_flags = serving_flags(strip_code(ref_launcher.read_text()))
        details["reference_serving_flags"] = ref_flags
        if ref_flags is None:
            failures.append(f"reference launcher {ref_launcher} has no flags to compare")
        else:
            only_new = [t for t in flags if t not in ref_flags]
            only_ref = [t for t in ref_flags if t not in flags]
            unapproved_new = [t for t in only_new if t not in _allowed_new]
            unapproved_dropped = [t for t in only_ref if t not in _allowed_dropped]
            # required replacement: if the reference token is present, at least
            # one declared alternative must be present in the new launcher.
            missing_replacements = sorted(
                old for old, alts in _sub.items()
                if old in ref_flags and not any(a in flags for a in alts)
            )
            details["serving_delta_allowance"] = {
                "profile": profile_obj.identity or "<<default>>",
                "declared_tokens": sorted(_allowed_new),
                "declared_dropped_tokens": sorted(_allowed_dropped),
                "declared_replacements": {k: list(v) for k, v in _sub.items()},
                "unapproved_new": unapproved_new,
                "unapproved_dropped": unapproved_dropped,
                "missing_replacements": missing_replacements,
                "missing_required_tokens": missing_required,
            }
            if (unapproved_new or unapproved_dropped
                    or missing_replacements or missing_required):
                failures.append(
                    "serving flags differ from reference beyond the exact "
                    f"profile ({profile_obj.identity or 'default'}) delta: "
                    f"only-in-new={only_new} "
                    f"only-in-reference={only_ref} "
                    f"unapproved_new={unapproved_new} "
                    f"unapproved_dropped={unapproved_dropped} "
                    f"missing_replacements={missing_replacements} "
                    f"missing_required_tokens={missing_required}"
                )

    # 4a. bind host validation.  Fail closed: --host MUST appear exactly once
    # and its value MUST be in the profile's approved set; unknown values fail.
    host_values = [
        tokens[i + 1] if i + 1 < len(tokens) else ""
        for i, tok in enumerate(tokens)
        if tok == "--host"
    ]
    approved_hosts = sorted(set(profile_obj.approved_bind_hosts))
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

    # 4b. served-model-name validation.  M2/M1 allow absence (the installed
    # contract carries no flag); when present, exactly one approved value is
    # required.  A profile with served_model_name_required=True (legacy default)
    # still hard-fails on absence.
    served_names: list[str] = []
    for i, tok in enumerate(tokens):
        if tok == "--served-model-name":
            _served_name = tokens[i + 1] if i + 1 < len(tokens) else ""
            served_names.append(_served_name)
            if _served_name not in profile_obj.approved_served_model_names:
                failures.append(
                    f"--served-model-name must be one of "
                    f"{sorted(profile_obj.approved_served_model_names)!r}, "
                    f"found {_served_name!r}"
                )
    if not served_names:
        if profile_obj.served_model_name_required:
            failures.append(
                "--served-model-name missing (exactly one approved value is required)"
            )
    elif len(served_names) > 1:
        failures.append(
            f"--served-model-name appears {len(served_names)} times; exactly one is allowed"
        )
    details["served_model_names"] = served_names
    details["served_model_name_required"] = profile_obj.served_model_name_required

    # 5. ARGS array + dry-run guard ordering
    has_args = re.search(r"^ARGS=\($", text, re.MULTILINE) is not None

    # 5b. Forbidden serving tokens.  AUTH keys are always forbidden (owner
    # ruling).  Profiles may forbid additional tokens outright (e.g. M2 forbids
    # the L3/storage args even though the v1.1 reference carries them): refusing
    # a forbidden token even when it appears in the reference is deliberate
    # fail-closed behavior, not a weakened check.
    forbidden = sorted(t for t in (flags or []) if t in FORBIDDEN_SERVING_TOKENS)
    details["forbidden_serving_tokens_present"] = forbidden
    if forbidden:
        failures.append(
            f"forbidden serving token(s) present (AUTH must be OFF): {forbidden}"
        )
    profile_forbidden = sorted(
        t for t in (flags or [])
        if t in profile_obj.forbidden_tokens and t not in FORBIDDEN_SERVING_TOKENS
    )
    details["profile_forbidden_tokens_present"] = profile_forbidden
    if profile_forbidden:
        failures.append(
            f"profile-forbidden serving token(s) present: {profile_forbidden}"
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
    parser.add_argument(
        "--profile",
        default=None,
        help="launcher profile name (key of LAUNCHER_PROFILES); when omitted, "
             "auto-select by --identity, else the legacy default firewall",
    )
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
        profile=args.profile,
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
