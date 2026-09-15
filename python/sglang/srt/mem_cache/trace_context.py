"""Marker-gated trace context helpers for the P0 durability vehicle."""

from __future__ import annotations

import os
import threading
import hashlib
from typing import Any, Optional

TRACE_MARKER = "/tmp/t38c-durable-trace"
TRACE_SCHEMA = "p0_durable.v3"

_SLOT_CONTEXTS: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
_SLOT_CONTEXTS_LOCK = threading.Lock()
_SLOT_SEQUENCE = 0
_SLOT_COMPLETION_HINT = threading.local()

# Every queued release has one metadata item.  This inert token deliberately
# cannot match a registered slot lifecycle and keeps page/token FIFO state
# aligned while tracing is disabled or context registration is unavailable.
INERT_RELEASE_TOKEN = ("t38c-inert-release",)


def is_inert_release_token(token: Optional[tuple[Any, ...]]) -> bool:
    return token == INERT_RELEASE_TOKEN


def durable_trace_enabled() -> bool:
    return os.path.exists(TRACE_MARKER)


def ordered_key_set_digest(keys) -> tuple[str, int]:
    """Return a privacy-safe digest and count for an ordered key sequence."""
    digest = hashlib.sha256()
    count = 0
    for key in keys:
        encoded = str(key).encode("utf-8")
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
        count += 1
    return digest.hexdigest(), count


def complete_trace_context(
    context: Optional[dict[str, Any]], node_id, final_kv_hash
) -> bool:
    """Check the authoritative lifecycle and write binding for one candidate."""
    if not isinstance(context, dict):
        return False
    return bool(
        context.get("session_id")
        and context.get("build_rid")
        and context.get("session_generation") is not None
        and str(context.get("node_id")) == str(node_id)
        and context.get("final_kv_hash") == final_kv_hash
    )


