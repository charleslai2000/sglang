#!/usr/bin/env python3
"""Fail-closed offline reducer for the P0-B HOST_ALLOC liveness oracle."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


SCHEMA = "p0b.trace.v1"
TARGET_GPU = "3060"
REQUIRED_EVENT_TYPES = {
    "storage_query",
    "alloc_attempt",
    "wait",
    "allocability_change",
    "generation_advance",
    "retry",
    "reclaim",
    "restore",
    "ready",
}
FORBIDDEN_EVENT_TYPES = {"crop", "genuine_miss", "same_generation_wake"}
IDENTITY_KEYS = ("rid", "session_id", "node_id", "build_id")


def _reject(reason: str, detail: str | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {"status": "REJECTED", "accepted": False, "reason": reason}
    if detail:
        result["detail"] = detail
    return result


def _identity(value: Any) -> dict[str, str] | None:
    if not isinstance(value, dict) or any(not isinstance(value.get(key), str) or not value[key] for key in IDENTITY_KEYS):
        return None
    return {key: value[key] for key in IDENTITY_KEYS}


def _event_identity(event: dict[str, Any], identity: dict[str, str]) -> bool:
    return all(event.get(key) == value for key, value in identity.items())


def reduce_trace(trace: Any) -> dict[str, Any]:
    """Apply all eleven P0-B oracle items; missing or malformed evidence rejects."""
    if not isinstance(trace, dict):
        return _reject("TRACE_NOT_OBJECT")
    if trace.get("schema") != SCHEMA:
        return _reject("SCHEMA_MISMATCH")
    if trace.get("target_gpu") != TARGET_GPU:
        return _reject("TARGET_NOT_3060")
    identity = _identity(trace.get("identity"))
    if identity is None:
        return _reject("IDENTITY_INCOMPLETE")
    events = trace.get("events")
    if not isinstance(events, list) or not events:
        return _reject("EVENTS_INCOMPLETE")
    if len(events) > 64:
        return _reject("EVENTS_UNBOUNDED")

    normalized: list[dict[str, Any]] = []
    for expected_seq, event in enumerate(events, start=1):
        if not isinstance(event, dict):
            return _reject("EVENT_NOT_OBJECT", f"index={expected_seq - 1}")
        if event.get("seq") != expected_seq:
            return _reject("EVENT_SEQUENCE_INVALID", f"expected={expected_seq}")
        event_type = event.get("type")
        if event_type not in REQUIRED_EVENT_TYPES and event_type not in FORBIDDEN_EVENT_TYPES:
            return _reject("UNKNOWN_OR_MISSING_EVENT_TYPE", repr(event_type))
        if not _event_identity(event, identity):
            return _reject("IDENTITY_MISMATCH", f"seq={expected_seq}")
        if event.get("crop_attempted") is True or event.get("genuine_miss") is True:
            return _reject("CROP_OR_GENUINE_MISS")
        normalized.append(event)

    if any(event["type"] in FORBIDDEN_EVENT_TYPES for event in normalized):
        return _reject("FORBIDDEN_NEGATIVE_EVENT")

    def only(event_type: str) -> list[dict[str, Any]]:
        return [event for event in normalized if event["type"] == event_type]

    queries = only("storage_query")
    if len(queries) != 1:
        return _reject("FULL_HIT_EVIDENCE_NOT_EXACTLY_ONCE")
    query = queries[0]
    required_tokens = query.get("kv_required_tokens")
    hit_tokens = query.get("kv_hit_tokens")
    required_mamba = query.get("mamba_required_units")
    hit_mamba = query.get("mamba_hit_units")
    if (
        query.get("hit_kind") != "full"
        or not isinstance(required_tokens, int)
        or required_tokens <= 0
        or hit_tokens != required_tokens
        or not isinstance(required_mamba, int)
        or required_mamba <= 0
        or hit_mamba != required_mamba
    ):
        return _reject("POSITIVE_FULL_KV_MAMBA_HIT_NOT_PROVEN")

    attempts = only("alloc_attempt")
    failures = [event for event in attempts if event.get("outcome") == "terminal_failure"]
    if len(failures) != 1 or failures[0] is not attempts[0]:
        return _reject("TERMINAL_NON_ALLOCABILITY_NOT_PROVEN")
    failure = failures[0]
    if (
        failure.get("non_allocable") is not True
        or failure.get("genuine_miss") is True
        or failure.get("failure_class") not in {"NON_ALLOCABLE", "TERMINAL_ALLOCATION_FAILURE"}
    ):
        return _reject("FAILURE_IS_NOT_NON_ALLOCABILITY")
    failed_domains = failure.get("failed_domains")
    if not isinstance(failed_domains, list) or not failed_domains or any(domain not in {"kv", "mamba"} for domain in failed_domains):
        return _reject("FAILED_DOMAIN_SET_INCOMPLETE")

    waits = only("wait")
    if len(waits) != 1:
        return _reject("HOST_ALLOC_PARK_NOT_EXACTLY_ONCE")
    wait = waits[0]
    if wait.get("state") != "WAIT_CAPACITY" or wait.get("reason") != "HOST_ALLOC" or wait.get("parked") is not True:
        return _reject("HOST_ALLOC_PARK_NOT_PROVEN")
    parked_generations = wait.get("generations")
    if not isinstance(parked_generations, dict) or any(not isinstance(parked_generations.get(domain), int) for domain in failed_domains):
        return _reject("PARK_GENERATION_CURSOR_MISSING")
    fifo_position = wait.get("fifo_position")
    if not isinstance(fifo_position, int) or fifo_position < 0:
        return _reject("FIFO_POSITION_MISSING")

    changes = only("allocability_change")
    if len(changes) != 1:
        return _reject("REAL_ALLOCABILITY_CHANGE_NOT_EXACTLY_ONCE")
    change = changes[0]
    changed_domain = change.get("domain")
    if changed_domain not in failed_domains or change.get("real") is not True or change.get("change_id") in (None, ""):
        return _reject("REAL_ALLOCABILITY_CHANGE_NOT_PROVEN")

    advances = only("generation_advance")
    if len(advances) != 1:
        return _reject("RELEVANT_GENERATION_ADVANCE_NOT_EXACTLY_ONCE")
    advance = advances[0]
    if (
        advance.get("domain") != changed_domain
        or advance.get("change_id") != change.get("change_id")
        or not isinstance(advance.get("before"), int)
        or not isinstance(advance.get("after"), int)
        or advance["after"] <= advance["before"]
        or advance["before"] != parked_generations[changed_domain]
    ):
        return _reject("GENERATION_ADVANCE_NOT_RELEVANT")

    retries = only("retry")
    if len(retries) != 1:
        return _reject("RETRY_NOT_EXACTLY_ONCE")
    retry = retries[0]
    if (
        retry.get("fifo_position") != fifo_position
        or retry.get("grant") is not True
        or retry.get("generation") != advance.get("after")
        or retry.get("generation") <= parked_generations[changed_domain]
        or retry.get("attempt") != 2
    ):
        return _reject("FIFO_RETRY_OR_GENERATION_RULE_FAILED")

    reclaims = only("reclaim")
    if len(reclaims) != 1:
        return _reject("BOUNDED_RECLAIM_NOT_EXACTLY_ONCE")
    reclaim = reclaims[0]
    if (
        reclaim.get("attempt") != 2
        or reclaim.get("bounded") is not True
        or reclaim.get("full_span") is not True
        or reclaim.get("requested_tokens") != required_tokens
        or not isinstance(reclaim.get("reclaimed_tokens"), int)
        or reclaim.get("reclaimed_tokens") <= 0
    ):
        return _reject("BOUNDED_FULL_SPAN_RECLAIM_NOT_PROVEN")

    successful_attempts = [event for event in attempts if event.get("outcome") == "success"]
    if len(successful_attempts) != 1 or successful_attempts[0].get("attempt") != 2 or successful_attempts[0].get("full_span") is not True:
        return _reject("FULL_SPAN_ALLOCATION_NOT_PROVEN")

    restores = only("restore")
    readies = only("ready")
    if len(restores) != 1 or len(readies) != 1:
        return _reject("RESTORE_READY_NOT_EXACTLY_ONCE")
    restore, ready = restores[0], readies[0]
    if (
        restore.get("attempt") != 2
        or restore.get("kv_restored_tokens") != required_tokens
        or restore.get("mamba_restored_units") != required_mamba
        or restore.get("complete") is not True
        or ready.get("attempt") != 2
        or ready.get("state") != "READY"
        or ready.get("kv_complete") is not True
        or ready.get("mamba_complete") is not True
    ):
        return _reject("COMPLETE_KV_MAMBA_READY_NOT_PROVEN")

    return {
        "status": "PASS",
        "accepted": True,
        "oracle_items": 11,
        "rid": identity["rid"],
        "session_id": identity["session_id"],
        "node_id": identity["node_id"],
        "build_id": identity["build_id"],
        "kv_tokens": required_tokens,
        "mamba_units": required_mamba,
        "retry_count": 1,
        "fifo_position": fifo_position,
        "generation": advance["after"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path)
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    try:
        trace = json.loads(args.trace.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        result = _reject("TRACE_READ_FAILED", str(exc))
    else:
        result = reduce_trace(trace)
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("accepted") else 1


if __name__ == "__main__":
    raise SystemExit(main())
