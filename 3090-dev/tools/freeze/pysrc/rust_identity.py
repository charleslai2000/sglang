#!/usr/bin/env python3
"""Reproduce the native-extension build identity the runtime loader selects on.

The runtime (`python/sglang/srt/rust_extensions/loader.py`) picks the cached
`.so` by a ``fingerprint`` computed over the ``rust/`` workspace sources, the
cargo/rustc toolchain and the Python ABI.  A freeze must record that exact key
so a candidate can prove *which* native binary its source implies; otherwise a
new source HEAD plus a stale cached ``.so`` could pass unnoticed.

This module mirrors ``loader._source_digest`` + ``loader._build_context`` +
``loader._cache_root`` + ``loader._cached_extension_path`` exactly.  It is
stdlib-only on purpose: it can then run under the tree's own venv interpreter
without importing ``sglang`` (whose ``__init__`` pulls torch and redirects
third-party caches).  Equivalence with the real loader is checked explicitly by
``--verify-with-loader`` and in the freeze tool's tests.

It never invents a value: an unavailable toolchain or artifact is reported as
``null`` with a machine-readable reason.

Exit codes: 0 ok (even with null fields), 2 usage/IO error.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import struct
import subprocess
import sys
import sysconfig
from pathlib import Path

# Kept in lockstep with loader.py.
_FINGERPRINT_VERSION = 1
_IGNORED_SOURCE_DIRECTORIES = frozenset(
    {".git", ".mypy_cache", ".pytest_cache", "__pycache__", "target"}
)
_BUILD_ENVIRONMENT_VARIABLES = (
    "CARGO_BUILD_TARGET",
    "CARGO_ENCODED_RUSTFLAGS",
    "RUSTFLAGS",
)


def _source_files(workspace: Path):
    for root, directories, filenames in os.walk(workspace):
        directories[:] = sorted(
            name for name in directories if name not in _IGNORED_SOURCE_DIRECTORIES
        )
        root_path = Path(root)
        for filename in sorted(filenames):
            yield root_path / filename


def _source_digest(workspace: Path) -> str:
    digest = hashlib.sha256()
    for path in _source_files(workspace):
        relative_path = path.relative_to(workspace).as_posix().encode()
        digest.update(len(relative_path).to_bytes(8, "big"))
        digest.update(relative_path)
        if path.is_symlink():
            contents = os.readlink(path).encode()
        else:
            contents = path.read_bytes()
        digest.update(len(contents).to_bytes(8, "big"))
        digest.update(contents)
    return digest.hexdigest()


def _json_digest(value: object) -> str:
    serialized = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode()
    return hashlib.sha256(serialized).hexdigest()


def _command_version(command: str, *arguments: str, cwd: Path) -> str:
    result = subprocess.run(
        [command, *arguments], check=True, capture_output=True, text=True, cwd=cwd
    )
    return result.stdout.strip()


def build_context(workspace: Path, package: str, library: str, python_module: str) -> dict:
    """Return the loader's source_digest / fingerprint / target_fingerprint."""
    source_digest = _source_digest(workspace)
    toolchain = {
        "cargo": _command_version(
            "cargo", "--version", "--verbose", cwd=workspace
        ),
        "rustc": _command_version("rustc", "-vV", cwd=workspace),
    }
    python_abi = {
        "cache_tag": sys.implementation.cache_tag,
        "ext_suffix": sysconfig.get_config_var("EXT_SUFFIX"),
        "platform": sysconfig.get_platform(),
        "pointer_bits": struct.calcsize("P") * 8,
        "soabi": sysconfig.get_config_var("SOABI"),
        "version": list(sys.version_info[:3]),
    }
    build_environment = {
        name: os.environ.get(name) for name in _BUILD_ENVIRONMENT_VARIABLES
    }
    target_inputs = {
        "build_environment": build_environment,
        "python_abi": python_abi,
        "toolchain": toolchain,
    }
    target_fingerprint = _json_digest(target_inputs)[:24]
    fingerprint = _json_digest(
        {
            "fingerprint_version": _FINGERPRINT_VERSION,
            "package": package,
            "library": library,
            "python_module": python_module,
            "source_digest": source_digest,
            **target_inputs,
        }
    )
    return {
        "source_digest": source_digest,
        "fingerprint": fingerprint,
        "target_fingerprint": target_fingerprint,
    }


