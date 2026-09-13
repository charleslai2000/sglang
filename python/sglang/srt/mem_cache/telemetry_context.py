"""Producer-owned identity shared by the P0-B telemetry producers.

The values in this module are created by the server process.  They are not
accepted from request payloads or from the temporary verification harness.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Mapping

_PROCESS_ID = os.getpid()
_PROCESS_START_NS = time.monotonic_ns()
_RUN_ID = f"run-{_PROCESS_ID}-{_PROCESS_START_NS}"
_EVENT_SEQUENCE = 0
_PROFILE_VALUES: dict[str, Any] = {}
_CONTEXT: dict[str, Any] | None = None

# Producer-owned lineage registry.  The scheduler is the authority for the
# wait/wake/attempt lineage; the cache and READY producers read it back so a
# single lifecycle can be joined without trusting request payloads or the
# verification harness.  Entries are bounded and never escape the process.
_LINEAGE_LOCK = threading.Lock()
_HOST_ALLOC_LINEAGE: dict[tuple[str, str], dict[str, Any]] = {}
_HOST_ALLOC_LINEAGE_MAX = 8192

# Fields shared by the HOST_ALLOC wait/wake/change/retry family.  A producer
# only ever publishes values it generated itself.
HOST_ALLOC_LINEAGE_FIELDS = (
    "lifecycle_key",
    "wait_id",
    "wait_event_id",
    "wake_event_id",
    "wake_event_state",
    "predecessor_wait_id",
    "predecessor_terminal_event_id",
    "predecessor_terminal_state",
    "attempt_number",
    "attempt_origin",
    "parent_wait_id",
    "predecessor_lineage_reason",
    "cache_instance_id",
    "blocked_pool_generations",
    "current_generations",
    "wait_started_mono_ns",
    "deadline_mono_ns",
    "fifo_sequence",
    "terminal_event_id",
    "terminal_state",
    "terminal_reason",
)

# R72/R68 provenance anchors.  The content digest below additionally binds the
# producer files loaded by this process, including an experimental worktree.
SOURCE_HEAD = "4f41f5bab562b99562f30c67540eb05344d13637"
DEPLOYMENT_MANIFEST_DIGEST = (
    "262a9362e345df15d93049301d2b0e60990ba65d80c3bbc5209fb4cdab140e2d"
)
_PRODUCER_FILES = (
    "python/sglang/srt/managers/scheduler.py",
    "python/sglang/srt/managers/scheduler_components/hicache_restore.py",
    "python/sglang/srt/mem_cache/unified_radix_cache.py",
    "python/sglang/srt/mem_cache/hybrid_cache/hybrid_cache_controller.py",
    "python/sglang/srt/mem_cache/trace_context.py",
    "python/sglang/srt/mem_cache/telemetry_context.py",
)


def _source_digest() -> str:
    digest = hashlib.sha256()
    root = Path(__file__).resolve().parents[3]
    for relative in _PRODUCER_FILES:
        path = root / relative
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        try:
            digest.update(path.read_bytes())
        except OSError:
            digest.update(b"<missing>")
        digest.update(b"\0")
    return digest.hexdigest()


_SOURCE_BUILD = f"{SOURCE_HEAD}:{_source_digest()}"


def next_event_id(component: str) -> str:
    global _EVENT_SEQUENCE
    _EVENT_SEQUENCE += 1
    return f"{_RUN_ID}:{component}:{_EVENT_SEQUENCE}"


def lifecycle_key(rid: Any, session_generation: Any) -> str:
    """Return the stable producer-owned lifecycle key for one request."""
    return f"{rid}:{session_generation}"


def profile_id(profile_values: Mapping[str, Any] | None = None) -> str:
    payload = json.dumps(dict(profile_values or {}), sort_keys=True, default=str)
    return "profile-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def producer_context(
    *, profile_values: Mapping[str, Any] | None = None, component: str = "runtime"
) -> dict[str, Any]:
    """Return immutable process/deployment identity for a producer event."""
    values = dict(_PROFILE_VALUES)
    if profile_values:
        values.update(profile_values)
    global _CONTEXT
    if _CONTEXT is None or profile_values:
        _CONTEXT = {
            "process_id": _PROCESS_ID,
            "run_id": _RUN_ID,
            "profile_id": profile_id(values),
            "source_build": _SOURCE_BUILD,
            "source_head": SOURCE_HEAD,
            "deployment_manifest_digest": DEPLOYMENT_MANIFEST_DIGEST,
        }
    context = dict(_CONTEXT)
    context["producer_component"] = component
    return context


def configure_producer_context(profile_values: Mapping[str, Any]) -> dict[str, Any]:
    """Set the process-owned profile binding before producer threads start."""
    _PROFILE_VALUES.clear()
    _PROFILE_VALUES.update(profile_values)
    return producer_context(component="runtime")


def record_host_alloc_lineage(
    rid: Any,
    *,
    attempt_id: Any = None,
    run_id: Any = None,
    replace_missing: bool = False,
    **fields: Any,
) -> dict[str, Any]:
    """Publish scheduler-owned wait/wake/attempt lineage for one request.

    ``lineage_attempt_id`` (inside ``fields``) is the attempt the snapshot
    belongs to.  Only producer code calls this; callers cannot inject lineage
    through a request payload.

    By default only non-``None`` fields are written, so an incremental update
    never erases an earlier value.  With ``replace_missing=True`` a field that
    is passed as ``None`` is removed from the record: producers use this at a
    wait boundary to clear stale predecessor/terminal lineage when the new
    wait has no producer-owned predecessor.  Unknown identity is never joined
    to a known lifecycle.
    """
    process_run = str(run_id or _RUN_ID)
    request_id = str(rid)
    key = (process_run, request_id)
    with _LINEAGE_LOCK:
        if (
            len(_HOST_ALLOC_LINEAGE) >= _HOST_ALLOC_LINEAGE_MAX
            and key not in _HOST_ALLOC_LINEAGE
        ):
            _HOST_ALLOC_LINEAGE.clear()
        record = _HOST_ALLOC_LINEAGE.get(key)
        if record is None:
            record = {"rid": request_id, "run_id": process_run}
            _HOST_ALLOC_LINEAGE[key] = record
        if attempt_id is not None:
            record["lineage_attempt_id"] = str(attempt_id)
        for name in HOST_ALLOC_LINEAGE_FIELDS:
            if name not in fields:
                continue
            value = fields[name]
            if value is not None:
                record[name] = value
            elif replace_missing:
                record.pop(name, None)
        return dict(record)


def host_alloc_lineage(
    rid: Any,
    *,
    attempt_id: Any = None,
    run_id: Any = None,
) -> dict[str, Any]:
    """Read back producer-owned lineage for one request/attempt.

    A missing request or a contradictory explicit ``attempt_id`` yields an
    empty mapping: unknown identity must never be joined to a known lifecycle.
    """
    process_run = str(run_id or _RUN_ID)
    key = (process_run, str(rid))
    with _LINEAGE_LOCK:
        record = _HOST_ALLOC_LINEAGE.get(key)
        if record is None:
            return {}
        stored_attempt = record.get("lineage_attempt_id")
        if attempt_id is not None and stored_attempt is not None:
            if str(attempt_id) != str(stored_attempt):
                return {}
        return dict(record)


def host_alloc_lineage_fields(
    rid: Any,
    *,
    attempt_id: Any = None,
    run_id: Any = None,
) -> dict[str, Any]:
    """Read back only the known lineage fields for one request/attempt.

    Cache and READY producers use this so they publish the scheduler-owned
    identity (including ``lifecycle_key`` and the granted ``wake_event_id``)
    instead of deriving a divergent value.  A missing record yields an empty
    mapping: absent producer state is never fabricated.
    """
    record = host_alloc_lineage(rid, attempt_id=attempt_id, run_id=run_id)
    if not record:
        return {}
    return {
        name: record.get(name)
        for name in HOST_ALLOC_LINEAGE_FIELDS
        if name in record
    }


def clear_host_alloc_lineage(rid: Any = None, *, run_id: Any = None) -> None:
    """Drop lineage for one request, or the whole process when rid is None."""
    with _LINEAGE_LOCK:
        if rid is None:
            _HOST_ALLOC_LINEAGE.clear()
            return
        _HOST_ALLOC_LINEAGE.pop((str(run_id or _RUN_ID), str(rid)), None)
