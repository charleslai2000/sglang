#!/usr/bin/env python3
"""Stream redactor for the DEV provider's server console log.

Why this exists
---------------
`sglang` logs the fully resolved startup configuration at launch:

    logger.info(f"server_args={server_args.resolved_dict()}")
    (sglang/srt/entrypoints/engine.py, _launch_subprocesses)

`resolved_dict()` contains the plaintext `api_key`.  Verified on this tree:

    >>> args.resolved_dict()["api_key"] == "<the key passed on the CLI>"

Without this filter the API key would land in the provider console log in
cleartext, which the owner directive forbids.

Secret handling
---------------
The key is read from the root-only key file with `sudo -n cat` at start-up.
It is deliberately NOT taken from this process's environment: a child's
environment is world-readable through /proc/<pid>/environ, and the redactor
outlives the launcher.  Reading the file here means the only in-memory copy
is inside this short-lived filter.

The redactor also never writes the key anywhere.  If it dies, the server's
stdout pipe closes and the server sees EPIPE rather than silently logging
unredacted output to a file.

Streaming
---------
Uses read1() rather than read(): read() on a pipe blocks until the buffer
is full or EOF, which delays log visibility by minutes and would defeat the
fail-closed startup checks that scan this log for evidence lines.
"""

from __future__ import annotations

import os
import subprocess
import sys

MASK = b"[REDACTED-API-KEY]"
CHUNK = 65536


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: provider-log-redactor.py <logfile> <api-key-file>", file=sys.stderr)
        return 2
    logfile, keyfile = sys.argv[1], sys.argv[2]

    proc = subprocess.run(
        ["sudo", "-n", "cat", keyfile],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30,
    )
    if proc.returncode != 0:
        print(
            "provider-log-redactor: cannot read key file: "
            + proc.stderr.decode(errors="replace").strip(),
            file=sys.stderr,
        )
        return 2
    secret = proc.stdout.decode().strip()
    if not secret:
        print("provider-log-redactor: key file is empty", file=sys.stderr)
        return 2
    needle = secret.encode()

    out_fd = os.open(logfile, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    # Bytes that may be the start of a secret straddling a read boundary.
    carry = b""
    inp = sys.stdin.buffer
    try:
        while True:
            chunk = inp.read1(CHUNK)
            if not chunk:
                break
            buf = carry + chunk
            keep = len(needle) - 1
            if len(buf) > keep:
                emit, carry = buf[:-keep], buf[-keep:]
            else:
                emit, carry = b"", buf
            if emit:
                os.write(out_fd, emit.replace(needle, MASK))
        if carry:
            os.write(out_fd, carry.replace(needle, MASK))
    finally:
        os.close(out_fd)
    return 0


if __name__ == "__main__":
    sys.exit(main())
