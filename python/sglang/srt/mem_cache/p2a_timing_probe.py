"""P2-A observation-only timing probe (FROZEN contract, default OFF).

This module implements the frozen P2-A measurement marks:

* M1 ``enqueue_mono_ns`` -- ``scheduler.py`` ``_add_request_to_queue``.
* M2 ``prefetch_issue_mono_ns`` -- ``unified_radix_cache.py``
  ``evt=prefetch_issued``.
* M3 storage-hit query -- ``HybridCacheController._storage_hit_query``.

Everything here is gated by the environment variable
``SGLANG_P2A_TIMING_PROBE`` (default OFF).  When the gate is not truthy:

* ``p2a_enabled()`` returns ``False`` after one ``os.environ`` lookup;
* ``mark_enqueue`` writes no field and reads no clock;
* ``begin_storage_query_probe`` returns ``None`` without reading a clock;
* ``emit`` produces no log line.

All subtractable marks use ``time.monotonic_ns()`` -- the same clock as the
existing ``admission.v2 admission_monotonic_ns``, ``ready_stage ts_ns`` and
``ready_host ready_monotonic_ns`` producers.  Wall-clock values are never
used as a mark.

``probe_ns`` is the duration of the probe's own extra work.  It is measured
from the start of the probe block to immediately *before* the ``logger.info``
call, so the logging I/O itself is not counted (counting it would need a
second clock read after the emit).  For M3 it measures the record-assembly
block at emission; the extra timestamp reads around the backend calls are
bounded by the same primitive cost measured by the no-op baseline.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)

ENV_GATE = "SGLANG_P2A_TIMING_PROBE"
_TRUTHY = frozenset(("1", "true", "yes", "on"))


def p2a_enabled() -> bool:
    """Return True only when the probe gate is explicitly truthy.

    Default OFF.  Reading the environment on every call keeps the gate inert
    by construction: when unset this is a single dict lookup with no clock
    read, no log and no field write.
    """
    return os.environ.get(ENV_GATE, "").strip().lower() in _TRUTHY


def probe_identity(
    source: Any = None, context: Optional[dict] = None
) -> dict:
    """Best-effort ``node_id`` / ``build_id`` / ``session_generation``.

    Values come from the object first, then from an optional trace context.
    ``build_id`` falls back to the context's ``build_rid``.  Absent identity
    is reported as ``None``; it is never fabricated.
    """

    def _get(name: str):
        value = getattr(source, name, None) if source is not None else None
        if value is None and isinstance(context, dict):
            value = context.get(name)
        return value

    node_id = _get("node_id")
    build_id = _get("build_id")
    session_generation = _get("session_generation")
    if isinstance(context, dict):
        if node_id is None:
            node_id = context.get("node_id")
        if build_id is None:
            build_id = context.get("build_rid")
        if session_generation is None:
            session_generation = context.get("session_generation")
    return {
        "node_id": node_id,
        "build_id": build_id,
        "session_generation": session_generation,
    }


def _format_fields(fields: dict) -> str:
    return " ".join(f"{name}={value}" for name, value in fields.items())


def emit(ts_ns: int, event: str, probe_ns: int, **fields) -> None:
    """Emit one probe line.  Guarded again here so no caller can leak a log."""
    if not p2a_enabled():
        return
    try:
        logger.info(
            "[P2A] ts_ns=%d evt=%s %s probe_ns=%d",
            ts_ns,
            event,
            _format_fields(fields),
            probe_ns,
        )
    except Exception:
        pass


def mark_enqueue(req: Any) -> bool:
    """M1: set ``req.hicache_enqueue_mono_ns`` exactly once and emit one line.

    Returns True only when the mark was newly written.  A re-queue/retraction
    finds the field already set and returns without overwriting or re-emitting.
    Inert (no clock, no field write, no log) when the probe is OFF.
    """
    if not p2a_enabled():
        return False
    if getattr(req, "hicache_enqueue_mono_ns", None) is not None:
        return False
    block_start = time.monotonic_ns()
    req.hicache_enqueue_mono_ns = block_start
    identity = probe_identity(req)
    probe_ns = time.monotonic_ns() - block_start
    emit(
        block_start,
        "enqueue_mono_ns",
        probe_ns,
        rid=getattr(req, "rid", None),
        enqueue_mono_ns=block_start,
        **identity,
    )
    return True


def begin_storage_query_probe() -> Optional["StorageQueryProbe"]:
    """M3: return a probe handle, or ``None`` when the probe is OFF."""
    if not p2a_enabled():
        return None
    return StorageQueryProbe()


class StorageQueryProbe:
    """Per-call M3 accumulator for ``HybridCacheController._storage_hit_query``.

    ``enter_mono_ns`` is taken at construction (method entry, probe ON only).
    ``backend_lookup_ns`` accumulates the ``batch_exists`` / ``batch_exists_v2``
    spans.  ``lock_wait_ns`` / ``syscall_wait_ns`` / ``all_reduce_ns`` are
    recorded as ``N/A``: the method takes no explicit lock, the file-backend
    disk I/O is inside ``backend_lookup_ns``, and the collective lives outside
    this method (``cache_controller.py`` async / ``unified_radix_cache.py``
    sync).  The probe never calls a collective itself.
    """

    __slots__ = ("enter_mono_ns", "backend_lookup_ns")

    def __init__(self) -> None:
        self.enter_mono_ns = time.monotonic_ns()
        self.backend_lookup_ns = 0

    def note_backend_lookup(self, started_mono_ns: int) -> None:
        self.backend_lookup_ns += time.monotonic_ns() - started_mono_ns

    def emit(
        self,
        operation: Any,
        *,
        query_len: int,
        kv_hit_pages: int,
    ) -> None:
        block_start = time.monotonic_ns()
        rid = getattr(operation, "request_id", None)
        caller = (
            "sync_decode" if rid == "__storage_hit_query__" else "async_prefetch"
        )
        attempt_id = getattr(operation, "prefetch_attempt_id", None)
        if attempt_id is None:
            attempt_id = getattr(operation, "trace_id", None)
        probe_ns = time.monotonic_ns() - block_start
        emit(
            block_start,
            "storage_hit_query",
            probe_ns,
            enter_mono_ns=self.enter_mono_ns,
            exit_mono_ns=block_start,
            backend_lookup_ns=self.backend_lookup_ns,
            lock_wait_ns="N/A",
            syscall_wait_ns="N/A",
            all_reduce_ns="N/A",
            caller=caller,
            rid=rid,
            attempt_id=attempt_id,
            query_len=query_len,
            kv_hit_pages=kv_hit_pages,
        )
