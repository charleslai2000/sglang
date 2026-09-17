#!/usr/bin/env python3
"""Detached supervisor for the DEV provider server.

Owns two things for the whole lifetime of the server:

  1. the server process, launched as its child, and
  2. the server's console log.

Why a supervisor instead of plain backgrounding
-----------------------------------------------
A process-substitution log filter is tied to the shell that created it and
inherits that shell's stdout, so a long-lived filter keeps the launcher's
pipe open forever and `provider-start` can never be consumed by a pipeline.
This supervisor is started under `setsid` with its own stdio detached, so it
survives the launcher exiting and never holds the launcher's descriptors.

AUTH
----
By owner ruling (2026-09-17) this is a private LAN (192.168.20.0/24) and an
API key is NOT required.  This supervisor knows nothing about keys: it passes
no --api-key and no --config, and it never reads api-key.txt.  A leftover key
file from the earlier auth experiment is deliberately ignored.

Usage:
    provider-supervise.py --log L --pid-file P -- <server command...>
"""

from __future__ import annotations

import os
import subprocess
import sys

CHUNK = 65536


def parse_argv(argv: list[str]) -> tuple[dict[str, str], list[str]]:
    opts: dict[str, str] = {}
    rest: list[str] = []
    i = 0
    while i < len(argv):
        tok = argv[i]
        if tok == "--":
            rest = argv[i + 1 :]
            break
        if tok.startswith("--") and i + 1 < len(argv):
            opts[tok[2:]] = argv[i + 1]
            i += 2
            continue
        raise SystemExit(f"provider-supervise: unexpected argument {tok!r}")
    return opts, rest


def main() -> int:
    opts, cmd = parse_argv(sys.argv[1:])
    for required in ("log", "pid-file"):
        if required not in opts:
            print(f"provider-supervise: --{required} is required", file=sys.stderr)
            return 2
    if not cmd:
        print("provider-supervise: no server command given", file=sys.stderr)
        return 2

    log_fd = os.open(opts["log"], os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)

    child = subprocess.Popen(
        cmd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        cwd="/tmp",  # avoid cwd shadowing `import sglang`
        close_fds=True,
    )
    # Record the SERVER's pid (not ours) so provider-stop can identity-check
    # and signal the real process.
    tmp = opts["pid-file"] + ".tmp"
    with open(tmp, "w") as fh:
        fh.write(str(child.pid))
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, opts["pid-file"])

    assert child.stdout is not None
    try:
        while True:
            chunk = child.stdout.read1(CHUNK)
            if not chunk:
                break
            os.write(log_fd, chunk)
    finally:
        os.close(log_fd)

    return child.wait()


if __name__ == "__main__":
    sys.exit(main())
