#!/usr/bin/env python3
"""Fail-closed reducer for an immutable, product-emitted P0-B raw bundle.

The reducer accepts only the product event envelopes that are emitted by the
checked-out scheduler/cache paths.  It deliberately does not accept a
normalized trace, a caller supplied verdict, or summary booleans.  Every
derived fact retains an absolute ``file:line`` reference into the raw input.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

STATUS_PASS = "PASS"
STATUS_BLOCKED = "BLOCKED"
STATUS_NOT_VERIFIED = "NOT_VERIFIED"
STATUS_INVALID_INPUT = "INVALID_INPUT"
STATUSES = {STATUS_PASS, STATUS_BLOCKED, STATUS_NOT_VERIFIED, STATUS_INVALID_INPUT}

TASK_ID = "P0-B-HARNESS-IMPLEMENT-20260911-R97"
EPOCH = "2026-09-11"
TARGET = "RTX 3060 12G"
IDENTITY = (
    "run_id",
    "session_id",
    "session_generation",
    "build_rid",
    "node_id",
    "final_kv_hash",
)
ORACLE = (
    "provenance",
    "pid_profile_source_binding",
    "singular_identity",
    "positive_full_hit",
    "host_alloc_park",
    "generation_transition",
    "fifo_predecessor",
    "attempt_lineage",
    "accepted_finalization",
    "ready_after_finalize",
    "raw_provenance",
    "negative_safety",
)

SCHEMAS = {"p0_durable.v3", "host_alloc.v1", "rh_ready_host.v1"}
EVENTS = {
    "p0_durable.v3": {"storage_persisted", "durability_barrier", "storage_query", "backup_ack_drain"},
    "host_alloc.v1": {
        "restore_host_alloc_wait",
        "host_allocability_change",
        "restore_host_alloc_wake_decision",
        "restore_host_alloc_retry_result",
        "restore_hybrid_finalize",
    },
    "rh_ready_host.v1": {"ready_host"},
}
SUMMARY_KEYS = {
    "positive_hit", "full_kv_hit", "complete_kv", "all_sidecars", "complete_mamba",
    "full_span", "accepted", "admitted", "ready", "generation_advanced", "fifo_eligible",
    "predecessor_check_passed", "same_generation_self_wake", "repeated_retry",
    "skipped_eligible_predecessor", "oracle", "verdict", "summary", "status",
}
HEX64 = re.compile(r"^[0-9a-fA-F]{64}$")


class InputError(ValueError):
    """The input is malformed, contradictory, or forged."""


class MissingEvidence(ValueError):
    """The input is well formed but cannot prove the requested chain."""


@dataclass(frozen=True)
class RawEvent:
    schema: str
    event: str
    fields: dict[str, Any]
    source_file: str
    source_line: int
    ordinal: int
    raw: dict[str, Any]

    @property
    def source(self) -> str:
        return f"{self.source_file}:{self.source_line}"

    def value(self, name: str, default: Any = None) -> Any:
        if name in self.fields:
            return self.fields[name]
        context = self.fields.get("trace_context")
        if isinstance(context, dict):
            return context.get(name, default)
        return default


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _positive_int(value: Any) -> bool:
    return _is_int(value) and value > 0


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_hex_map(value: Any, name: str) -> dict[str, str]:
    if not isinstance(value, dict) or not value:
        raise InputError(f"{name} must be a non-empty object")
    result: dict[str, str] = {}
    for key, digest in value.items():
        if not isinstance(key, str) or not os.path.isabs(key):
            raise InputError(f"{name} keys must be absolute paths")
        if not isinstance(digest, str) or not HEX64.fullmatch(digest):
            raise InputError(f"{name} has a non-SHA256 digest")
        result[key] = digest.lower()
    return result


def load_provenance(path: Path, event_paths: Iterable[Path] = ()) -> dict[str, Any]:
    """Load and verify the canonical provenance/hash manifest.

    Hash mismatches are invalid input.  Missing source files are incomplete
    evidence and are reported as NOT_VERIFIED by ``reduce_events``.
    """
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise InputError(f"invalid provenance manifest {path}: {exc}") from exc
    if not isinstance(manifest, dict):
        raise InputError("provenance manifest must be an object")
    if manifest.get("format") != "p0b.raw-bundle.v2":
        raise InputError("unsupported provenance format")
    if "task_id" not in manifest or "epoch" not in manifest:
        raise MissingEvidence("provenance task_id/epoch is missing")
    if manifest.get("task_id") != TASK_ID or manifest.get("epoch") != EPOCH:
        raise InputError("provenance task_id/epoch mismatch")
    if "target" not in manifest or "immutable" not in manifest:
        raise MissingEvidence("provenance target/immutable binding is missing")
    if manifest.get("target") != TARGET or manifest.get("immutable") is not True:
        raise InputError("provenance target/immutable binding mismatch")
    runtime = manifest.get("runtime")
    profile = manifest.get("profile")
    if not isinstance(runtime, dict) or not isinstance(profile, dict):
        raise MissingEvidence("runtime and profile provenance are required")
    if not _positive_int(runtime.get("pid")) or not runtime.get("worker"):
        raise InputError("runtime pid/worker provenance is required")
    if profile.get("gpu") != TARGET or profile.get("compute_capability") != "8.6":
        raise InputError("profile is not the authorized RTX 3060 12G profile")
    if "source_files" not in manifest or "raw_files" not in manifest:
        raise MissingEvidence("source_files/raw_files provenance is missing")
    source_files = _require_hex_map(manifest.get("source_files"), "source_files")
    raw_files = _require_hex_map(manifest.get("raw_files"), "raw_files")
    event_sources = manifest.get("event_sources")
    if not isinstance(event_sources, dict) or not event_sources:
        raise MissingEvidence("event_sources file:line provenance is missing")
    if not all(
        isinstance(key, str)
        and isinstance(value, list)
        and value
        and all(isinstance(ref, str) and ":" in ref for ref in value)
        for key, value in event_sources.items()
    ):
        raise InputError("event_sources must map event names to file:line references")
    capture = manifest.get("capture")
    if not isinstance(capture, dict) or capture.get("complete") is not True:
        raise MissingEvidence("capture completeness is not asserted by the provenance manifest")
    requested = {str(path.resolve()) for path in event_paths}
    if requested and not requested.issubset(raw_files):
        raise MissingEvidence("raw event path is not bound by raw_files")
    for name, expected in raw_files.items():
        candidate = Path(name)
        if not candidate.is_file():
            raise MissingEvidence(f"raw file is missing: {name}")
        if _sha256(candidate) != expected:
            raise InputError(f"raw file hash mismatch: {name}")
    for name, expected in source_files.items():
        candidate = Path(name)
        if not candidate.is_file():
            raise MissingEvidence(f"source file is missing: {name}")
        if _sha256(candidate) != expected:
            raise InputError(f"source file hash mismatch: {name}")
    return manifest


def _validate_common(event: str, fields: dict[str, Any]) -> None:
    required = {"schema", "evt", "ts_mono_ns", "ts_wall_ms", "worker", "rank"}
    if event in {"restore_host_alloc_wait", "host_allocability_change", "restore_host_alloc_wake_decision",
                 "restore_host_alloc_retry_result", "restore_hybrid_finalize"}:
        required |= {"rid", "attempt_id", "cache_instance_id", "trace_context"}
    missing = sorted(key for key in required if key not in fields)
    if missing:
        raise MissingEvidence(f"{event} missing product fields: {', '.join(missing)}")
    if not isinstance(fields["ts_mono_ns"], int) or not isinstance(fields["ts_wall_ms"], int):
        raise InputError(f"{event} has malformed timestamps")
    if fields.get("rid") is not None and not isinstance(fields["rid"], str):
        raise InputError(f"{event} rid is malformed")
    if fields.get("attempt_id") is not None and not isinstance(fields["attempt_id"], str):
        raise InputError(f"{event} attempt_id is malformed")


def parse_raw_jsonl(paths: Iterable[Path]) -> list[RawEvent]:
    """Parse immutable raw JSONL without accepting a normalized trace."""
    events: list[RawEvent] = []
    for given_path in paths:
        path = given_path.resolve()
        if not path.is_file():
            raise MissingEvidence(f"raw event file is missing: {path}")
        with path.open("r", encoding="utf-8") as handle:
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
                event = record.get("evt")
                if schema == "p0b.trace.v1" or "payload" in record or "event" in record or "event_type" in record:
                    raise InputError(f"non-product or synthetic envelope at {path}:{line_number}")
                if schema not in SCHEMAS or event not in EVENTS.get(schema, set()):
                    raise InputError(f"unsupported product event at {path}:{line_number}")
                if set(record) & SUMMARY_KEYS:
                    raise InputError(f"caller-authored summary field at {path}:{line_number}")
                fields = dict(record)
                fields["schema"] = schema
                _validate_common(event, fields)
                events.append(RawEvent(schema, event, fields, str(path), line_number, len(events), record))
    if not events:
        raise MissingEvidence("raw event input is empty")
    return events


def _identity(event: RawEvent) -> tuple[Any, ...]:
    return tuple(event.value(key) for key in IDENTITY)


def _identity_complete(identity: tuple[Any, ...]) -> bool:
    return all(value is not None and value != "" for value in identity)


def _same(a: RawEvent, b: RawEvent, field: str) -> bool:
    return a.value(field) == b.value(field)


def _events(events: Iterable[RawEvent], name: str) -> list[RawEvent]:
    return [event for event in events if event.event == name]


def _positive_mapping(value: Any) -> bool:
    return isinstance(value, dict) and bool(value) and all(_positive_int(item) for item in value.values())


def _full_sidecars(event: RawEvent) -> bool:
    sidecars = event.value("sidecars", event.value("per_sidecar"))
    if not isinstance(sidecars, dict) or not sidecars:
        return False
    for value in sidecars.values():
        if not isinstance(value, dict) or value.get("expected") != value.get("fetched") or not _positive_int(value.get("expected")):
            return False
    return True


def reduce_events(events: list[RawEvent], provenance: dict[str, Any]) -> dict[str, Any]:
    """Reduce product facts; absence is NOT_VERIFIED and contradiction is INVALID_INPUT."""
    checks = {name: False for name in ORACLE}
    reasons: list[str] = []
    refs = [event.source for event in events]
    runtime = provenance.get("runtime", {})

    checks["provenance"] = (
        provenance.get("task_id") == TASK_ID
        and provenance.get("epoch") == EPOCH
        and provenance.get("target") == TARGET
        and provenance.get("immutable") is True
        and isinstance(provenance.get("source_files"), dict)
        and isinstance(provenance.get("raw_files"), dict)
    )
    checks["pid_profile_source_binding"] = all(
        event.value("worker") == runtime.get("worker")
        for event in events
    ) and bool(runtime.get("pid")) and bool(provenance.get("profile", {}).get("profile_id"))

    lifecycle_events = [event for event in events if event.event != "host_allocability_change"]
    identities = [_identity(event) for event in lifecycle_events]
    checks["singular_identity"] = all(_identity_complete(identity) for identity in identities)
    if checks["singular_identity"] and len(set(identities)) != 1:
        raise InputError("contradictory lifecycle identities")
    identity = identities[0] if identities else ()

    barriers = _events(events, "durability_barrier")
    queries = _events(events, "storage_query")
    waits = _events(events, "restore_host_alloc_wait")
    changes = _events(events, "host_allocability_change")
    wakes = _events(events, "restore_host_alloc_wake_decision")
    retries = _events(events, "restore_host_alloc_retry_result")
    finalizations = _events(events, "restore_hybrid_finalize")
    readies = _events(events, "ready_host")

    checks["positive_full_hit"] = any(
        event.value("kv_durable") is True
        and event.value("mamba_durable") is True
        and _positive_int(event.value("kv_completed_tokens"))
        and event.value("kv_completed_tokens") == event.value("kv_requested_tokens")
        and _positive_int(event.value("mamba_expected_pages"))
        and event.value("mamba_expected_pages") == event.value("mamba_succeeded_pages")
        for event in barriers
    ) and any(
        _positive_int(event.value("kv_hit_pages"))
        and _positive_int(event.value("storage_hit_count"))
        and isinstance(event.value("sidecar_hits"), dict)
        and _positive_mapping(event.value("sidecar_hits"))
        for event in queries
    )

    def valid_wait(event: RawEvent) -> bool:
        required_aux = event.value("required_aux_units")
        sidecar_hits = event.value("sidecar_hit_pages")
        return (
            event.value("state") == "WAIT_CAPACITY"
            and event.value("reason") == "HOST_ALLOC"
            and _positive_int(event.value("positive_hit_tokens"))
            and _positive_int(event.value("requested_primary_tokens"))
            and event.value("positive_hit_tokens") >= event.value("requested_primary_tokens")
            and isinstance(required_aux, dict)
            and isinstance(sidecar_hits, dict)
            and all(isinstance(key, str) and _positive_int(value) for key, value in required_aux.items())
            and all(sidecar_hits.get(key, 0) >= value for key, value in required_aux.items())
            and isinstance(event.value("captured_generations"), dict)
            and isinstance(event.value("fifo_sequence"), int)
            and event.value("prefetch_reservation_held") is False
        )

    valid_waits = [event for event in waits if valid_wait(event)]
    checks["host_alloc_park"] = len(valid_waits) == 1

    def valid_change(event: RawEvent) -> bool:
        before, after = event.value("generation_before"), event.value("generation_after")
        return (
            isinstance(event.value("cache_instance_id"), (int, str))
            and isinstance(event.value("pool"), str)
            and _is_int(before) and _is_int(after) and after == before + 1
            and event.value("cause") in {"direct_free", "queued_release_drain", "lock_release_evictable"}
            and _positive_int(event.value("returned_units"))
            and _positive_int(event.value("telemetry_seq"))
        )

    valid_changes = [event for event in changes if valid_change(event)]
    if valid_changes:
        by_pool: dict[tuple[Any, str], list[RawEvent]] = {}
        for event in valid_changes:
            by_pool.setdefault((event.value("cache_instance_id"), event.value("pool")), []).append(event)
        checks["generation_transition"] = all(
            all(right.value("generation_before") == left.value("generation_after") for left, right in zip(sorted(group, key=lambda item: item.ordinal), sorted(group, key=lambda item: item.ordinal)[1:]))
            and any(
                wait.value("cache_instance_id") == key[0]
                and wait.value("captured_generations", {}).get(key[1]) == group[0].value("generation_before")
                for wait in valid_waits
            )
            for key, group in by_pool.items()
        )
        if not checks["generation_transition"]:
            reasons.append("blocked-domain generation edge is missing or non-contiguous")
    if checks["generation_transition"] and valid_waits:
        target_wait = valid_waits[0]
        target_changes = [event for event in valid_changes if event.value("cache_instance_id") == target_wait.value("cache_instance_id") and event.value("pool") in target_wait.value("captured_generations", {})]
        checks["generation_transition"] = all(
            any(
                event.ordinal > target_wait.ordinal
                and event.value("pool") == pool
                and event.value("generation_before")
                == target_wait.value("captured_generations", {}).get(pool)
                for event in valid_changes
            )
            for pool in target_wait.value("blocked_domains", [])
        )

    grants = [event for event in wakes if event.value("decision") == "grant" and event.value("retry_grant") is True and event.value("retry_skip") is False]
    checks["fifo_predecessor"] = bool(valid_waits and len(grants) == 1 and grants[0].value("fifo_sequence") == valid_waits[0].value("fifo_sequence"))
    if checks["fifo_predecessor"]:
        checks["fifo_predecessor"] = all(
            event.value("fifo_sequence") >= grants[0].value("fifo_sequence")
            for event in valid_waits
        ) and all(event.ordinal < grants[0].ordinal for event in valid_waits)

    if len(retries) == 1 and len(grants) == 1 and valid_waits:
        retry = retries[0]
        grant = grants[0]
        prior_attempt = valid_waits[0].value("attempt_id")
        checks["attempt_lineage"] = (
            retry.value("retry_outcome") == "revoked_alloc_failed"
            and retry.value("terminal") == "revoked_alloc_failed"
            and retry.value("genuine_miss") is False
            and _positive_int(retry.value("full_frontier_tokens"))
            and retry.value("attempt_id") not in {None, ""}
            and retry.value("attempt_id") != prior_attempt
            and grant.value("attempt_id") == prior_attempt
            and all(_same(retry, event, "rid") for event in [grant])
        )

    accepted = [event for event in finalizations if event.value("result") == "accepted" and event.value("all_or_nothing") is True and event.value("restore_state_after") == "READY" and _positive_int(event.value("kv_expected")) and event.value("kv_expected") == event.value("kv_fetched") and _full_sidecars(event)]
    checks["accepted_finalization"] = len(accepted) == 1 and bool(retries) and accepted[0].value("attempt_id") == retries[0].value("attempt_id")
    checks["ready_after_finalize"] = len(readies) == 1 and bool(accepted) and readies[0].ordinal > accepted[0].ordinal and readies[0].value("attempt_id") == accepted[0].value("attempt_id") and readies[0].value("finalize_result") == "accepted" and readies[0].value("issue_origin") == "DEMAND_RETRY" and _positive_int(readies[0].value("completed_kv_tokens"))
    event_sources = provenance.get("event_sources", {})
    checks["raw_provenance"] = all(
        Path(event.source_file).is_absolute()
        and event.source_line > 0
        and event.source in event_sources.get(event.event, [])
        for event in events
    )
    checks["negative_safety"] = not any(
        event.value(name) is True
        for event in events
        for name in ("genuine_miss", "crop_attempted", "lower_checkpoint_queried", "partial_sidecar", "discarded_hybrid", "recompute_fallback", "retry_skip")
    )

    missing = [name for name, passed in checks.items() if not passed]
    if missing:
        reasons.extend(f"{name} is not proven" for name in missing)
    status = STATUS_PASS if not missing else STATUS_NOT_VERIFIED
    return {"status": status, "oracle": checks, "reasons": sorted(set(reasons)), "raw_event_count": len(events), "raw_references": refs, "identity": identity}


def reduce_paths(events_paths: list[Path], provenance_path: Path) -> dict[str, Any]:
    try:
        provenance = load_provenance(provenance_path, events_paths)
        events = parse_raw_jsonl(events_paths)
        return reduce_events(events, provenance)
    except MissingEvidence as exc:
        return {"status": STATUS_NOT_VERIFIED, "oracle": {}, "reasons": [str(exc)]}
    except InputError as exc:
        return {"status": STATUS_INVALID_INPUT, "oracle": {}, "reasons": [str(exc)]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", nargs="+", type=Path, required=True)
    parser.add_argument("--provenance", type=Path, required=True)
    args = parser.parse_args(argv)
    result = reduce_paths(args.events, args.provenance)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
