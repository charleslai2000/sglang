#!/usr/bin/env python3
"""Stage 4b: `IOV_MAX` chunking boundary (charter AMENDMENT 1-D).

Proves the native `pwritev` path never passes more than the runtime `IOV_MAX`
iovecs, shows the boundary exactly at the limit and one over, and shows the
failure the chunker prevents (`EINVAL` from an over-limit single `pwritev`).
"""

from __future__ import annotations

import ctypes
import errno
import json
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _load import load_poc  # noqa: E402

SCRATCH = "/tmp/opencode/l3-native-poc-20260916"
IOV_BYTES = 16


def make_arena(count: int):
    total = count * IOV_BYTES
    arena = bytearray(total)
    for i in range(total):
        arena[i] = (i * 7 + 3) & 0xFF
    ctype = (ctypes.c_char * total).from_buffer(arena)
    base = ctypes.addressof(ctype)
    pairs = [(base + i * IOV_BYTES, IOV_BYTES) for i in range(count)]
    return arena, ctype, base, pairs, bytes(arena)


def main() -> None:
    module = load_poc()
    report: dict = {}

    # --- 1. the runtime limit, three independent sources ---
    native_limit = module.iov_max()
    python_limit = os.sysconf("SC_IOV_MAX")
    getconf = subprocess.run(
        ["getconf", "IOV_MAX"], capture_output=True, text=True, check=True
    ).stdout.strip()
    report["iov_max"] = {
        "native_sysconf": native_limit,
        "python_os_sysconf": python_limit,
        "getconf_IOV_MAX": int(getconf),
        "all_agree": native_limit == python_limit == int(getconf),
    }
    assert report["iov_max"]["all_agree"], report["iov_max"]

    # --- 2. chunk plan boundary table ---
    boundary = {}
    for count in (0, 1, 1023, 1024, 1025, 2048, 2049, 1_000_000):
        plan = module.plan_iovec_chunks(count, 0)
        boundary[str(count)] = {
            "chunks": len(plan),
            "first_chunk": list(plan[0]) if plan else None,
            "last_chunk": list(plan[-1]) if plan else None,
            "max_chunk": max((n for _, n in plan), default=0),
        }
    report["plan_boundary"] = boundary
    assert boundary["1024"]["chunks"] == 1
    assert boundary["1025"]["chunks"] == 2
    assert boundary["1025"]["last_chunk"] == [1024, 1]
    assert boundary["2048"]["chunks"] == 2
    assert boundary["2049"]["chunks"] == 3
    assert boundary["0"]["chunks"] == 0
    assert boundary["1000000"]["max_chunk"] == 1024

    # A caller-supplied limit above the runtime one is clamped, not honoured.
    report["clamping"] = {
        "requested_1_000_000": {
            "chunks": len(module.plan_iovec_chunks(1025, 1_000_000)),
            "max_chunk": max(n for _, n in module.plan_iovec_chunks(1025, 1_000_000)),
        },
        "requested_1025_one_over": {
            "chunks": len(module.plan_iovec_chunks(1025, 1025)),
            "max_chunk": max(n for _, n in module.plan_iovec_chunks(1025, 1025)),
        },
        "requested_512_under": {
            "chunks": len(module.plan_iovec_chunks(1025, 512)),
            "max_chunk": max(n for _, n in module.plan_iovec_chunks(1025, 512)),
        },
    }
    assert report["clamping"]["requested_1_000_000"]["max_chunk"] == 1024
    assert report["clamping"]["requested_1025_one_over"]["max_chunk"] == 1024
    assert report["clamping"]["requested_512_under"]["chunks"] == 3

    # --- 3. the boundary is real: os.writev EINVAL past 1024 iovecs ---
    writev_boundary = {}
    for count in (1023, 1024, 1025):
        read_fd, write_fd = os.pipe()
        try:
            written = os.writev(write_fd, [b"x" * IOV_BYTES] * count)
            writev_boundary[str(count)] = {"ok": True, "bytes": written}
        except OSError as exc:
            writev_boundary[str(count)] = {
                "ok": False,
                "errno": exc.errno,
                "errno_name": errno.errorcode.get(exc.errno, str(exc.errno)),
            }
        finally:
            os.close(read_fd)
            os.close(write_fd)
    report["os_writev_boundary"] = writev_boundary
    assert writev_boundary["1024"]["ok"] is True
    assert writev_boundary["1025"]["ok"] is False
    assert writev_boundary["1025"]["errno_name"] == "EINVAL"

    # --- 4. native unchunked negative control vs chunked path ---
    with tempfile.TemporaryDirectory(dir=SCRATCH, prefix="iovtest-") as tmp:
        unchunked = {}
        for count in (1024, 1025):
            arena, _ctype, _base, pairs, _expected = make_arena(count)
            path = os.path.join(tmp, f"unchunked-{count}.bin")
            fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_TRUNC, 0o644)
            try:
                module.pwritev_unchunked(fd, pairs)
                unchunked[str(count)] = {"ok": True}
            except ValueError as exc:
                unchunked[str(count)] = {"ok": False, "message": str(exc)}
            finally:
                os.close(fd)
        report["native_unchunked_negative_control"] = unchunked
        assert unchunked["1024"]["ok"] is True
        assert unchunked["1025"]["ok"] is False, unchunked
        # Rust's io::Error renders errno 22 as "Invalid argument (os error 22)".
        assert "os error 22" in unchunked["1025"]["message"], unchunked

        chunked = {}
        for count in (1024, 1025, 2049):
            arena, _ctype, _base, pairs, expected = make_arena(count)
            path = os.path.join(tmp, f"chunked-{count}.bin")
            fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_TRUNC, 0o644)
            try:
                plan_report, total = module.pwritev_chunked(fd, pairs)
            finally:
                os.close(fd)
            with open(path, "rb") as handle:
                on_disk = handle.read()
            chunked[str(count)] = {
                "iovec_count": count,
                "expected_bytes": len(expected),
                "bytes_written": total,
                "chunk_report": [list(row) for row in plan_report],
                "chunks": len(plan_report),
                "max_iovecs_per_call": max(row[1] for row in plan_report),
                "round_trip_byte_identical": on_disk == expected,
            }
            assert total == len(expected), chunked[str(count)]
            assert on_disk == expected, chunked[str(count)]
            assert max(row[1] for row in plan_report) <= native_limit
        report["native_pwritev_chunked"] = chunked
        assert chunked["1024"]["chunks"] == 1
        assert chunked["1025"]["chunks"] == 2
        assert chunked["1025"]["chunk_report"] == [[0, 1024, 16384], [1024, 1, 16]]
        assert chunked["2049"]["chunks"] == 3

    print(json.dumps(report, indent=2))
    print("STAGE4_IOV_OK")


if __name__ == "__main__":
    main()
