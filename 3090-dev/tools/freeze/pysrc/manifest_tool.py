#!/usr/bin/env python3
"""Deterministic tree-manifest generation / validation for the LOCAL-PROD line.

The v1.1 manifest is coreutils output from

    cd <tree> && find . -type f -not -path './manifest/*' \
        -not -path '*/__pycache__/*' -not -path '*/.pytest_cache/*' -print0 \
        | sort -z | xargs -0 sha256sum

This module re-implements that file set and ordering independently (bytewise
order == LC_ALL=C `sort -z`), so the freeze pipeline can cross-check the
coreutils output with a second implementation and fail closed if they diverge.
It also validates the exact line format, and produces the identity/pin JSON.

Exit codes: 0 ok, 1 validation/consistency failure, 2 usage/IO error.
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import re
import stat
import sys
from datetime import datetime, timezone
from pathlib import Path

EXCLUSION_PATTERNS = ("./manifest/*", "*/__pycache__/*", "*/.pytest_cache/*")
LINE_RE = re.compile(r"^([0-9a-f]{64})  (\./.+)$")


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def excluded(path: str) -> bool:
    return any(fnmatch.fnmatchcase(path, pat) for pat in EXCLUSION_PATTERNS)


def iter_hashed_files(tree: Path):
    """Yield (manifest_path, absolute_path) for every regular file that the v1.1
    manifest command would hash, in bytewise order."""
    found: list[tuple[str, str]] = []
    for root, _dirs, files in os.walk(tree, followlinks=False):
        for name in files:
            full = os.path.join(root, name)
            try:
                st = os.lstat(full)
            except OSError:
                continue
            if not stat.S_ISREG(st.st_mode):
                continue  # symlinks (and anything non-regular) are not hashed
            rel = os.path.relpath(full, tree)
            manifest_path = "./" + rel.replace(os.sep, "/")
            if excluded(manifest_path):
                continue
            found.append((manifest_path, full))
    found.sort(key=lambda item: os.fsencode(item[0]))
    return found


def sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def generate(tree: Path, out: Path) -> dict:
    errors: list[str] = []
    lines: list[str] = []
    count = total = 0
    src_count = src_bytes = 0
    for manifest_path, full in iter_hashed_files(tree):
        if "\\" in manifest_path or "\n" in manifest_path:
            errors.append(
                f"path contains backslash/newline; coreutils would escape it: {manifest_path!r}"
            )
            continue
        digest = sha256_file(full)
        lines.append(f"{digest}  {manifest_path}")
        st = os.lstat(full)
        count += 1
        total += st.st_size
        if manifest_path.startswith("./src/"):
            src_count += 1
            src_bytes += st.st_size
    if errors:
        return {"ok": False, "errors": errors}
    data = "".join(line + "\n" for line in lines)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(data)
    return {
        "ok": True,
        "out": str(out),
        "file_count": count,
        "total_bytes": total,
        "src_file_count": src_count,
        "src_total_bytes": src_bytes,
        "manifest_bytes": len(data.encode()),
        "manifest_sha256": hashlib.sha256(data.encode()).hexdigest(),
    }


def validate(manifest: Path) -> dict:
    errors: list[str] = []
    raw = manifest.read_bytes()
    if not raw:
        return {"ok": False, "errors": ["manifest is empty"]}
    if not raw.endswith(b"\n"):
        errors.append("manifest does not end with a newline")
    text = raw.decode("utf-8", errors="surrogateescape")
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    paths: list[str] = []
    for lineno, line in enumerate(lines, 1):
        m = LINE_RE.match(line)
        if not m:
            errors.append(f"line {lineno}: not '<64hex>  ./path': {line[:120]!r}")
            continue
        paths.append(m.group(2))
    if len(set(paths)) != len(paths):
        dupes = sorted({p for p in paths if paths.count(p) > 1})[:5]
        errors.append(f"duplicate paths: {dupes}")
    encoded = [os.fsencode(p) for p in paths]
    if encoded != sorted(encoded):
        for i in range(1, len(encoded)):
            if encoded[i] < encoded[i - 1]:
                errors.append(
                    f"manifest is not bytewise-sorted at line {i + 1}: "
                    f"{paths[i]!r} after {paths[i - 1]!r}"
                )
                break
    if "__pycache__" in text:
        errors.append("manifest contains __pycache__ entries (exclusion failed)")
    if "\n./manifest/" in "\n" + text:
        errors.append("manifest contains manifest/ entries (self-reference)")
    return {
        "ok": not errors,
        "errors": errors,
        "lines": len(lines),
        "manifest_sha256": hashlib.sha256(raw).hexdigest(),
        "manifest_bytes": len(raw),
    }


def entries(manifest: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in manifest.read_text().splitlines():
        if not line:
            continue
        digest, path = line.split("  ", 1)
        out[path] = digest
    return out


def compare(source: Path, dest: Path, allow_modified: set[str]) -> dict:
    a = entries(source)
    b = entries(dest)
    def norm(path: str) -> str:
        return path[2:] if path.startswith("./") else path

    allow = {norm(p) for p in allow_modified}
    errors: list[str] = []
    changed: list[dict] = []
    missing: list[str] = []
    for path, digest in a.items():
        if norm(path) in allow:
            changed.append(
                {"path": path, "source": digest, "dest": b.get(path), "reason": "allowed-repin"}
            )
            continue
        if path not in b:
            missing.append(path)
        elif b[path] != digest:
            changed.append({"path": path, "source": digest, "dest": b[path], "reason": "UNEXPECTED"})
    if missing:
        errors.append(f"{len(missing)} source file(s) missing from dest: {missing[:5]}")
    unexpected = [c for c in changed if c["reason"] == "UNEXPECTED"]
    if unexpected:
        errors.append(
            f"{len(unexpected)} file(s) changed content unexpectedly: "
            + ", ".join(c["path"] for c in unexpected[:5])
        )
    added = sorted(set(b) - set(a))
    return {
        "ok": not errors,
        "errors": errors,
        "source_files": len(a),
        "dest_files": len(b),
        "added": added,
        "changed_allowed": [c for c in changed if c["reason"] == "allowed-repin"],
    }


def src_stream_digest(tree: Path) -> str:
    """The v1-convention src-subtree stream digest:
    sha256 of the sha256sum stream produced from inside <tree>/src with the
    cache exclusions applied.  Independent of launcher bytes, so a launcher can
    embed it without circularity."""
    lines: list[str] = []
    src = tree / "src"
    for manifest_path, full in iter_hashed_files(src):
        digest = sha256_file(full)
        # v1 convention: `cd src && find .` => paths are './python/...'
        lines.append(f"{digest}  {manifest_path}")
    payload = "".join(line + "\n" for line in lines).encode()
    return hashlib.sha256(payload).hexdigest()


def sha256_of(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def stats_from_manifest(tree: Path, manifest: Path) -> dict:
    count = total = src_count = src_bytes = 0
    errors: list[str] = []
    for path in entries(manifest):
        full = tree / path[2:]
        try:
            st = os.lstat(full)
        except OSError:
            errors.append(f"missing: {path}")
            continue
        count += 1
        total += st.st_size
        if path.startswith("./src/"):
            src_count += 1
            src_bytes += st.st_size
    return {
        "ok": not errors,
        "errors": errors,
        "file_count": count,
        "total_bytes": total,
        "src_file_count": src_count,
        "src_total_bytes": src_bytes,
    }


def fidelity(
    source_tree: Path,
    source_manifest: Path,
    dest_tree: Path,
    dest_manifest: Path,
    allow_modified: set[str],
) -> dict:
    """Copy-fidelity proof: every source file must be byte-identical in the
    destination unless explicitly allowed to be re-pinned, and the destination
    count/bytes must equal the source's plus exactly the intended deltas."""
    cmp_report = compare(source_manifest, dest_manifest, allow_modified)
    src_stats = stats_from_manifest(source_tree, source_manifest)
    dst_stats = stats_from_manifest(dest_tree, dest_manifest)
    errors = list(cmp_report["errors"]) + list(src_stats["errors"]) + list(dst_stats["errors"])

    src_entries = entries(source_manifest)
    dst_entries = entries(dest_manifest)
    added = cmp_report["added"]
    modified = [c["path"] for c in cmp_report["changed_allowed"]]

    def size(tree: Path, path: str) -> int:
        try:
            return os.lstat(tree / path[2:]).st_size
        except OSError:
            return 0

    expected_count = src_stats["file_count"] + len(added)
    expected_bytes = src_stats["total_bytes"] + sum(
        size(dest_tree, p) for p in added
    ) + sum(size(dest_tree, p) - size(source_tree, p) for p in modified)

    if dst_stats["file_count"] != expected_count:
        errors.append(
            f"file count {dst_stats['file_count']} != expected {expected_count} "
            f"(source {src_stats['file_count']} + added {len(added)})"
        )
    if dst_stats["total_bytes"] != expected_bytes:
        errors.append(
            f"total bytes {dst_stats['total_bytes']} != expected {expected_bytes}"
        )
    if set(dst_entries) - set(src_entries) - set(added):
        extra = sorted(set(dst_entries) - set(src_entries) - set(added))
        errors.append(f"unexplained extra files in dest: {extra[:5]}")
    return {
        "ok": not errors,
        "errors": errors,
        "source": {"tree": str(source_tree), **src_stats},
        "dest": {"tree": str(dest_tree), **dst_stats},
        "added": added,
        "modified_allowed": cmp_report["changed_allowed"],
        "expected_count": expected_count,
        "expected_bytes": expected_bytes,
    }


