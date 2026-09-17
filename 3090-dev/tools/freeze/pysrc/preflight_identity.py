#!/usr/bin/env python3
"""Reusable source-identity preflight gate (charter AMENDMENT 1-A).

Exits immediately with a nonzero status unless ALL of:

  1. `sglang.__file__` resolves inside the designated frozen tree (never the
     workspace WIP copy that the venv editable `.pth` binds);
  2. key file hashes match the tree manifest, and the manifest's own digest
     matches the digest recorded in `manifest/identity.json`;
  3. the running process is re-confirmed at runtime from `/proc/<pid>/environ`
     (and, when available, `/proc/<pid>/maps`).

General by construction: `--tree`, `--pid`, `--key-file` and `--all` are
arguments, so this is not hardcoded to one run. Intended to be prepended to every
future formal run.

Exit codes
  0  PASS
  2  sglang resolved outside the designated tree
  3  manifest structure/self-digest/key-hash failure
  4  runtime process confirmation failure (/proc/<pid>/environ)
  5  tree layout missing
  6  usage error
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

DEFAULT_TREE = Path("/opt/sglang/local-prod-v1.1-candidate")
DEFAULT_MANIFEST = "manifest/TREE-SHA256.txt"

#: The files this L3 native line depends on. Override with --key-file.
DEFAULT_KEY_FILES = (
    "src/python/sglang/srt/rust_extensions/loader.py",
    "src/python/sglang/srt/mem_cache/storage/extent/extent_file_backend.py",
    "src/python/sglang/srt/mem_cache/storage/extent/extent_metadata.py",
    "src/python/sglang/srt/mem_cache/pool_host/mha.py",
    "src/python/sglang/srt/mem_cache/pool_host/mamba.py",
    "src/rust/Cargo.toml",
    "launcher/launch.sh",
)


class Failure(Exception):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def read_manifest(manifest_path: Path) -> dict[str, str]:
    entries: dict[str, str] = {}
    with manifest_path.open() as handle:
        for line in handle:
            line = line.rstrip("\n")
            if not line:
                continue
            parts = line.split(None, 1)
            if len(parts) != 2:
                raise Failure(3, f"malformed manifest line: {line!r}")
            digest, raw_path = parts
            clean = raw_path.strip()
            if clean.startswith("./"):
                clean = clean[2:]
            entries[clean] = digest
    return entries


def check_layout(tree: Path, manifest_path: Path) -> None:
    for candidate in (tree, tree / "src" / "python", manifest_path):
        if not candidate.exists():
            raise Failure(5, f"tree layout missing: {candidate}")


def check_import(tree: Path, report: dict) -> None:
    """Check 1: `sglang.__file__` must resolve inside the frozen tree."""
    expected_root = (tree / "src" / "python").resolve()
    probe = (
        "import json, sys, sglang; "
        "print(json.dumps({'file': sglang.__file__, "
        "'sys_path': sys.path[:6], "
        "'python': sys.executable}))"
    )
    proc = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True
    )
    if proc.returncode != 0:
        raise Failure(
            2,
            "import probe failed, so frozen-tree resolution cannot be confirmed:\n"
            + proc.stderr.strip()[-1500:],
        )
    payload = json.loads(proc.stdout.strip().splitlines()[-1])
    resolved = Path(payload["file"]).resolve()
    report["import_check"] = {
        "sglang_file": str(resolved),
        "expected_root": str(expected_root),
        "python": payload["python"],
        "sys_path_head": payload["sys_path"],
    }
    if not resolved.is_relative_to(expected_root):
        raise Failure(
            2,
            f"sglang resolved OUTSIDE the designated frozen tree: {resolved}\n"
            f"  expected under: {expected_root}\n"
            "  cause: PYTHONPATH does not put the frozen tree ahead of the "
            "venv editable binding",
        )


def check_manifest(
    tree: Path, manifest_path: Path, key_files: list[str], verify_all: bool, report: dict
) -> None:
    """Check 2: manifest integrity plus key (or all) file hashes."""
    manifest_digest = sha256_file(manifest_path)
    report["manifest"] = {
        "path": str(manifest_path),
        "sha256": manifest_digest,
    }
    identity_path = tree / "manifest" / "identity.json"
    if identity_path.is_file():
        identity = json.loads(identity_path.read_text())
        recorded = identity.get("tree", {}).get("tree_manifest_sha256_self")
        report["manifest"]["recorded_in_identity_json"] = recorded
        if recorded and recorded != manifest_digest:
            raise Failure(
                3,
                "manifest self-digest does not match identity.json:\n"
                f"  computed {manifest_digest}\n  recorded {recorded}",
            )
    entries = read_manifest(manifest_path)
    report["manifest"]["entries"] = len(entries)

    targets = sorted(entries) if verify_all else list(key_files)
    checked: list[dict] = []
    missing: list[str] = []
    mismatched: list[dict] = []
    for relative in targets:
        path = tree / relative
        expected = entries.get(relative)
        if expected is None:
            missing.append(relative)
            continue
        if not path.is_file():
            missing.append(relative)
            continue
        actual = sha256_file(path)
        row = {
            "path": relative,
            "expected": expected,
            "actual": actual,
            "match": actual == expected,
        }
        checked.append(row)
        if actual != expected:
            mismatched.append(row)
    report["manifest"]["key_files_checked"] = checked
    report["manifest"]["verify_all"] = verify_all
    if missing:
        raise Failure(
            3, "key files absent from tree or manifest: " + ", ".join(missing)
        )
    if mismatched:
        detail = "\n".join(
            f"  {row['path']}: expected {row['expected']} got {row['actual']}"
            for row in mismatched
        )
        raise Failure(3, "key file hash mismatch:\n" + detail)


def check_runtime_pid(pid: int, tree: Path, report: dict) -> None:
    """Check 3: re-confirm the running process from /proc/<pid>/environ."""
    proc_root = Path(f"/proc/{pid}")
    if not proc_root.exists():
        raise Failure(4, f"runtime confirmation failed: /proc/{pid} does not exist")
    environ_raw = (proc_root / "environ").read_bytes()
    environ = dict(
        item.split("=", 1)
        for item in environ_raw.decode(errors="replace").split("\0")
        if "=" in item
    )
    expected = str((tree / "src" / "python").resolve())
    pythonpath = environ.get("PYTHONPATH", "")
    entries = [p for p in pythonpath.split(":") if p]
    report["runtime_pid"] = {
        "pid": pid,
        "PYTHONPATH": pythonpath,
        "pythonpath_contains_tree": expected in entries,
        "CUDA_VISIBLE_DEVICES": environ.get("CUDA_VISIBLE_DEVICES"),
        "cmdline": (proc_root / "cmdline")
        .read_bytes()
        .decode(errors="replace")
        .replace("\0", " ")
        .strip(),
    }
    if expected not in entries:
        raise Failure(
            4,
            f"/proc/{pid}/environ PYTHONPATH does not contain {expected}\n"
            f"  PYTHONPATH={pythonpath!r}",
        )
    # Corroboration only: a loaded .so from the tree proves the tree was used.
    try:
        maps = (proc_root / "maps").read_text(errors="replace")
    except OSError:
        maps = ""
    tree_maps = [
        line.split()[-1]
        for line in maps.splitlines()
        if line.split() and str(tree) in line.split()[-1]
    ]
    report["runtime_pid"]["tree_mapped_objects"] = sorted(set(tree_maps))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tree", default=str(DEFAULT_TREE))
    parser.add_argument(
        "--pid",
        default="self",
        help="'self', 'none', or a PID whose /proc/<pid>/environ is re-confirmed",
    )
    parser.add_argument("--manifest", default=DEFAULT_MANIFEST)
    parser.add_argument(
        "--key-file",
        action="append",
        default=None,
        help="tree-relative path to hash-verify (repeatable)",
    )
    parser.add_argument("--all", action="store_true", help="verify every manifest entry")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    tree = Path(args.tree).resolve()
    manifest_path = (tree / args.manifest).resolve()
    key_files = args.key_file if args.key_file else list(DEFAULT_KEY_FILES)
    report: dict = {
        "gate": "source-identity preflight",
        "tree": str(tree),
        "checks": {},
    }
    try:
        check_layout(tree, manifest_path)
        report["checks"]["layout"] = "PASS"
        check_import(tree, report)
        report["checks"]["import_tree_binding"] = "PASS"
        check_manifest(tree, manifest_path, key_files, args.all, report)
        report["checks"]["manifest_hashes"] = "PASS"
        if args.pid == "none":
            report["checks"]["runtime_pid"] = "SKIPPED (--pid none)"
        else:
            pid = os.getpid() if args.pid == "self" else int(args.pid)
            check_runtime_pid(pid, tree, report)
            report["checks"]["runtime_pid"] = "PASS"
    except Failure as failure:
        report["result"] = "FAIL"
        report["exit_code"] = failure.code
        report["error"] = failure.message
        if args.json:
            print(json.dumps(report, indent=2))
        else:
            print(f"PREFLIGHT FAIL (exit {failure.code}): {failure.message}", file=sys.stderr)
            print(json.dumps(report, indent=2))
        return failure.code

    report["result"] = "PASS"
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(json.dumps(report, indent=2))
        print(
            "PREFLIGHT PASS: "
            + ", ".join(f"{key}={value}" for key, value in report["checks"].items())
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
