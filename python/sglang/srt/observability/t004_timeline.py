"""Run-scoped T004 CPU/NVTX timeline observations.

This module is inert unless both an explicit marker file and output path are
provided. NVTX ranges are created and closed on the calling thread; it never
opens a range across a thread boundary.
"""
from __future__ import annotations

import contextlib
import json
import os
import threading
import time
from pathlib import Path
from typing import Iterator

_write_lock = threading.Lock()


def enabled() -> bool:
    marker = os.environ.get("T004_TIMELINE_MARKER", "")
    return bool(marker and os.environ.get("T004_TIMELINE_LOG") and Path(marker).is_file())


def emit(event: str, **fields) -> None:
    if not enabled():
        return
    mono_before = time.monotonic_ns()
    wall_ns = time.time_ns()
    mono_after = time.monotonic_ns()
    row = {
        "schema": "t004_timeline.v1",
        "evt": event,
        "ts_mono_ns": (mono_before + mono_after) // 2,
        "mono_bracket_ns": [mono_before, mono_after],
        "ts_wall_ns": wall_ns,
        "pid": os.getpid(),
        "tid": threading.get_native_id(),
        **fields,
    }
    target = Path(os.environ["T004_TIMELINE_LOG"])
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(row, sort_keys=True, separators=(",", ":"), default=str)
    with _write_lock, target.open("a", encoding="utf-8") as stream:
        stream.write(payload + "\n")


@contextlib.contextmanager
def nvtx_range(name: str) -> Iterator[None]:
    """A same-thread NVTX range; disabled runs do not import nvtx."""
    if not enabled():
        yield
        return
    try:
        import nvtx
    except ImportError as exc:
        raise RuntimeError("T004 timeline requested but nvtx is unavailable") from exc
    with nvtx.annotate(name):
        yield
