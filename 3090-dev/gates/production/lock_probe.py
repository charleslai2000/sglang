#!/usr/bin/env python3
"""Fresh-process canonical-lock probe (stdlib only).

Usage: lock_probe.py <lock_path>

Opens the lock file in a brand-new process (no inherited fd) and attempts a
non-blocking exclusive flock.  Prints one JSON line:

    {"locked": <bool>, "holder": <raw lock-file text>, "pid": <probe pid>}

``locked=true`` means some other process currently owns the lock.  This is used
to prove the gate DRIVER -- not a server it launched -- holds the lock
generation, including across a server SIGTERM.
"""
from __future__ import annotations

import fcntl
import json
import os
import sys


def main() -> int:
    path = sys.argv[1]
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_CLOEXEC, 0o644)
    locked = False
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        locked = True
    holder = None
    try:
        os.lseek(fd, 0, os.SEEK_SET)
        holder = os.read(fd, 4096).decode("utf-8", "replace").strip()
    except OSError:
        pass
    if not locked:
        # Do not leave the probe holding the lock.
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        except OSError:
            pass
    os.close(fd)
    print(json.dumps({"locked": locked, "holder": holder,
                      "pid": os.getpid()}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
