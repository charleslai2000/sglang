#!/usr/bin/env python3
"""Fail-closed reducer for the R94 P0-B authoritative event bundle.

The input is product-emitted JSONL.  The reducer never accepts a normalized
trace, caller supplied verdict, or boolean summary as evidence.  Every event
reference returned by the reducer is an absolute source-file:line reference
created while parsing the immutable JSONL file.
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

# These names are the stable eleven-predicate R79 oracle.  The implementation
# below makes each predicate depend on raw product records, not summary flags.
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

IDENTITY = (
    "rid",
    "session_id",
    "session_generation",
    "node_id",
    "build_rid",
    "generation",
    "server_pid",
    "profile",
    "source_manifest_id",
)

ALLOWED_SCHEMAS = {
    "host_alloc.v1",
    "admission.v2",
    "restore.v1",
    "finalization.v1",
    "rh_holder.v1",
    "rh_ready_host.v1",
}

# These names are deliberately refused even when nested in an otherwise valid
# event.  A product event can provide atomic counts/states; these aggregate
# claims must never be used as an oracle input.
SUMMARY_FIELDS = {
    "positive_hit",
    "full_kv_hit",
    "complete_kv",
    "all_sidecars",
    "full_span",
    "complete_request",
    "ready",
    "admitted",
    "accepted",
    "passed",
    "success",
    "verified",
    "oracle",
    "status",
    "verdict",
    "pass",
}

COMMON_FIELDS = set(IDENTITY) | {"event_id", "ts_ns"}


class InputError(ValueError):
    """Malformed, unsupported, forged, or contradictory evidence."""


class MissingEvidence(ValueError):
    """Well-formed evidence bundle that cannot prove the oracle."""


@dataclass(frozen=True)
class RawEvent:
    schema: str
    event: str
    payload: dict[str, Any]
    source: str
    line_number: int
    ordinal: int
    raw: dict[str, Any]


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _positive_int(value: Any) -> bool:
    return _is_int(value) and value > 0


def _nonempty(value: Any) -> bool:
    return isinstance(value, (str, int)) and not isinstance(value, bool) and value != ""


def _walk_keys(value: Any) -> Iterable[str]:
    if isinstance(value, dict):
        for key, child in value.items():
            if isinstance(key, str):
                yield key
            yield from _walk_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_keys(child)


def _walk_values(value: Any) -> Iterable[Any]:
    if isinstance(value, dict):
        for child in value.values():
            yield child
            yield from _walk_values(child)
    elif isinstance(value, list):
        for child in value:
            yield child
            yield from _walk_values(child)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_raw_jsonl(paths: Iterable[Path]) -> list[RawEvent]:
    """Read raw JSONL and attach absolute, parser-owned source references."""

    events: list[RawEvent] = []
    seen_ids: set[str] = set()
    for supplied_path in paths:
        path = supplied_path.resolve()
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
                schema = record.get("schema")
                event_name = record.get("event")
                payload = record.get("payload")
                if not isinstance(schema, str) or schema not in ALLOWED_SCHEMAS:
                    raise InputError(f"unsupported or missing authoritative schema at {path}:{line_number}")
                if schema == "p0b.trace.v1":
                    raise InputError("synthetic p0b.trace.v1 is not authoritative")
                if not isinstance(event_name, str) or not event_name:
                    raise InputError(f"missing event at {path}:{line_number}")
                if not isinstance(payload, dict):
                    raise InputError(f"payload must be an object at {path}:{line_number}")
                if any(key in SUMMARY_FIELDS for key in _walk_keys(payload)):
                    raise InputError(f"caller-supplied summary field at {path}:{line_number}")
                event_id = payload.get("event_id")
                if not isinstance(event_id, str) or not event_id or event_id in seen_ids:
                    raise InputError(f"missing or duplicate event_id at {path}:{line_number}")
                seen_ids.add(event_id)
                events.append(
                    RawEvent(
                        schema=schema,
                        event=event_name,
                        payload=payload,
                        source=f"{path}:{line_number}",
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


def _events(events: Iterable[RawEvent], schema: str | None = None, event: str | None = None) -> list[RawEvent]:
    return [item for item in events if (schema is None or item.schema == schema) and (event is None or item.event == event)]


def _identity(event: RawEvent) -> tuple[Any, ...]:
    return tuple(event.payload.get(key) for key in IDENTITY)


def _all_identity(event: RawEvent) -> bool:
    values = _identity(event)
    return (
        _nonempty(values[0])
        and _nonempty(values[1])
        and _positive_int(values[2])
        and _nonempty(values[3])
        and _nonempty(values[4])
        and _positive_int(values[5])
        and _positive_int(values[6])
        and _nonempty(values[7])
        and _nonempty(values[8])
    )


def _same_identity(events: Iterable[RawEvent]) -> bool:
    identities = {_identity(event) for event in events}
    return len(identities) == 1


def _source_parts(source: str) -> tuple[Path, int]:
    path_text, separator, line_text = source.rpartition(":")
    if not separator or not path_text.startswith("/") or not line_text.isdigit() or int(line_text) < 1:
        raise InputError(f"invalid parser source reference: {source}")
    return Path(path_text), int(line_text)


def _check_provenance(events: list[RawEvent], provenance: dict[str, Any]) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if provenance.get("task_id") != "P0-B-HARNESS-IMPLEMENT-20260911-R94":
        reasons.append("provenance task_id is not R94")
    if provenance.get("epoch") != "2026-09-11":
        reasons.append("provenance epoch is not 2026-09-11")
    if provenance.get("target") != "RTX 3060 12G":
        reasons.append("provenance target is not RTX 3060 12G")
    if not _positive_int(provenance.get("server_pid")):
        reasons.append("provenance server_pid is absent")
    if not isinstance(provenance.get("profile"), str) or not provenance["profile"]:
        reasons.append("provenance profile is absent")
    manifest_id = provenance.get("source_manifest_id")
    if not isinstance(manifest_id, str) or not manifest_id:
        reasons.append("provenance source_manifest_id is absent")
    source_files = provenance.get("source_files")
    if not isinstance(source_files, dict) or not source_files:
        reasons.append("provenance source_files is absent")
    elif any(
        not isinstance(path, str)
        or not path.startswith("/")
        or not isinstance(digest, str)
        or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest.lower())
        for path, digest in source_files.items()
    ):
        reasons.append("provenance source_files is not an absolute SHA256 manifest")
    else:
        for source in sorted({event.source for event in events}):
            path, line = _source_parts(source)
            expected = source_files.get(str(path))
            if expected is None:
                reasons.append(f"event source is not bound in manifest: {source}")
                continue
            try:
                actual = _sha256(path)
            except OSError as exc:
                raise InputError(f"cannot hash bound source {path}: {exc}") from exc
            if actual != expected.lower():
                raise InputError(f"source hash mismatch for {path}")
            with path.open("r", encoding="utf-8") as source_handle:
                line_count = sum(1 for _ in source_handle)
            if line > line_count:
                raise InputError(f"source line is outside bound file: {source}")
    return not reasons, reasons


def _validate_common(events: list[RawEvent], provenance: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    if not events:
        return ["no authoritative events"]
    for event in events:
        if not _all_identity(event):
            reasons.append(f"missing lifecycle identity at {event.source}")
            continue
        if provenance.get("server_pid") is not None and event.payload["server_pid"] != provenance.get("server_pid"):
            raise InputError(f"PID binding contradiction at {event.source}")
        if provenance.get("profile") is not None and event.payload["profile"] != provenance.get("profile"):
            raise InputError(f"profile binding contradiction at {event.source}")
        if provenance.get("source_manifest_id") is not None and event.payload["source_manifest_id"] != provenance.get("source_manifest_id"):
            raise InputError(f"source manifest binding contradiction at {event.source}")
        if not _positive_int(event.payload.get("ts_ns")):
            reasons.append(f"missing event timestamp at {event.source}")
        if set(event.payload) - COMMON_FIELDS:
            # Schema-specific validation below owns all non-common fields.
            continue
    timestamps = [event.payload.get("ts_ns") for event in events]
    if all(_positive_int(value) for value in timestamps) and timestamps != sorted(timestamps):
        raise InputError("authoritative event timestamps contradict raw ordering")
    return reasons


def _require_fields(event: RawEvent, fields: set[str]) -> None:
    missing = sorted(fields - set(event.payload))
    if missing:
        raise MissingEvidence(f"missing fields for {event.schema}/{event.event}: {', '.join(missing)}")


def _validate_event_contract(event: RawEvent) -> None:
    contracts: dict[tuple[str, str], set[str]] = {
        ("admission.v2", "request_created"): COMMON_FIELDS | {"role", "admission_state"},
        ("host_alloc.v1", "kv_lookup"): COMMON_FIELDS | {"span_id", "requested_units", "resident_units", "lookup_outcome", "lookup_generation"},
        ("host_alloc.v1", "sidecar_lookup"): COMMON_FIELDS | {"sidecar_id", "required_units", "resident_units", "lookup_outcome", "lookup_generation"},
        ("host_alloc.v1", "wait_entered"): COMMON_FIELDS | {"wait_id", "state", "reason", "blocked_pool_generations", "fifo_ticket"},
        ("host_alloc.v1", "generation_edge"): COMMON_FIELDS | {"wait_id", "pool", "from_generation", "to_generation", "edge_seq", "cause"},
        ("host_alloc.v1", "fifo_predecessor"): COMMON_FIELDS | {"wait_id", "fifo_ticket", "predecessor_wait_id", "predecessor_ticket", "predecessor_terminal_event_id"},
        ("host_alloc.v1", "predecessor_terminal"): COMMON_FIELDS | {"wait_id", "terminal_state"},
        ("host_alloc.v1", "wake_grant"): COMMON_FIELDS | {"wait_id", "attempt_id", "required_pools", "observed_generations", "predecessor_event_id", "grant_state"},
        ("host_alloc.v1", "retry_attempt"): COMMON_FIELDS | {"wait_id", "attempt_id", "wake_event_id", "retry_outcome", "attempt_number", "attempt_origin"},
        ("restore.v1", "restore_completed"): COMMON_FIELDS | {"attempt_id", "restore_state", "restored_units", "restored_sidecar_units", "origin_event_id"},
        ("finalization.v1", "finalization_accepted"): COMMON_FIELDS | {"attempt_id", "finalization_state", "atomicity", "commit_id", "origin_event_id"},
        ("rh_ready_host.v1", "ready"): COMMON_FIELDS | {"attempt_id", "ready_state", "admission_state", "finalization_event_id"},
        ("rh_holder.v1", "holder_staged"): COMMON_FIELDS | {"holder_state", "holder_rid"},
    }
    allowed = contracts.get((event.schema, event.event))
    if allowed is None:
        raise InputError(f"unsupported event for authoritative schema: {event.schema}/{event.event}")
    _require_fields(event, allowed - COMMON_FIELDS)
    unknown = set(event.payload) - allowed
    if unknown:
        raise InputError(f"unknown fields in {event.schema}/{event.event}: {', '.join(sorted(unknown))}")


def _valid_scalar_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value)


def _reduce_checks(events: list[RawEvent], provenance: dict[str, Any]) -> tuple[dict[str, bool], list[str]]:
    reasons: list[str] = []
    checks = {name: False for name in ORACLE}
    checks["provenance"], provenance_reasons = _check_provenance(events, provenance)
    reasons.extend(provenance_reasons)
    common_reasons = _validate_common(events, provenance)
    reasons.extend(common_reasons)
    for event in events:
        _validate_event_contract(event)

    checks["singular_identity"] = bool(events) and all(_all_identity(event) for event in events)
    if not checks["singular_identity"]:
        reasons.append("one or more authoritative records lack complete identity")
    checks["single_lifecycle"] = checks["singular_identity"] and _same_identity(events)
    if not checks["single_lifecycle"]:
        reasons.append("records do not bind to one RID/session/node/build/generation lifecycle")

    admission = _events(events, "admission.v2", "request_created")
    kv = _events(events, "host_alloc.v1", "kv_lookup")
    sidecar = _events(events, "host_alloc.v1", "sidecar_lookup")
    checks["positive_full_hit"] = any(
        item.payload.get("role") == "target" and item.payload.get("admission_state") == "accepted"
        for item in admission
    ) and any(
        item.payload.get("lookup_outcome") == "HIT"
        and _positive_int(item.payload.get("requested_units"))
        and item.payload.get("resident_units") == item.payload.get("requested_units")
        for item in kv
    ) and any(
        item.payload.get("lookup_outcome") == "HIT"
        and _positive_int(item.payload.get("required_units"))
        and item.payload.get("resident_units") == item.payload.get("required_units")
        for item in sidecar
    )
    if not checks["positive_full_hit"]:
        reasons.append("atomic KV and sidecar hit records do not establish a complete target span")

    waits = _events(events, "host_alloc.v1", "wait_entered")
    checks["host_alloc_park"] = any(
        item.payload.get("state") == "WAIT_CAPACITY"
        and item.payload.get("reason") == "HOST_ALLOC"
        and isinstance(item.payload.get("blocked_pool_generations"), dict)
        and set(item.payload["blocked_pool_generations"]) == {"kv", "mamba"}
        and all(_positive_int(value) for value in item.payload["blocked_pool_generations"].values())
        and _positive_int(item.payload.get("fifo_ticket"))
        for item in waits
    )
    if not checks["host_alloc_park"]:
        reasons.append("complete WAIT_CAPACITY/HOST_ALLOC park is absent")

    edges = _events(events, "host_alloc.v1", "generation_edge")
    valid_edges: list[RawEvent] = []
    for edge in edges:
        if "from_generation" not in edge.payload or "to_generation" not in edge.payload:
            raise MissingEvidence(f"incomplete generation edge at {edge.source}")
        before = edge.payload.get("from_generation")
        after = edge.payload.get("to_generation")
        if not _positive_int(before) or not _positive_int(after) or after != before + 1:
            raise InputError(f"non-contiguous generation edge at {edge.source}")
        if not _valid_scalar_string(edge.payload.get("pool")) or not _valid_scalar_string(edge.payload.get("cause")):
            raise MissingEvidence(f"incomplete generation edge at {edge.source}")
        valid_edges.append(edge)
    wait_by_id = {item.payload.get("wait_id"): item for item in waits}
    pools_seen: dict[str, list[RawEvent]] = {"kv": [], "mamba": []}
    for edge in valid_edges:
        if edge.payload["pool"] not in pools_seen:
            raise InputError(f"unknown generation pool at {edge.source}")
        wait = wait_by_id.get(edge.payload["wait_id"])
        if wait is None:
            raise MissingEvidence(f"generation edge has no wait origin at {edge.source}")
        captured = wait.payload["blocked_pool_generations"].get(edge.payload["pool"])
        if captured != edge.payload["from_generation"]:
            raise InputError(f"generation edge does not start at captured generation at {edge.source}")
        pools_seen[edge.payload["pool"]].append(edge)
    contiguous = True
    for pool, pool_edges in pools_seen.items():
        if not pool_edges:
            contiguous = False
            continue
        ordered = sorted(pool_edges, key=lambda item: item.payload["edge_seq"])
        if [item.payload["edge_seq"] for item in ordered] != list(range(ordered[0].payload["edge_seq"], ordered[-1].payload["edge_seq"] + 1)):
            raise InputError(f"non-contiguous telemetry edge sequence for {pool}")
        if len({item.payload["to_generation"] for item in ordered}) != len(ordered):
            raise InputError(f"contradictory generation edge for {pool}")
    checks["generation_transition"] = checks["host_alloc_park"] and contiguous
    if not checks["generation_transition"]:
        reasons.append("both blocked pools lack a contiguous captured-to-next generation edge")

    predecessors = _events(events, "host_alloc.v1", "fifo_predecessor")
    wakes = _events(events, "host_alloc.v1", "wake_grant")
    retries = _events(events, "host_alloc.v1", "retry_attempt")
    predecessor_by_wait = {item.payload.get("wait_id"): item for item in predecessors}
    eligible_wakes = []
    for wake in wakes:
        if wake.payload.get("grant_state") != "RETRY_ELIGIBLE":
            continue
        wait = wait_by_id.get(wake.payload.get("wait_id"))
        predecessor = predecessor_by_wait.get(wake.payload.get("wait_id"))
        if wait is None or predecessor is None:
            continue
        if wake.payload.get("predecessor_event_id") != predecessor.payload.get("event_id"):
            raise InputError(f"wake predecessor reference mismatch at {wake.source}")
        if predecessor.payload.get("predecessor_ticket") >= predecessor.payload.get("fifo_ticket"):
            raise InputError(f"FIFO predecessor ticket contradiction at {predecessor.source}")
        terminal = next((item for item in events if item.payload.get("event_id") == predecessor.payload.get("predecessor_terminal_event_id")), None)
        if terminal is None or terminal.ordinal >= wake.ordinal:
            continue
        eligible_wakes.append(wake)
    checks["fifo_retry"] = False
    if len(eligible_wakes) == 1 and len(retries) == 1:
        wake = eligible_wakes[0]
        retry = retries[0]
        if retry.payload.get("wake_event_id") != wake.payload.get("event_id"):
            raise InputError(f"retry wake lineage mismatch at {retry.source}")
        checks["fifo_retry"] = (
            retry.payload.get("attempt_id") == wake.payload.get("attempt_id")
            and retry.payload.get("wake_event_id") == wake.payload.get("event_id")
            and retry.payload.get("wait_id") == wake.payload.get("wait_id")
            and retry.payload.get("attempt_origin") == "HOST_ALLOC_WAKE"
            and retry.payload.get("retry_outcome") == "REVOKED_ALLOC_FAILED"
            and retry.payload.get("attempt_number") == 1
            and all(
                any(edge.payload.get("pool") == pool and edge.payload.get("to_generation") == wake.payload["observed_generations"].get(pool) for edge in valid_edges)
                for pool in ("kv", "mamba")
            )
        )
        if retry.payload.get("attempt_number", 1) > 1:
            reasons.append("repeated retry attempt")
    if not checks["fifo_retry"]:
        reasons.append("FIFO predecessor, generation-advanced wake, and retry lineage are incomplete")

    restores = _events(events, "restore.v1", "restore_completed")
    finalizations = _events(events, "finalization.v1", "finalization_accepted")
    checks["complete_restore"] = False
    if len(restores) == 1 and len(finalizations) == 1:
        restore = restores[0]
        final = finalizations[0]
        checks["complete_restore"] = (
            restore.payload.get("restore_state") == "COMPLETE"
            and _positive_int(restore.payload.get("restored_units"))
            and _positive_int(restore.payload.get("restored_sidecar_units"))
            and final.payload.get("attempt_id") == restore.payload.get("attempt_id")
            and final.payload.get("origin_event_id") == restore.payload.get("event_id")
            and final.payload.get("finalization_state") == "ACCEPTED"
            and final.payload.get("atomicity") == "ALL_OR_NOTHING"
            and final.ordinal > restore.ordinal
        )
    if not checks["complete_restore"]:
        reasons.append("accepted all-or-nothing full restore/finalization is incomplete")

    ready = _events(events, "rh_ready_host.v1", "ready")
    checks["ready_after_finalize"] = any(
        item.payload.get("ready_state") == "READY"
        and item.payload.get("admission_state") == "ACCEPTED"
        and any(
            final.payload.get("event_id") == item.payload.get("finalization_event_id")
            and final.payload.get("attempt_id") == item.payload.get("attempt_id")
            and final.ordinal < item.ordinal
            for final in finalizations
        )
        for item in ready
    )
    if not checks["ready_after_finalize"]:
        reasons.append("rh_ready_host.v1 READY does not follow accepted finalization")

    checks["raw_provenance"] = all(event.source.startswith("/") and event.line_number > 0 for event in events)
    if not checks["raw_provenance"]:
        reasons.append("raw event source references are not absolute file:line values")

    negative = False
    for item in kv + sidecar:
        if item.payload.get("lookup_outcome") in {"MISS", "CROP"}:
            negative = True
    for item in wakes:
        if item.payload.get("grant_state") == "SAME_GENERATION":
            negative = True
    for item in retries:
        if item.payload.get("attempt_number") != 1:
            negative = True
    checks["negative_safety"] = not negative
    if negative:
        reasons.append("genuine miss, crop, same-generation wake, or repeated retry is present")

    bounds = provenance.get("bounds")
    if bounds != {"max_seconds": 600, "max_requests": 6}:
        raise InputError("provenance bounds must declare the exact 600 second/six request limits")
    timestamps = [item.payload["ts_ns"] for item in events if _positive_int(item.payload.get("ts_ns"))]
    request_count = len(_events(events, "admission.v2", "request_created"))
    elapsed_ns = max(timestamps) - min(timestamps) if timestamps else 0
    if elapsed_ns > 600_000_000_000 or request_count > 6:
        checks["negative_safety"] = False
        reasons.append("600 second or six request bound exceeded")

    return checks, sorted(set(reasons))


def reduce_events(events: list[RawEvent], provenance: dict[str, Any]) -> dict[str, Any]:
    """Reduce raw events; missing evidence is NOT_VERIFIED, never PASS."""

    checks = {name: False for name in ORACLE}
    reasons: list[str] = []
    try:
        checks, reasons = _reduce_checks(events, provenance)
    except MissingEvidence as exc:
        reasons.append(str(exc))
    except InputError as exc:
        return {
            "status": STATUS_INVALID_INPUT,
            "oracle": checks,
            "reasons": [str(exc)],
            "raw_event_count": len(events),
            "raw_references": [event.source for event in events],
        }
    status = STATUS_PASS if all(checks.values()) else STATUS_NOT_VERIFIED
    return {
        "status": status,
        "oracle": checks,
        "reasons": sorted(set(reasons)),
        "raw_event_count": len(events),
        "raw_references": [event.source for event in events],
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