def emit_identity(
    tree: Path,
    identity: str,
    manifest_sha: str,
    manifest_bytes: int,
    stats: dict,
    stream: str,
    extra: dict,
) -> dict:
    tree_name = tree.name
    report = {
        "name": identity,
        "status": "FROZEN",
        "identity_version": 1,
        "frozen_at_utc": now_utc(),
        "no_server_started": True,
        "gpu_touched": False,
        "layout": {
            "src": {"path": str(tree / "src"), "mode_after_freeze": "write bits cleared on every entry"},
            "env": {"path": str(tree / "env"), "type": "symlink", "note": "shared venv, not per-tree frozen"},
            "launcher": {"path": str(tree / "launcher" / "launch.sh")},
            "tools": {"path": str(tree / "tools")},
            "manifest": {"path": str(tree / "manifest"), "note": "evidence dir, intentionally writable"},
        },
        "tree": {
            "path": str(tree),
            "tree_name": tree_name,
            "src_path": str(tree / "src"),
            "file_count": stats["file_count"],
            "total_bytes": stats["total_bytes"],
            "src_file_count": stats["src_file_count"],
            "src_total_bytes": stats["src_total_bytes"],
            "tree_manifest_file": "manifest/TREE-SHA256.txt",
            "tree_manifest_digest_sha256": manifest_sha,
            "tree_manifest_sha256_self": manifest_sha,
            "tree_manifest_bytes": manifest_bytes,
            "tree_manifest_lines": stats["file_count"],
            "tree_manifest_sha256_command": f"sha256sum {tree}/manifest/TREE-SHA256.txt",
            "tree_manifest_generation_command": (
                f"cd {tree} && find . -type f -not -path './manifest/*' "
                "-not -path '*/__pycache__/*' -not -path '*/.pytest_cache/*' -print0 "
                "| LC_ALL=C sort -z | xargs -0 sha256sum"
            ),
            "srctree_stream_digest_sha256_v1_convention": stream,
            "srctree_stream_digest_command_v1_convention": (
                f"cd {tree}/src && find . -type f -not -path '*/__pycache__/*' "
                "-not -path '*/.pytest_cache/*' -print0 | LC_ALL=C sort -z "
                "| xargs -0 sha256sum | sha256sum"
            ),
            "exclusions": {
                "manifest/": "self-reference; its digest is recorded here instead",
                "__pycache__/ and .pytest_cache/": "interpreter/test-runner byproducts",
            },
        },
        "runtime": {
            "env_symlink": str(tree / "env"),
            "editable_binding_caveat": (
                "the venv editable install resolves sglang to the live WIP workspace; "
                "every launch MUST export PYTHONPATH=<tree>/src/python and pass the "
                "fail-closed source-identity gate in launcher/launch.sh"
            ),
        },
        "namespace_policy": {
            "rule": "one task/run -> one unique L3 store namespace",
            "store": "<SGLANG_L3_ROOT>/<SGLANG_RUN_ID>, default /data/l3/<run-id>",
            "shared_stores": "never used or cleared by a run (clearing destroys the previous run's WAL/durability evidence)",
            "enforcement": "tools/l3_namespace.py (installed verbatim from the freeze tool) + launcher gate",
        },
        "freeze_tool": extra.get("freeze_tool", "v1.1.2-freeze-20260917"),
        "source_tree": extra.get("source_tree"),
        "generated_by": extra.get("generated_by"),
        "self_test": extra.get("self_test", {}),
        "open_items": extra.get("open_items", []),
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_gen = sub.add_parser("generate")
    p_gen.add_argument("--tree", required=True)
    p_gen.add_argument("--out", required=True)
    p_gen.add_argument("--json", action="store_true")

    p_val = sub.add_parser("validate")
    p_val.add_argument("--manifest", required=True)
    p_val.add_argument("--json", action="store_true")

    p_stats = sub.add_parser("stats")
    p_stats.add_argument("--tree", required=True)
    p_stats.add_argument("--manifest", required=True)
    p_stats.add_argument("--json", action="store_true")

    p_fid = sub.add_parser("fidelity")
    p_fid.add_argument("--source-tree", required=True)
    p_fid.add_argument("--source-manifest", required=True)
    p_fid.add_argument("--dest-tree", required=True)
    p_fid.add_argument("--dest-manifest", required=True)
    p_fid.add_argument("--allow-modified", default="")
    p_fid.add_argument("--json", action="store_true")

    p_cmp = sub.add_parser("compare")
    p_cmp.add_argument("--source", required=True)
    p_cmp.add_argument("--dest", required=True)
    p_cmp.add_argument("--allow-modified", default="")
    p_cmp.add_argument("--json", action="store_true")

    p_stream = sub.add_parser("src-stream")
    p_stream.add_argument("--tree", required=True)
    p_stream.add_argument("--json", action="store_true")

    p_sha = sub.add_parser("sha256")
    p_sha.add_argument("--file", required=True)

    args = parser.parse_args()

    if args.cmd == "generate":
        report = generate(Path(args.tree), Path(args.out))
        if args.json:
            print(json.dumps(report, indent=2, sort_keys=True))
        elif not report["ok"]:
            for e in report["errors"]:
                print(f"manifest generate: {e}", file=sys.stderr)
        else:
            print(
                f"manifest generated: {report['file_count']} files, "
                f"{report['total_bytes']} bytes, sha256={report['manifest_sha256']}"
            )
        return 0 if report["ok"] else 1

    if args.cmd == "validate":
        report = validate(Path(args.manifest))
        if args.json:
            print(json.dumps(report, indent=2, sort_keys=True))
        elif not report["ok"]:
            for e in report["errors"]:
                print(f"manifest validate: {e}", file=sys.stderr)
        return 0 if report["ok"] else 1

    if args.cmd == "stats":
        man = Path(args.manifest)
        tree = Path(args.tree)
        report = stats_from_manifest(tree, man)
        if args.json:
            print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if report["ok"] else 1

    if args.cmd == "fidelity":
        allow = {p for p in args.allow_modified.split(",") if p}
        report = fidelity(
            Path(args.source_tree),
            Path(args.source_manifest),
            Path(args.dest_tree),
            Path(args.dest_manifest),
            allow,
        )
        if args.json:
            print(json.dumps(report, indent=2, sort_keys=True))
        elif not report["ok"]:
            for e in report["errors"]:
                print(f"fidelity: {e}", file=sys.stderr)
        return 0 if report["ok"] else 1

    if args.cmd == "compare":
        allow = {p for p in args.allow_modified.split(",") if p}
        report = compare(Path(args.source), Path(args.dest), allow)
        if args.json:
            print(json.dumps(report, indent=2, sort_keys=True))
        elif not report["ok"]:
            for e in report["errors"]:
                print(f"manifest compare: {e}", file=sys.stderr)
        return 0 if report["ok"] else 1

    if args.cmd == "src-stream":
        digest = src_stream_digest(Path(args.tree))
        if args.json:
            print(json.dumps({"src_stream_digest_v1_convention": digest}, indent=2))
        else:
            print(digest)
        return 0

    if args.cmd == "sha256":
        value = sha256_of(Path(args.file))
        if value is None:
            print(f"cannot read {args.file}", file=sys.stderr)
            return 2
        print(f"{value}  {args.file}")
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