def cache_root(explicit: str | None) -> Path:
    """Mirror loader._cache_root(None): SGLANG_CACHE_DIR/rust_extensions."""
    if explicit:
        return Path(explicit).expanduser().resolve()
    sglang_cache = os.environ.get("SGLANG_CACHE_DIR") or "~/.cache/sglang"
    return Path(sglang_cache).expanduser().resolve() / "rust_extensions"


def cached_extension_path(
    root: Path, package: str, fingerprint: str, python_module: str
) -> Path:
    ext_suffix = sysconfig.get_config_var("EXT_SUFFIX")
    if not ext_suffix:
        raise RuntimeError("Python did not report an EXT_SUFFIX")
    module_leaf = python_module.rsplit(".", 1)[-1]
    return root / "artifacts" / package / fingerprint / (module_leaf + ext_suffix)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tree", required=True, help="frozen tree (uses <tree>/src/rust)")
    parser.add_argument("--rust-workspace", default=None, help="override the rust workspace")
    parser.add_argument("--package", default="l3-native-wal")
    parser.add_argument("--library", default="l3_native_wal")
    parser.add_argument("--python-module", default="sglang.srt.rust_extensions._l3wal")
    parser.add_argument("--cache-root", default=None, help="override SGLANG_CACHE_DIR/rust_extensions")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    tree = Path(args.tree).resolve()
    workspace = (
        Path(args.rust_workspace).resolve()
        if args.rust_workspace
        else tree / "src" / "rust"
    )
    report: dict = {
        "package": args.package,
        "library": args.library,
        "python_module": args.python_module,
        "tree": str(tree),
        "rust_workspace": str(workspace),
        "computed_by": sys.executable,
        "rust_source_digest": None,
        "rust_source_digest_kind": "loader._build_context().fingerprint (v1)",
        "source_digest": None,
        "target_fingerprint": None,
        "cache_root": None,
        "loaded_so_path": None,
        "loaded_so_present": False,
        "loaded_so_bytes": None,
        "loaded_so_sha256": None,
        "unavailable_reason": None,
    }

    if not workspace.is_dir():
        report["unavailable_reason"] = f"rust workspace missing: {workspace}"
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0

    try:
        context = build_context(
            workspace, args.package, args.library, args.python_module
        )
    except (OSError, subprocess.CalledProcessError, RuntimeError) as exc:
        report["unavailable_reason"] = (
            f"toolchain unavailable ({type(exc).__name__}): {exc}"
        )
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0

    root = cache_root(args.cache_root)
    extension = cached_extension_path(
        root, args.package, context["fingerprint"], args.python_module
    )
    report.update(
        {
            "rust_source_digest": context["fingerprint"],
            "source_digest": context["source_digest"],
            "target_fingerprint": context["target_fingerprint"],
            "cache_root": str(root),
            "loaded_so_path": str(extension),
        }
    )
    if extension.is_file():
        report["loaded_so_present"] = True
        report["loaded_so_bytes"] = extension.stat().st_size
        report["loaded_so_sha256"] = sha256_file(extension)
    else:
        report["unavailable_reason"] = (
            "cached native artifact not present at freeze time; "
            "the resolved path's sha256 must be verified at launch"
        )

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"rust_source_digest: {report['rust_source_digest']}")
        print(f"loaded_so_path    : {report['loaded_so_path']}")
        print(f"loaded_so_sha256  : {report['loaded_so_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
