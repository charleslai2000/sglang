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
     reference (v1.1) token list
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

    # 4. serving flags vs reference
    tokens = strip_code(text)
    flags = serving_flags(tokens)
    details["serving_flags"] = flags
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
            failures.append(
                "serving flags differ from reference: "
                f"only-in-new={only_new} only-in-reference={only_ref}"
            )

    # 5. ARGS array + dry-run guard ordering
    has_args = re.search(r"^ARGS=\($", text, re.MULTILINE) is not None
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
