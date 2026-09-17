#!/usr/bin/env python3
"""Repoint tools/validate_telemetry.py to a new frozen tree and FAIL CLOSED if
its hash bindings no longer hold.

The v1.1 incident had two halves: a launcher that still bound v1, and a
telemetry tool whose SRC still pointed at v1.  Repointing the path is only half
the job: the tool binds 6 reviewed source bytes + 4 Gate/erratum artifacts by
SHA-256 relative to SRC, so a repoint must be accompanied by proof that those
bindings still resolve to the same bytes under the new tree.

Exit codes: 0 ok, 1 binding failure, 2 usage/IO error.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import sys
from pathlib import Path

TREE_RE = re.compile(r"/opt/sglang/[A-Za-z0-9._\-]+")
IDENT_RE = re.compile(r"LOCAL-PROD-[A-Za-z0-9._\-]+")
SRC_RE = re.compile(r'^SRC\s*=\s*"([^"]+)"\s*$', re.MULTILINE)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


_SAFE_NODES = (
    ast.Expression, ast.Constant, ast.JoinedStr, ast.FormattedValue, ast.Name,
    ast.Dict, ast.List, ast.Tuple, ast.BinOp, ast.Add, ast.Load,
)


def _safe_eval(value_node: ast.expr, names: dict) -> object:
    """Evaluate a *constant expression* that may reference already-resolved
    names (e.g. EVID = f"{SRC}/...") without executing any call or attribute."""
    for sub in ast.walk(value_node):
        if not isinstance(sub, _SAFE_NODES):
            raise ValueError(f"unsafe node in constant expression: {type(sub).__name__}")
    code = compile(ast.Expression(value_node), "<const>", "eval")
    return eval(code, {"__builtins__": {}}, names)  # noqa: S307 - whitelisted AST


def literal_dicts(text: str) -> dict[str, dict[str, str]]:
    """Extract `NAME = {str: str}` assignments without executing the module.
    Handles f-string keys that depend on earlier constants."""
    assignments: list[tuple[str, ast.expr]] = []
    tree = ast.parse(text)
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            assignments.append((node.targets[0].id, node.value))
    names: dict = {}
    unresolved = list(assignments)
    for _ in range(len(unresolved) + 1):
        progress = False
        remaining = []
        for name, value in unresolved:
            try:
                names[name] = _safe_eval(value, names)
                progress = True
            except (ValueError, NameError, TypeError):
                remaining.append((name, value))
        unresolved = remaining
        if not progress:
            break
    return {
        name: value
        for name, value in names.items()
        if isinstance(value, dict) and all(isinstance(v, str) for v in value.values())
    }


def verify_bindings(text: str, tree: Path) -> dict:
    """Check every hash-binding dict in the tool against the new tree.
    Bindings whose value is a path (absolute) are resolved as-is; relative ones
    are resolved under <tree>/src."""
    src = tree / "src"
    checked: list[dict] = []
    mismatched: list[dict] = []
    missing: list[str] = []
    for name, mapping in literal_dicts(text).items():
        if "HASH" not in name.upper() and "HASHES" not in name.upper():
            continue
        for key, expected in mapping.items():
            if key.startswith("/"):
                path = Path(key)
            else:
                path = src / key
            if not path.is_file():
                missing.append(str(path))
                continue
            actual = sha256_file(path)
            row = {"dict": name, "path": str(path), "expected": expected, "actual": actual}
            row["match"] = actual == expected
            checked.append(row)
            if not row["match"]:
                mismatched.append(row)
    return {
        "bindings_checked": len(checked),
        "bindings_mismatched": mismatched,
        "bindings_missing": missing,
        "ok": not mismatched and not missing,
    }


def repoint(text: str, new_tree: str, new_identity: str) -> tuple[str, dict]:
    m = SRC_RE.search(text)
    if not m:
        return text, {"ok": False, "error": "no `SRC = \"...\"` assignment found"}
    old_src = m.group(1)
    old_tree = str(Path(old_src).parent)
    new_src = f"{new_tree}/src"

    old_trees = sorted(set(TREE_RE.findall(text)))
    idents = sorted(set(IDENT_RE.findall(text)))
    old_idents = [i for i in idents if i != new_identity]

    new_text = text.replace(old_src, new_src)
    for old in old_trees:
        if old != new_tree:
            new_text = new_text.replace(old, new_tree)
    for old in old_idents:
        new_text = new_text.replace(old, new_identity)

    return new_text, {
        "old_src": old_src,
        "new_src": new_src,
        "old_tree": old_tree,
        "old_trees": old_trees,
        "old_identities": old_idents,
        "src_substitutions": text.count(old_src),
        "tree_substitutions": sum(text.count(o) for o in old_trees if o != new_tree),
        "identity_substitutions": sum(text.count(o) for o in old_idents),
        "ok": True,
    }


def audit_result(text: str, new_tree: str, new_identity: str) -> dict:
    trees = sorted(set(TREE_RE.findall(text)))
    idents = sorted(set(IDENT_RE.findall(text)))
    bad_trees = [t for t in trees if t != new_tree]
    bad_idents = [i for i in idents if i != new_identity]
    return {
        "trees_referenced": trees,
        "identities_referenced": idents,
        "foreign_trees": bad_trees,
        "foreign_identities": bad_idents,
        "ok": not bad_trees and not bad_idents,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", required=True, help="tools/validate_telemetry.py (in the staged tree)")
    parser.add_argument("--tree", required=True, help="destination tree root")
    parser.add_argument("--identity", required=True)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    path = Path(args.file)
    if not path.is_file():
        print(f"repoint: not found: {path}", file=sys.stderr)
        return 2
    text = path.read_text()
    new_text, changes = repoint(text, args.tree.rstrip("/"), args.identity)
    report = {"changes": changes, "audit": audit_result(new_text, args.tree.rstrip("/"), args.identity)}
    if not changes.get("ok"):
        report["ok"] = False
        report["exit_code"] = 1
        if args.json:
            print(json.dumps(report, indent=2, sort_keys=True))
        else:
            print(f"repoint FAILED: {changes.get('error')}", file=sys.stderr)
        return 1
    if not report["audit"]["ok"]:
        report["ok"] = False
        report["exit_code"] = 1
        if args.json:
            print(json.dumps(report, indent=2, sort_keys=True))
        else:
            print(
                "repoint FAILED: foreign references remain: "
                f"trees={report['audit']['foreign_trees']} "
                f"identities={report['audit']['foreign_identities']}",
                file=sys.stderr,
            )
        return 1

    bindings = verify_bindings(new_text, Path(args.tree))
    report["bindings"] = bindings
    if not bindings["ok"]:
        report["ok"] = False
        report["exit_code"] = 1
        if args.json:
            print(json.dumps(report, indent=2, sort_keys=True))
        else:
            print(
                "repoint FAILED: telemetry hash bindings do not hold under the new tree "
                "(the reviewed bytes must be re-bound and re-reviewed; do not paper over this):",
                file=sys.stderr,
            )
            for row in bindings["bindings_mismatched"]:
                print(f"  MISMATCH {row['path']}: expected {row['expected']} got {row['actual']}", file=sys.stderr)
            for miss in bindings["bindings_missing"]:
                print(f"  MISSING  {miss}", file=sys.stderr)
        return 1

    if args.write:
        path.write_text(new_text)
        report["written"] = True
    else:
        report["written"] = False
    report["ok"] = True
    report["exit_code"] = 0
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(
            f"repoint OK: {path} -> {changes['new_src']} "
            f"(src x{changes['src_substitutions']}, identity x{changes['identity_substitutions']}, "
            f"bindings {bindings['bindings_checked']}/{bindings['bindings_checked']} verified)"
            + ("" if args.write else " [dry-run, not written]")
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
