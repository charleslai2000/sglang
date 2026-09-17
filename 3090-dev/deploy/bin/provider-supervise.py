#!/usr/bin/env python3
"""Detached supervisor for the DEV provider server.

Owns two things for the whole lifetime of the server:

  1. the server process, launched as its child, and
  2. the server's console log, written through a secret redactor.

Why a supervisor instead of a shell `>(...)` log filter
-------------------------------------------------------
sglang logs the fully resolved startup config, which includes the plaintext
API key:

    logger.info(f"server_args={server_args.resolved_dict()}")

so the console stream must be filtered.  A process-substitution filter is
tied to the shell that created it and inherits that shell's stdout, so the
long-lived filter keeps the launcher's pipe open forever and `provider-start`
can never be consumed by a pipeline.  This supervisor is started under
`setsid` with its own stdio detached, so it survives the launcher exiting and
never holds the launcher's descriptors.

Key handling
------------
The key is read from the root-only key file with `sudo -n cat` at start-up.
It is deliberately NOT taken from this process's argv or environment: argv is
world-readable through /proc/<pid>/cmdline and the environment through
/proc/<pid>/environ.  The only argv that carries it is the server child's own
`--api-key` argument, which sglang requires and the owner dispatch mandates.

If this supervisor dies, the server's stdout pipe closes and the server sees
EPIPE; it cannot silently continue writing unredacted output into the log.

Usage:
    provider-supervise.py --log L --key-file K --pid-file P [--inject-api-key]
                          -- <server command...>
"""

from __future__ import annotations

import os
import subprocess
import sys

MASK = b"[REDACTED-API-KEY]"
CHUNK = 65536


def parse_argv(argv: list[str]) -> tuple[dict[str, str], bool, list[str]]:
    opts: dict[str, str] = {}
    inject = False
    rest: list[str] = []
    i = 0
    while i < len(argv):
        tok = argv[i]
        if tok == "--":
            rest = argv[i + 1 :]
            break
        if tok == "--inject-api-key":
            inject = True
            i += 1
            continue
        if tok.startswith("--") and i + 1 < len(argv):
            opts[tok[2:]] = argv[i + 1]
            i += 2
            continue
        raise SystemExit(f"provider-supervise: unexpected argument {tok!r}")
    return opts, inject, rest


def read_secret(keyfile: str) -> str:
    proc = subprocess.run(
        ["sudo", "-n", "cat", keyfile],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30,
    )
    if proc.returncode != 0:
        print(
            "provider-supervise: cannot read the key file: "
            + proc.stderr.decode(errors="replace").strip(),
            file=sys.stderr,
        )
        raise SystemExit(2)
    secret = proc.stdout.decode().strip()
    if not secret:
        print("provider-supervise: the key file is empty", file=sys.stderr)
        raise SystemExit(2)
    return secret


def main() -> int:
    opts, inject, cmd = parse_argv(sys.argv[1:])
    for required in ("log", "key-file", "pid-file"):
        if required not in opts:
            print(f"provider-supervise: --{required} is required", file=sys.stderr)
            return 2
    if not cmd:
        print("provider-supervise: no server command given", file=sys.stderr)
        return 2

    secret = read_secret(opts["key-file"])
    if inject:
        # Appended here rather than by the launcher so the key never appears
        # in the launcher's own argv.
        cmd = [*cmd, "--api-key", secret]

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

    needle = secret.encode()
    assert child.stdout is not None
    carry = b""
    try:
        while True:
            chunk = child.stdout.read1(CHUNK)
            if not chunk:
                break
            buf = carry + chunk
            keep = len(needle) - 1
            if len(buf) > keep:
                emit, carry = buf[:-keep], buf[-keep:]
            else:
                emit, carry = b"", buf
            if emit:
                os.write(log_fd, emit.replace(needle, MASK))
        if carry:
            os.write(log_fd, carry.replace(needle, MASK))
    finally:
        os.close(log_fd)

    return child.wait()


if __name__ == "__main__":
    sys.exit(main())
