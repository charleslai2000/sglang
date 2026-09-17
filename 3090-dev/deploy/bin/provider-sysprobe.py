#!/usr/bin/env python3
"""Small, dependency-free system probes used by the provider scripts.

Subcommands
-----------
lock-state <lockpath>   print "free" or "held" (non-blocking flock probe)
gpu-ordinal <uuid>      print the CUDA ordinal that maps to a GPU UUID
port-free <host> <port> print "free", or "busy" and exit 1

The GPU check exists because NVML index and CUDA ordinal are inverted on this
box: pinning `CUDA_VISIBLE_DEVICES=1` has previously landed on the wrong
device.  We resolve the ordinal from the UUID at start time instead of
hardcoding an index.
"""

from __future__ import annotations

import fcntl
import os
import socket
import sys


def lock_state(path: str) -> int:
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print("held")
    else:
        fcntl.flock(fd, fcntl.LOCK_UN)
        print("free")
    finally:
        os.close(fd)
    return 0


def gpu_ordinal(uuid: str) -> int:
    """CUDA_VISIBLE_DEVICES=GPU-<uuid> is not valid; we need the numeric ordinal."""
    try:
        import pynvml
    except ImportError:
        print("PROBE_FAIL: pynvml unavailable", file=sys.stderr)
        return 2
    try:
        import torch
    except ImportError:
        print("PROBE_FAIL: torch unavailable", file=sys.stderr)
        return 2

    want = uuid[len("GPU-") :] if uuid.startswith("GPU-") else uuid
    pynvml.nvmlInit()
    try:
        count = pynvml.nvmlDeviceGetCount()
        # CUDA orders devices by PCI bus id (unless pinned otherwise); NVML
        # index order matches torc's default ordering on this host, but we
        # cross-check against torch before trusting it.
        for idx in range(count):
            handle = pynvml.nvmlDeviceGetHandleByIndex(idx)
            got = pynvml.nvmlDeviceGetUUID(handle)
            got = got[len("GPU-") :] if got.startswith("GPU-") else got
            if got == want:
                if not torch.cuda.is_available():
                    print("PROBE_FAIL: torch reports no CUDA device", file=sys.stderr)
                    return 2
                if torch.cuda.device_count() != count:
                    print(
                        "PROBE_FAIL: torch device_count=%d but NVML count=%d"
                        % (torch.cuda.device_count(), count),
                        file=sys.stderr,
                    )
                    return 2
                print(idx)
                return 0
    finally:
        pynvml.nvmlShutdown()
    print(f"PROBE_FAIL: no GPU with UUID {uuid}", file=sys.stderr)
    return 2


def port_free(host: str, port: int) -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        s.bind((host, port))
    except OSError as exc:
        print(f"busy: {exc}")
        return 1
    finally:
        s.close()
    print("free")
    return 0


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: provider-sysprobe.py <lock-state|gpu-ordinal|port-free> ...",
              file=sys.stderr)
        return 2
    cmd, rest = sys.argv[1], sys.argv[2:]
    if cmd == "lock-state":
        return lock_state(rest[0])
    if cmd == "gpu-ordinal":
        return gpu_ordinal(rest[0])
    if cmd == "port-free":
        return port_free(rest[0], int(rest[1]))
    print(f"unknown subcommand {cmd!r}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
