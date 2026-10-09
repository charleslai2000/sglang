#!/usr/bin/env python3
"""Fail-closed reducer for authoritative P0-B product event logs.

The reducer deliberately accepts raw JSONL product records, not a normalized or
synthetic ``p0b.trace.v1`` stream.  It never controls the server and every
derived fact retains the source file/line reference supplied by this parser.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

STATUS_PASS = "PASS"
STATUS_BLOCKED = "BLOCKED"
STATUS_NOT_VERIFIED = "NOT_VERIFIED"
STATUS_INVALID_INPUT = "INVALID_INPUT"
STATUSES = {STATUS_PASS, STATUS_BLOCKED, STATUS_NOT_VERIFIED, STATUS_INVALID_INPUT}

IDENTITY = (
    "run_id",
    "session_id",
    "session_generation",
    "build_rid",
    "node_id",
    "final_kv_hash",
)

# This is the exact, stable eleven-item oracle.  Keep names in README and
# reports unchanged: reviewers use them to map each verdict to raw evidence.
ORACLE = (
    "provenance",
    "singular_identity",
    "positive_full_hit",
    "host_alloc_park",
    "generation_transition",
    "fifo_retry",
    "complete_restore",
    "ready_after_finalize",
    "raw_provenance",
    "negative_safety",
    "single_lifecycle",
)

REQUIRED_SCHEMAS = {
    "p0_durable.v3",
    "host_alloc.v1",
    "ready_host",
    "restore_ready",
}


class InputError(ValueError):
    """Input cannot be interpreted as an authoritative event bundle."""


@dataclass(frozen=True)
class RawEvent:
    schema: str
    event: str
    payload: dict[str, Any]
    source: str
    line_number: int
    ordinal: int
    raw: dict[str, Any]


def _nonempty(value: Any) -> bool:
    return value is not None and value != ""


def _payload(record: dict[str, Any]) -> dict[str, Any]:
    value = record.get("payload", record)
    if not isinstance(value, dict):
        raise InputError("payload must be an object")
    return value


def parse_raw_jsonl(paths: Iterable[Path]) -> list[RawEvent]:
    """Parse product-emitted JSONL and attach non-forgeable local line refs."""

    events: list[RawEvent] = []
    for path in paths:
        if not path.is_file():
            raise InputError(f"raw event file is missing: {path}")
        try:
            handle = path.open("r", encoding="utf-8")
        except OSError as exc:
            raise InputError(f"cannot read raw event file {path}: {exc}") from exc
        with handle:
            for line_number, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise InputError(f"invalid JSON at {path}:{line_number}: {exc}") from exc
                if not isinstance(record, dict):
                    raise InputError(f"event at {path}:{line_number} is not an object")
                schema = record.get("schema", record.get("schema_version"))
                event = record.get("event", record.get("event_type"))
                if not isinstance(schema, str) or not schema:
                    raise InputError(f"missing schema at {path}:{line_number}")
                if not isinstance(event, str) or not event:
                    raise InputError(f"missing event at {path}:{line_number}")
                if schema == "p0b.trace.v1":
                    raise InputError("synthetic p0b.trace.v1 is not an authoritative input")
                events.append(
                    RawEvent(
                        schema=schema,
                        event=event,
                        payload=_payload(record),
                        source=f"{path.resolve()}:{line_number}",
                        line_number=line_number,
                        ordinal=len(events),
                        raw=record,
                    )
                )
    if not events:
        raise InputError("raw event input is empty")
    return events


def load_provenance(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise InputError(f"provenance manifest is missing: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise InputError(f"invalid provenance manifest {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise InputError("provenance manifest must be an object")
    return value


def _fields(event: RawEvent) -> dict[str, Any]:
    identity = event.payload.get("identity")
    if not isinstance(identity, dict):
        return event.payload
    fields = {key: value for key, value in event.payload.items() if key != "identity"}
    fields.update(identity)
    return fields


def _identity(event: RawEvent) -> tuple[Any, ...]:
    fields = _fields(event)
    return tuple(fields.get(key) for key in IDENTITY)


def _all_identity(event: RawEvent) -> bool:
    return all(_nonempty(value) for value in _identity(event))


def _same_identity(events: Iterable[RawEvent]) -> bool:
    identities = {_identity(event) for event in events if _all_identity(event)}
    return len(identities) == 1


def _matching(events: Iterable[RawEvent], *names: str) -> list[RawEvent]:
    wanted = set(names)
    return [event for event in events if event.event in wanted]


def _value(event: RawEvent, *names: str, default: Any = None) -> Any:
    fields = _fields(event)
    for name in names:
        if name in fields:
            return fields[name]
    return default


def _bool(event: RawEvent, *names: str, default: bool = False) -> bool:
    return _value(event, *names, default=default) is True


def _positive_int(event: RawEvent, *names: str) -> bool:
    value = _value(event, *names)
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _refs(events: Iterable[RawEvent]) -> list[str]:
    return [event.source for event in events]


def reduce_events(events: list[RawEvent], provenance: dict[str, Any]) -> dict[str, Any]:
    """Return a derivative verdict while preserving source references."""

    reasons: list[str] = []
    checks: dict[str, bool] = {name: False for name in ORACLE}
    all_identity_events = [
        event
        for event in events
        if event.schema in REQUIRED_SCHEMAS and event.event != "host_allocability_change"
    ]
    unknown_schemas = sorted({event.schema for event in events} - REQUIRED_SCHEMAS)
    if unknown_schemas:
        reasons.append(f"unsupported authoritative schemas: {', '.join(unknown_schemas)}")

    manifest_files = provenance.get("source_files")
    checks["provenance"] = (
        provenance.get("task_id") == "P0-B-HARNESS-IMPLEMENT-20260911-R89"
        and provenance.get("epoch") == "2026-09-11"
        and provenance.get("target") == "RTX 3060 12G"
        and isinstance(manifest_files, dict)
        and bool(manifest_files)
        and all(
            isinstance(name, str) and name and isinstance(digest, str) and len(digest) == 64
            for name, digest in manifest_files.items()
        )
    )
    if not checks["provenance"]:
        reasons.append("provenance manifest lacks exact task/epoch/target/source_files")

    checks["singular_identity"] = bool(all_identity_events) and all(
        _all_identity(event) for event in all_identity_events
    )
    if not checks["singular_identity"]:
        reasons.append("missing required six-field lifecycle identity")

    checks["single_lifecycle"] = checks["singular_identity"] and _same_identity(all_identity_events)
    if not checks["single_lifecycle"]:
        reasons.append("identity is not singular across authoritative events")

    hits = _matching(events, "durable_hit", "p0_durable_hit")
    checks["positive_full_hit"] = any(
        _bool(event, "positive_hit", "full_kv_hit")
        and _bool(event, "complete_kv", "full_span")
        and _bool(event, "all_sidecars", "complete_mamba")
        for event in hits
    )
    if not checks["positive_full_hit"]:
        reasons.append("no authoritative positive full KV plus sidecar hit")

    waits = _matching(events, "restore_host_alloc_wait")
    checks["host_alloc_park"] = any(
        _value(event, "state") == "WAIT_CAPACITY"
        and _value(event, "reason") == "HOST_ALLOC"
        and _positive_int(event, "positive_hit_tokens")
        and _bool(event, "full_span", "complete_request")
        and not _bool(event, "genuine_miss")
        and not _bool(event, "crop_attempted")
        and _nonempty(_value(event, "fifo_sequence"))
        and isinstance(_value(event, "captured_generations", "generations"), dict)
        and _nonempty(_value(event, "cache_instance_id"))
        for event in waits
    )
    if not checks["host_alloc_park"]:
        reasons.append("no complete positive-hit WAIT_CAPACITY/HOST_ALLOC park")

    changes = _matching(events, "host_allocability_change")
    def is_exact_change(change: RawEvent) -> bool:
        instance = _value(change, "cache_instance_id")
        pool = _value(change, "pool")
        before = _value(change, "generation_before")
        after = _value(change, "generation_after")
        return (
            _nonempty(instance)
            and _nonempty(pool)
            and isinstance(before, int)
            and isinstance(after, int)
            and after > before
            and _nonempty(_value(change, "cause"))
            and _nonempty(_value(change, "telemetry_sequence", "sequence"))
            and (_positive_int(change, "returned_units") or _bool(change, "evictability_changed"))
            and any(
                _value(wait, "cache_instance_id") == instance
                and isinstance(_value(wait, "captured_generations", "generations"), dict)
                and _value(wait, "captured_generations", "generations").get(pool) == before
                for wait in waits
            )
        )

    checks["generation_transition"] = any(is_exact_change(change) for change in changes)
    if not checks["generation_transition"]:
        reasons.append("no exact contiguous host_alloc generation transition")

    wakes = _matching(events, "restore_host_alloc_wake_decision")
    retries = _matching(events, "restore_host_alloc_retry_result", "restore_retry")
    eligible_wakes = [
        event
        for event in wakes
        if _value(event, "decision") == "grant"
        and _bool(event, "required_generations_advanced", "generation_advanced")
        and _bool(event, "fifo_eligible")
        and _bool(event, "predecessor_check_passed")
        and not _bool(event, "same_generation_self_wake")
    ]
    checks["fifo_retry"] = (
        len(eligible_wakes) == 1
        and len(retries) == 1
        and (
            _value(retries[0], "retry_outcome") == "revoked_alloc_failed"
            or _value(retries[0], "cause") == "capacity"
        )
        and _positive_int(retries[0], "positive_hit_tokens")
        and _nonempty(_value(retries[0], "attempt_id"))
        and not _bool(retries[0], "repeated_retry")
        and not _bool(retries[0], "skipped_eligible_predecessor")
        and any(
            _value(wake, "cache_instance_id") == _value(retries[0], "cache_instance_id")
            for wake in eligible_wakes
        )
        and any(
            _value(wake, "attempt_id") == _value(retries[0], "attempt_id")
            for wake in eligible_wakes
            if _nonempty(_value(wake, "attempt_id"))
        )
    )
    if not checks["fifo_retry"]:
        reasons.append("FIFO wake/retry is absent, repeated, same-generation, or unordered")

    finalizations = _matching(
        events, "restore_hybrid_finalize", "restore_host_alloc_finalize", "restore_finalization"
    )
    checks["complete_restore"] = any(
        _bool(event, "all_or_nothing")
        and _bool(event, "complete_kv", "full_kv_restored")
        and _bool(event, "all_sidecars", "complete_mamba")
        and _bool(event, "accepted", "finalization_accepted")
        and not _bool(event, "crop_attempted", "crop")
        and not _bool(event, "lower_checkpoint_queried", "lower_frontier_substitution")
        and not _bool(event, "partial_sidecar")
        and not _bool(event, "discarded_hybrid")
        and not _bool(event, "recompute_fallback")
        for event in finalizations
    )
    if checks["complete_restore"] and retries:
        checks["complete_restore"] = any(
            _value(final, "attempt_id") == _value(retries[0], "attempt_id")
            for final in finalizations
        )
    if not checks["complete_restore"]:
        reasons.append("complete all-or-nothing restore/finalization is not proven")

    ready = _matching(events, "ready_host", "restore_ready")
    checks["ready_after_finalize"] = any(
        _bool(event, "ready", "admitted")
        and _nonempty(_value(event, "attempt_id"))
        and any(
            _value(final, "attempt_id") == _value(event, "attempt_id")
            and final.ordinal < event.ordinal
            for final in finalizations
        )
        for event in ready
    )
    if not checks["ready_after_finalize"]:
        reasons.append("authoritative READY is absent or precedes finalization")

    checks["raw_provenance"] = (
        not unknown_schemas
        and all(event.schema in REQUIRED_SCHEMAS and event.source and event.raw for event in events)
        and any(event.schema == "host_alloc.v1" for event in events)
    )
    if not checks["raw_provenance"]:
        reasons.append("raw authoritative references or host_alloc.v1 evidence are absent")

    negative_flags = (
        "genuine_miss",
        "crop_attempted",
        "lower_checkpoint_queried",
        "same_generation_self_wake",
        "repeated_retry",
        "skipped_eligible_predecessor",
        "partial_sidecar",
        "discarded_hybrid",
        "recompute_fallback",
    )
    checks["negative_safety"] = not any(
        _bool(event, flag) for event in events for flag in negative_flags
    )
    if not checks["negative_safety"]:
        reasons.append("a prohibited negative condition is present")

    status = STATUS_PASS if all(checks.values()) else STATUS_NOT_VERIFIED
    return {
        "status": status,
        "oracle": checks,
        "reasons": sorted(set(reasons)),
        "raw_event_count": len(events),
        "raw_references": _refs(events),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", nargs="+", type=Path, required=True)
    parser.add_argument("--provenance", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = reduce_events(parse_raw_jsonl(args.events), load_provenance(args.provenance))
    except InputError as exc:
        result = {"status": STATUS_INVALID_INPUT, "oracle": {}, "reasons": [str(exc)]}
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0 if result["status"] in STATUSES else 1


if __name__ == "__main__":
    raise SystemExit(main())
