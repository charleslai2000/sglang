#!/usr/bin/env python3
"""Per-run L3 store namespace policy for the LOCAL-PROD runtime line.

Frozen policy
-------------

One task/run -> one unique L3 store namespace.  The launch-time store is
``<root>/<SGLANG_RUN_ID>`` with ``root`` defaulting to ``/data/l3``.

A run must never use, adopt, clear or delete a *shared* store: clearing a shared
store unlinks the previous task's WAL segment and destroys concurrent durability
evidence.  This tool therefore has no clear/delete code path at all; it only
allocates (once, with a claim) and validates.  A namespace whose directory
already exists without a claim, or with somebody else's claim, is refused.

This module is the single implementation of the policy.  ``bin/freeze.sh``
installs it verbatim into the frozen tree as ``<tree>/tools/l3_namespace.py``
(and verifies the installed copy's sha256), so the launcher's own gate and the
external ``bin/preflight.sh`` enforce identical rules rather than two divergent
copies.

Exit codes
----------
  0  ok
  2  usage error
  3  invalid task/run id
  4  reserved / shared namespace refused (e.g. local-prod-v1.1)
  5  resolved path escapes the namespace root
  6  store is not run-unique: pre-existing unclaimed store, or not allocated
  7  namespace path (or a parent) is a symlink
  8  claim mismatch (task id / tree digest / resume token)
  9  path is not unique to the run (basename != run id, or collision)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_ROOT = "/data/l3"
CLAIM_NAME = ".run-claim.json"

#: Namespaces reserved for the frozen production candidates.  These are shared
#: by definition (all runs of a candidate point at them) and are exactly the
#: stores that must never be cleared by a run.
RESERVED_PREFIXES = ("local-prod-",)
RESERVED_EXACT = frozenset(
    {"shared", "default", "common", "prod", "production", "l3", "data"}
)

TASK_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


class PolicyError(Exception):
    def __init__(self, code: int, message: str, **detail):
        super().__init__(message)
        self.code = code
        self.message = message
        self.detail = detail


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def check_task_id(task_id: str) -> None:
    if not task_id:
        raise PolicyError(3, "run/task id is empty")
    if not TASK_ID_RE.match(task_id):
        raise PolicyError(
            3,
            f"invalid run/task id {task_id!r}: must match {TASK_ID_RE.pattern}",
        )
    lowered = task_id.lower()
    if lowered in RESERVED_EXACT or lowered.startswith(RESERVED_PREFIXES):
        raise PolicyError(
            4,
            f"reserved/shared namespace refused: {task_id!r} "
            f"(prefixes={RESERVED_PREFIXES}, exact={sorted(RESERVED_EXACT)}). "
            "One task/run -> one unique store; a shared store must never be "
            "used or cleared by a run.",
        )
    if task_id in {".", ".."}:
        raise PolicyError(3, f"invalid run/task id {task_id!r}")


def resolve_namespace(root: str, task_id: str) -> tuple[Path, Path]:
    check_task_id(task_id)
    root_p = Path(root)
    if not root_p.is_absolute():
        raise PolicyError(2, f"--root must be absolute, got {root!r}")
    raw = root_p / task_id
    # A symlinked namespace (or symlinked component below the root) is never
    # acceptable: it can silently alias a shared store.  Checked on the raw
    # path, before resolve() follows anything.
    probe = raw
    while probe != root_p and probe.parent != probe:
        if os.path.islink(probe):
            raise PolicyError(7, f"namespace path component is a symlink: {probe}")
        probe = probe.parent
    root_r = root_p.resolve()
    path_r = raw.resolve()
    if path_r == root_r or root_r not in path_r.parents:
        raise PolicyError(
            5, f"namespace {raw} escapes the namespace root {root_p}"
        )
    if path_r.name != task_id:
        raise PolicyError(
            9, f"namespace basename {path_r.name!r} != run id {task_id!r}"
        )
    return raw, path_r


def read_claim(path: Path) -> dict | None:
    claim = path / CLAIM_NAME
    if not claim.is_file():
        return None
    try:
        return json.loads(claim.read_text())
    except (OSError, ValueError) as exc:
        raise PolicyError(8, f"unreadable claim {claim}: {exc}") from exc


def write_claim(path: Path, payload: dict) -> None:
    claim = path / CLAIM_NAME
    tmp = path / f"{CLAIM_NAME}.tmp.{os.getpid()}"
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    os.chmod(tmp, 0o644)
    os.replace(tmp, claim)


def directory_entries(path: Path) -> list[str]:
    try:
        return [e for e in os.listdir(path) if e != CLAIM_NAME]
    except OSError:
        return []


def build_claim(task_id: str, tree_digest: str | None, nonce: str, root: Path) -> dict:
    return {
        "policy": "one task/run -> one unique L3 store namespace",
        "task_id": task_id,
        "run_id": task_id,
        "namespace": str(root / task_id),
        "nonce": nonce,
        "tree_digest": tree_digest or "",
        "host": os.uname().nodename,
        "created_at_utc": now_utc(),
        "allocated_by_pid": os.getpid(),
    }


def validate(
    root: str,
    task_id: str,
    path: str | None,
    expect_tree_digest: str | None,
    resume_token: str | None,
) -> dict:
    raw, path_r = resolve_namespace(root, task_id)
    if path is not None:
        supplied = Path(path)
        if not supplied.is_absolute():
            raise PolicyError(2, f"--path must be absolute, got {path!r}")
        if supplied.resolve() != path_r:
            raise PolicyError(
                9,
                f"supplied namespace {supplied} is not unique to run {task_id!r} "
                f"(expected {path_r})",
            )
    if not path_r.exists():
        raise PolicyError(
            6,
            f"L3 store {path_r} is not allocated for run {task_id!r}; "
            "allocate it before launching (this run must own its namespace)",
        )
    if not path_r.is_dir():
        raise PolicyError(6, f"L3 store {path_r} exists but is not a directory")
    claim = read_claim(path_r)
    if claim is None:
        entries = directory_entries(path_r)
        raise PolicyError(
            6,
            f"L3 store {path_r} is a pre-existing store with no run claim"
            + (f" and {len(entries)} entries" if entries else "")
            + "; refusing to adopt a store that may be another run's (clearing "
            "it would destroy that run's WAL/durability evidence)",
        )
    if claim.get("task_id") != task_id:
        raise PolicyError(
            8,
            f"L3 store {path_r} is claimed by run {claim.get('task_id')!r}, "
            f"not {task_id!r}",
        )
    if expect_tree_digest and claim.get("tree_digest") not in ("", expect_tree_digest):
        raise PolicyError(
            8,
            f"L3 store {path_r} is claimed for tree digest "
            f"{claim.get('tree_digest')!r}, not {expect_tree_digest!r}",
        )
    if resume_token is not None and claim.get("nonce") != resume_token:
        raise PolicyError(8, f"resume token does not match the claim on {path_r}")
    return {
        "action": "validate",
        "task_id": task_id,
        "namespace": str(path_r),
        "claim": claim,
        "result": "PASS",
    }


def allocate(
    root: str,
    task_id: str,
    path: str | None,
    expect_tree_digest: str | None,
    resume_token: str | None,
) -> dict:
    raw, path_r = resolve_namespace(root, task_id)
    if path is not None:
        supplied = Path(path)
        if not supplied.is_absolute():
            raise PolicyError(2, f"--path must be absolute, got {path!r}")
        if supplied.resolve() != path_r:
            raise PolicyError(
                9,
                f"supplied namespace {supplied} is not unique to run {task_id!r} "
                f"(expected {path_r})",
            )
    root_r = Path(root).resolve()
    root_r.mkdir(parents=True, exist_ok=True)

    if path_r.exists() and not path_r.is_dir():
        raise PolicyError(6, f"namespace {path_r} exists and is not a directory")

    if path_r.exists():
        claim = read_claim(path_r)
        entries = directory_entries(path_r)
        if claim is None:
            if entries:
                raise PolicyError(
                    6,
                    f"refusing to adopt pre-existing non-empty L3 store {path_r} "
                    f"({len(entries)} entries, no claim): it may belong to another "
                    "run and must never be cleared",
                )
            path_r.mkdir(parents=True, exist_ok=True)
            nonce = resume_token or secrets.token_hex(8)
            payload = build_claim(task_id, expect_tree_digest, nonce, root_r)
            write_claim(path_r, payload)
            return {
                "action": "allocate",
                "task_id": task_id,
                "namespace": str(path_r),
                "claim": payload,
                "note": "adopted an existing empty directory",
                "result": "PASS",
            }
        # claimed already: only an explicit matching resume token may re-enter.
        if claim.get("task_id") != task_id:
            raise PolicyError(
                6,
                f"L3 store {path_r} is already claimed by another run "
                f"({claim.get('task_id')!r}); refusing",
            )
        if resume_token is None or claim.get("nonce") != resume_token:
            raise PolicyError(
                6,
                f"L3 store {path_r} is already claimed by run {task_id!r} "
                "(pass --resume-token <nonce> to re-enter the same run); "
                "refusing to reuse a store from a previous run",
            )
        if expect_tree_digest and claim.get("tree_digest") not in ("", expect_tree_digest):
            raise PolicyError(8, f"resume token matches but tree digest differs on {path_r}")
        return {
            "action": "resume",
            "task_id": task_id,
            "namespace": str(path_r),
            "claim": claim,
            "result": "PASS",
        }

    path_r.mkdir(parents=True, exist_ok=False)
    os.chmod(path_r, 0o755)
    nonce = resume_token or secrets.token_hex(8)
    payload = build_claim(task_id, expect_tree_digest, nonce, root_r)
    write_claim(path_r, payload)
    return {
        "action": "allocate",
        "task_id": task_id,
        "namespace": str(path_r),
        "claim": payload,
        "result": "PASS",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--allocate", action="store_true")
    mode.add_argument("--validate", action="store_true")
    parser.add_argument("--task-id", required=True, help="unique run/task id = L3 namespace name")
    parser.add_argument("--root", default=DEFAULT_ROOT, help="namespace root (default /data/l3)")
    parser.add_argument("--path", default=None, help="assert the namespace equals this path")
    parser.add_argument("--expect-tree-digest", default=None)
    parser.add_argument("--resume-token", default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    try:
        report = {
            "root": args.root,
            "policy": "one task/run -> one unique L3 store namespace",
        }
        report.update(
            allocate(
                args.root, args.task_id, args.path, args.expect_tree_digest, args.resume_token
            )
            if args.allocate
            else validate(
                args.root, args.task_id, args.path, args.expect_tree_digest, args.resume_token
            )
        )
    except PolicyError as exc:
        report = {
            "result": "REFUSE",
            "exit_code": exc.code,
            "error": exc.message,
            "task_id": args.task_id,
            "root": args.root,
            **exc.detail,
        }
        if args.json:
            print(json.dumps(report, indent=2, sort_keys=True))
        else:
            print(f"L3-NAMESPACE REFUSE (exit {exc.code}): {exc.message}", file=sys.stderr)
        return exc.code

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(
            f"L3-NAMESPACE PASS: {report['action']} {report['namespace']} "
            f"(task_id={report['task_id']})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