def make_trace_context(
    session_id: Optional[str],
    session_generation: Optional[int],
    build_rid: Optional[str],
    warm_rid: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    # A session id alone is not an authoritative lifecycle identity.  In
    # particular, never let a request without the scheduler-owned generation
    # inherit an older build tuple.
    if (
        not durable_trace_enabled()
        or not session_id
        or session_generation is None
        or not build_rid
    ):
        return None
    return {
        "schema_version": TRACE_SCHEMA,
        "session_id": str(session_id),
        "session_generation": session_generation,
        "build_rid": str(build_rid),
        "warm_rid": str(warm_rid) if warm_rid else None,
    }


def attach_trace_context(
    record: dict[str, Any], context: Optional[dict[str, Any]] = None
) -> dict[str, Any]:
    context = context or record.pop("trace_context", None)
    if context and context.get("session_id") and context.get("build_rid"):
        record.update(dict(context))
        record["schema_version"] = TRACE_SCHEMA
    # Marker-gated durability records keep their existing run_id/process_id
    # semantics for backward compatibility; the non-forgeable producer
    # identity is attached under a dedicated nested key.
    from sglang.srt.mem_cache.telemetry_context import producer_context

    record.setdefault("producer", producer_context(component="durable"))
    return record


def remember_slot_context(
    pool: str,
    tier: str,
    slot_digest: Optional[str],
    context: Optional[dict[str, Any]],
    lifecycle: Optional[dict[str, Any]] = None,
) -> Optional[tuple[Any, ...]]:
    """Register one slot lifecycle and return its exact completion token.

    The digest is only a lookup hint.  The returned token carries a process
    run, node, generation/build context, and monotonic detach sequence so a
    reused slot cannot satisfy a previous lifecycle's completion.
    """
    global _SLOT_SEQUENCE
    if not slot_digest or not context:
        return None
    context_copy = dict(context)
    lifecycle_copy = dict(lifecycle or {})
    with _SLOT_CONTEXTS_LOCK:
        key = (str(pool), str(tier), str(slot_digest))
        records = _SLOT_CONTEXTS.setdefault(key, [])
        for record in records:
            if not record["completed"] and record["context"] == context_copy:
                if lifecycle is None or record["lifecycle"] == lifecycle_copy:
                    return record["token"]
                if not record["lifecycle"] and lifecycle_copy:
                    _SLOT_SEQUENCE += 1
                    record["lifecycle"] = lifecycle_copy
                    record["token"] = (
                        lifecycle_copy.get("run_id") or f"pid-{os.getpid()}",
                        context_copy.get("session_id"),
                        str(lifecycle_copy.get("node_id", "")),
                        lifecycle_copy.get(
                            "session_generation", context_copy.get("session_generation")
                        ),
                        context_copy.get("build_rid"),
                        _SLOT_SEQUENCE,
                    )
                    return record["token"]
        _SLOT_SEQUENCE += 1
        token = (
            lifecycle_copy.get("run_id") or f"pid-{os.getpid()}",
            context_copy.get("session_id"),
            str(lifecycle_copy.get("node_id", "")),
            lifecycle_copy.get(
                "session_generation", context_copy.get("session_generation")
            ),
            context_copy.get("build_rid"),
            _SLOT_SEQUENCE,
        )
        records.append(
            {
                "context": context_copy,
                "lifecycle": lifecycle_copy,
                "token": token,
                "completed": False,
            }
        )
        return token


def slot_context(
    pool: str, tier: str, slot_digest: Optional[str]
) -> Optional[dict[str, Any]]:
    if not slot_digest:
        return None
    with _SLOT_CONTEXTS_LOCK:
        key = (str(pool), str(tier), str(slot_digest))
        record = next(
            (item for item in _SLOT_CONTEXTS.get(key, []) if not item["completed"]),
            None,
        )
        if record is None:
            return None
        _SLOT_COMPLETION_HINT.record = record
        _SLOT_COMPLETION_HINT.key = key
    return dict(record["context"])


def slot_context_for_token(
    token: Optional[tuple[Any, ...]],
) -> Optional[dict[str, Any]]:
    """Return context for an exact queued release token."""
    if token is None:
        return None
    with _SLOT_CONTEXTS_LOCK:
        for records in _SLOT_CONTEXTS.values():
            for record in records:
                if record["token"] == token and not record["completed"]:
                    return dict(record["context"])
    return None


def complete_slot_context(
    pool: str,
    tier: str,
    slot_digest: Optional[str],
    token: Optional[tuple[Any, ...]] = None,
) -> Optional[tuple[Any, ...]]:
    """Mark one slot lifecycle complete only by its exact queue token."""
    if token is None or is_inert_release_token(token) or not slot_digest:
        return None
    key = (str(pool), str(tier), str(slot_digest))
    with _SLOT_CONTEXTS_LOCK:
        record = next(
            (
                item
                for record_key, records in _SLOT_CONTEXTS.items()
                for item in records
                if record_key == key
                and item["token"] == token
                and not item["completed"]
            ),
            None,
        )
        if record is None:
            return None
        record["completed"] = True
        _SLOT_COMPLETION_HINT.record = None
        return record["token"]


def slot_token(
    pool: str, tier: str, slot_digest: Optional[str]
) -> Optional[tuple[Any, ...]]:
    """Return the exact active token for a non-queued allocator free."""
    if not slot_digest:
        return None
    with _SLOT_CONTEXTS_LOCK:
        key = (str(pool), str(tier), str(slot_digest))
        record = next(
            (item for item in _SLOT_CONTEXTS.get(key, []) if not item["completed"]),
            None,
        )
        return record["token"] if record is not None else None


def retire_slot_token(token: Optional[tuple[Any, ...]]) -> None:
    if token is None:
        return
    with _SLOT_CONTEXTS_LOCK:
        for key in list(_SLOT_CONTEXTS):
            records = [
                record
                for record in _SLOT_CONTEXTS[key]
                if record["token"] != token
            ]
            if records:
                _SLOT_CONTEXTS[key] = records
            else:
                _SLOT_CONTEXTS.pop(key, None)


def retire_slot_contexts(session_id: Optional[str] = None) -> None:
    """Retire trace-only slot records on cache reset or session release."""
    with _SLOT_CONTEXTS_LOCK:
        if session_id is None:
            _SLOT_CONTEXTS.clear()
            return
        for key in list(_SLOT_CONTEXTS):
            records = [
                record
                for record in _SLOT_CONTEXTS[key]
                if record["context"].get("session_id") != str(session_id)
            ]
            if records:
                _SLOT_CONTEXTS[key] = records
            else:
                _SLOT_CONTEXTS.pop(key, None)
