#!/usr/bin/env python3
"""Mode histogram over the entries of a directory (symlinks excluded).

Used to reproduce the frozen v1.1 `src` modes exactly: dirs 0555, files
0444/0555, 0 writable entries.  `--clear-write` answers "what would the
histogram be after chmod -R a-w" for a pre-freeze tree, so a freeze can compare
against a derived expectation instead of a hardcoded one.

Exit 0 always (comparison is the caller's job).
"""

from __future__ import annotations

import argparse
import json
import os
import stat
import sys
from pathlib import Path


def histogram(root: Path, clear_write: bool) -> dict:
    counts: dict[str, int] = {}
    writable: list[str] = []
    symlinks = 0

    def record(full: str, st: os.stat_result) -> None:
        mode = st.st_mode & 0o7777
        if clear_write:
            mode &= ~0o222
        kind = "d" if stat.S_ISDIR(st.st_mode) else "f"
        key = f"{mode:04o} {kind}"
        counts[key] = counts.get(key, 0) + 1
        if st.st_mode & 0o222:
            writable.append(full)

    # count the root itself (find <root> -type d includes it)
    try:
        record(str(root), os.lstat(root))
    except OSError:
        pass

    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        for name in list(dirnames):
            full = os.path.join(dirpath, name)
            if os.path.islink(full):
                symlinks += 1
                dirnames.remove(name)
                continue
            try:
                record(full, os.lstat(full))
            except OSError:
                pass
        for name in filenames:
            full = os.path.join(dirpath, name)
            try:
                st = os.lstat(full)
            except OSError:
                continue
            if stat.S_ISLNK(st.st_mode):
                symlinks += 1
                continue
            if not (stat.S_ISREG(st.st_mode) or stat.S_ISDIR(st.st_mode)):
                continue
            record(full, st)
    return {
        "root": str(root),
        "clear_write": clear_write,
        "counts": dict(sorted(counts.items())),
        "total_entries": sum(counts.values()),
        "symlinks_excluded": symlinks,
        "writable_entries": len(writable),
        "writable_sample": writable[:10],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", required=True)
    parser.add_argument("--clear-write", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    report = histogram(Path(args.dir), args.clear_write)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        for key, count in report["counts"].items():
            print(f"{key} {count}")
        print(
            f"TOTAL {report['total_entries']} entries, "
            f"{report['writable_entries']} writable, "
            f"{report['symlinks_excluded']} symlinks excluded",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
