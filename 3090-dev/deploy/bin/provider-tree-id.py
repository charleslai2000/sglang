#!/usr/bin/env python3
"""Deployed-tree identity for the DEV provider.

Verifies that the deployed tree is a byte-exact export of a pinned git
commit.  Two modes:

    write  export time -- verify every tracked deployed file against the
           commit's blob, digest the staged build artifacts, reject unexpected
           extras, and record MANIFEST-provider-tree.tsv.
    check  every start -- recompute the deployed files and compare against the
           recorded manifest, so a later hand-edit or partial overwrite in
           /opt is caught before anything is launched.

Why artifacts are handled separately
------------------------------------
`git archive` can only carry tracked bytes.  Three Rust extension `.so`
files and `python/sglang/_version.py` are gitignored build outputs that the
proven frozen production tree also ships.  They are staged into the deploy
tree from the live worktree and pinned here by sha256, so a later change to
them in /opt is still detected.  None of them is exercised by this serving
profile (no --grpc-port, no SGLANG_RUST_SERVER, no Inkling model); staging
them keeps the layout identical to the proven tree and prevents an
accidental cargo build at import time.

Hashing rules
-------------
* Tracked files use git's own blob hash (sha1 over "blob <len>\\0<content>"),
  so the comparison needs no working-tree assumptions.
* Symlink entries (mode 120000) hash their target string.
* Paths come from `git ls-tree -z` because this repo has filenames with
  spaces, commas and brackets.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys

SUBTREE = "python/sglang"
MANIFEST_NAME = "MANIFEST-provider-tree.tsv"
SKIP_DIRS = {"__pycache__", ".pytest_cache"}
KIND_ARTIFACT = "artifact"


def git(*args: str) -> bytes:
    proc = subprocess.run(
        ["git", *args], stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    if proc.returncode != 0:
        raise SystemExit(
            "IDENTITY_FAIL: git %s failed: %s"
            % (" ".join(args), proc.stderr.decode(errors="replace").strip())
        )
    return proc.stdout


def git_blob_sha(content: bytes) -> str:
    h = hashlib.sha1()
    h.update(b"blob %d\0" % len(content))
    h.update(content)
    return h.hexdigest()


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def expected_entries(repo: str, commit: str) -> dict[str, tuple[str, str]]:
    """{path: (git_mode, blob_sha)} for tracked files under SUBTREE."""
    raw = git("-C", repo, "ls-tree", "-r", "-z", commit, "--", SUBTREE)
    entries: dict[str, tuple[str, str]] = {}
    for rec in raw.split(b"\0"):
        if not rec:
            continue
        meta, path = rec.split(b"\t", 1)
        fmode, _ftype, sha = meta.split(b" ")
        entries[path.decode()] = (fmode.decode(), sha.decode())
    return entries


def digest(deploy: str, path: str, kind: str) -> str:
    """Hash one deployed path. kind is a git mode, or 'artifact'."""
    full = os.path.join(deploy, path)
    if not os.path.lexists(full):
        raise SystemExit(f"IDENTITY_FAIL: missing deployed file {path}")
    if kind == KIND_ARTIFACT:
        if os.path.islink(full) or not os.path.isfile(full):
            raise SystemExit(f"IDENTITY_FAIL: artifact {path} is not a regular file")
        return sha256_file(full)
    if kind == "120000":
        if not os.path.islink(full):
            raise SystemExit(f"IDENTITY_FAIL: {path} is not a symlink in the deploy tree")
        return git_blob_sha(os.readlink(full).encode())
    if os.path.islink(full):
        raise SystemExit(f"IDENTITY_FAIL: {path} is a symlink in the deploy tree")
    if not os.path.isfile(full):
        raise SystemExit(f"IDENTITY_FAIL: {path} is not a regular file")
    with open(full, "rb") as fh:
        return git_blob_sha(fh.read())


def deployed_paths(deploy: str) -> set[str]:
    found: set[str] = set()
    for dirpath, dirnames, filenames in os.walk(os.path.join(deploy, SUBTREE)):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            if name.endswith((".pyc", ".pyo")):
                continue
            found.add(os.path.relpath(os.path.join(dirpath, name), deploy))
    return found


def fail_report(bad: list[tuple[str, str, str]], extra: set[str]) -> None:
    for path, want, got in bad[:5]:
        print(f"IDENTITY_FAIL: {path} expected={want} actual={got}", file=sys.stderr)
    for item in sorted(extra)[:5]:
        print(f"IDENTITY_FAIL: unexpected file in deploy tree: {item}", file=sys.stderr)


def read_manifest(manifest: str) -> dict[str, tuple[str, str]]:
    rec: dict[str, tuple[str, str]] = {}
    with open(manifest) as fh:
        for line in fh:
            sha, kind, path = line.rstrip("\n").split("\t", 2)
            rec[path] = (kind, sha)
    return rec


def main() -> int:
    if len(sys.argv) < 6:
        print(
            "usage: provider-tree-id.py <write|check> <deploy> <commit> <repo> "
            "<artifact> [<artifact> ...]",
            file=sys.stderr,
        )
        return 2
    mode, deploy, commit, repo = sys.argv[1:5]
    artifacts = list(dict.fromkeys(sys.argv[5:]))
    manifest = os.path.join(deploy, MANIFEST_NAME)

    tracked = expected_entries(repo, commit)
    if not tracked:
        raise SystemExit(f"IDENTITY_FAIL: commit {commit} has no {SUBTREE} entries")

    if mode == "write":
        bad: list[tuple[str, str, str]] = []
        for path, (kind, sha) in tracked.items():
            got = digest(deploy, path, kind)
            if got != sha:
                bad.append((path, sha, got))
        art: dict[str, str] = {}
        for path in artifacts:
            art[path] = digest(deploy, path, KIND_ARTIFACT)
        allowed = set(tracked) | set(art)
        extra = deployed_paths(deploy) - allowed
        if bad or extra:
            fail_report(bad, extra)
            raise SystemExit(
                f"IDENTITY_FAIL: {len(bad)} mismatched, {len(extra)} unexpected"
            )
        tmp = manifest + ".tmp"
        with open(tmp, "w") as fh:
            for path, (kind, sha) in tracked.items():
                fh.write(f"{sha}\t{kind}\t{path}\n")
            for path, sha in art.items():
                fh.write(f"{sha}\t{KIND_ARTIFACT}\t{path}\n")
        os.replace(tmp, manifest)
        print(
            f"IDENTITY_OK tracked={len(tracked)} artifacts={len(art)} commit={commit}"
        )
        return 0

    if mode != "check":
        print(f"unknown mode {mode!r}", file=sys.stderr)
        return 2
    if not os.path.isfile(manifest):
        raise SystemExit("IDENTITY_FAIL: no manifest in deploy tree; re-export required")

    rec = read_manifest(manifest)
    if set(rec) != set(tracked) | set(artifacts):
        raise SystemExit(
            "IDENTITY_FAIL: manifest does not describe the pinned commit plus "
            "the expected artifacts (tree layout changed; re-export required)"
        )
    bad = []
    for path, (kind, sha) in rec.items():
        got = digest(deploy, path, kind)
        if got != sha:
            bad.append((path, sha, got))
    extra = deployed_paths(deploy) - set(rec)
    if bad or extra:
        fail_report(bad, extra)
        raise SystemExit(
            f"IDENTITY_FAIL: {len(bad)} file(s) changed since export, "
            f"{len(extra)} unexpected"
        )
    print(f"IDENTITY_OK files={len(rec)} commit={commit}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
