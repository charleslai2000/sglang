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


def nvml_order() -> list[tuple[int, str]]:
    """[(nvml_index, uuid)] in NVML order."""
    try:
        import pynvml
    except ImportError:
        return []
    pynvml.nvmlInit()
    try:
        out = []
        for idx in range(pynvml.nvmlDeviceGetCount()):
            handle = pynvml.nvmlDeviceGetHandleByIndex(idx)
            out.append((idx, pynvml.nvmlDeviceGetUUID(handle)))
        return out
    finally:
        pynvml.nvmlShutdown()


def cuda_visible_order() -> list[str]:
    """UUIDs in CUDA_VISIBLE_DEVICES order as torch enumerates them."""
    import torch

    out = []
    for idx in range(torch.cuda.device_count()):
        props = torch.cuda.get_device_properties(idx)
        raw = getattr(props, "uuid", None)
        if raw is None:
            raise RuntimeError(f"torch exposes no uuid for device {idx}")
        out.append(raw if str(raw).startswith("GPU-") else f"GPU-{raw}")
    return out


def gpu_ordinal(uuid: str) -> int:
    """Print the CUDA ordinal whose device UUID matches `uuid`.

    NVML index and CUDA ordinal are inverted on this box, so the ordinal is
    resolved by identity rather than assumed.  Both NVML and torch are
    consulted, and they must agree, because the server is pinned by whatever
    CUDA sees inside its own processes.
    """
    import torch

    if not torch.cuda.is_available():
        print("PROBE_FAIL: torch reports no CUDA device", file=sys.stderr)
        return 2
    cuda_uuids = cuda_visible_order()
    if uuid not in cuda_uuids:
        print(
            f"PROBE_FAIL: {uuid} not among CUDA devices {cuda_uuids}",
            file=sys.stderr,
        )
        return 2
    ordinal = cuda_uuids.index(uuid)

    nvml = nvml_order()
    if nvml:
        nvml_uuids = [u for _i, u in nvml]
        if uuid not in nvml_uuids:
            print(f"PROBE_FAIL: {uuid} not among NVML devices {nvml_uuids}",
                  file=sys.stderr)
            return 2
        nvml_index = nvml_uuids.index(uuid)
        if nvml_index != ordinal:
            # Not fatal, but recorded: the pin below is the CUDA ordinal.
            print(
                f"note: NVML index {nvml_index} != CUDA ordinal {ordinal} "
                f"for {uuid}",
                file=sys.stderr,
            )
    print(ordinal)
    return 0


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
