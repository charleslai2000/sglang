#!/usr/bin/env python3
"""R107 fail-closed offline reducer for the canonical P0-B 11-predicate oracle.

The reducer consumes only real captured product log text:

  * ``[HAE] {json}`` records with ``schema == "host_alloc.v1"`` and one of the
    real HOST_ALLOC event names (``restore_host_alloc_wait``,
    ``restore_host_alloc_wake_decision``, ``restore_host_alloc_retry_result``,
    ``restore_hybrid_finalize``, ``host_allocability_change``);
  * the real ``[P3] ... evt=ready_host schema=rh_ready_host.v1 ...`` line;
  * ``p0_durable`` JSONL records (``"trace": "p0_durable"``) written by the
    marker-gated durability producer (``build_complete``, ``backup_ack_drain``,
    ``storage_persisted``, ``durability_barrier``).

Pure Python standard library.  No product imports, no monkeypatching, no
synthesis of product events, no runtime instrumentation.  Every consumed
record keeps its absolute ``file:line`` reference.  Any missing required
field, any contradictory identity/join, or any unrecognized lineage reason is
``NOT_VERIFIED`` with an explicit reason; the reducer never backfills a fact
from timestamps or nearby rows and never trusts a bundle's own ``oracle`` /
``verdict`` / ``status`` / summary claims.

Run:

    python p0b_reducer.py --events <raw.log> [<raw2.log> ...] \
        --manifest <manifest.json>
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass
from typing import Any, Iterable, Optional

# ---------------------------------------------------------------------------
# Frozen contract
# ---------------------------------------------------------------------------

# Exactly eleven predicates, in canonical order.  ``raw_provenance`` is an
# input gate verified before reduction and is NOT one of the eleven;
# ``negative_safety`` IS predicate 11.
ORACLE_NAMES = (
    "provenance",
    "singular_identity",
    "pid_profile_source_binding",
    "positive_full_hit",
    "host_alloc_park",
    "generation_transition",
    "fifo_predecessor",
    "attempt_lineage",
    "accepted_finalization",
    "ready_after_finalize",
    "negative_safety",
)

STATUS_VERIFIED = "VERIFIED"
STATUS_NOT_VERIFIED = "NOT_VERIFIED"

MANIFEST_FORMAT = "p0b.raw-bundle.v3"
TASK_ID = "P0-B-REDUCER-FREEZE-20260911-R107"
EPOCH = "2026-09-11"

HOST_ALLOC_SCHEMA = "host_alloc.v1"
READY_SCHEMA = "rh_ready_host.v1"
DURABLE_TRACE = "p0_durable"

HOST_ALLOC_EVENTS = frozenset(
    {
        "restore_host_alloc_wait",
        "restore_host_alloc_wake_decision",
        "restore_host_alloc_retry_result",
        "restore_hybrid_finalize",
        "host_allocability_change",
    }
)

# Scheduler-owned terminal states that count as a released FIFO waiter
# (scheduler.py ``_HOST_ALLOC_RELEASED_TERMINAL_STATES``).
RELEASED_TERMINAL_STATES = frozenset(
    {"RELEASED", "TIMEOUT", "RESTORED", "MISS", "ABORTED", "RECOMPUTE", "ABANDONED"}
)

# The exact fail-closed reasons emitted by the producer-owned FIFO arbiter.
FAIL_CLOSED_PREDECESSOR_REASONS = frozenset(
    {
        "no_wait_cursor",
        "no_released_predecessor",
        "predecessor_terminal_incomplete",
        "predecessor_terminal_state_unrecognized",
    }
)

RECOGNIZED_RETRY_OUTCOMES = frozenset(
    {"revoked_alloc_failed", "forfeited_alloc_failed"}
)

# A raw record carrying any of these keys is a caller-authored summary/verdict
# claim and is rejected by the input gate.  Real product fields such as
# ``result`` (values ``accepted``/``discarded``/``complete``), ``terminal``,
# ``retry_outcome`` and ``decision`` are NOT in this set.
FORBIDDEN_SUMMARY_KEYS = frozenset(
    {
        "oracle",
        "verdict",
        "status",
        "summary",
        "positive_hit",
        "full_kv_hit",
        "complete_kv",
        "all_sidecars",
        "complete_mamba",
        "full_span",
        "accepted",
        "admitted",
        "ready",
        "generation_advanced",
        "fifo_eligible",
        "predecessor_check_passed",
        "same_generation_self_wake",
        "repeated_retry",
        "skipped_eligible_predecessor",
        "partial_sidecar",
        "discarded_hybrid",
        "recompute_fallback",
    }
)

_HEX64 = re.compile(r"^[0-9a-fA-F]{64}$")
_INT_RE = re.compile(r"^-?\d+$")
_KV_SPLIT_RE = re.compile(r"\s+(?=[A-Za-z_][A-Za-z0-9_]*=)")


def oracle_names() -> tuple[str, ...]:
    """Return the frozen tuple of exactly eleven predicate names."""
    return ORACLE_NAMES


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_int_val(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _positive_int(value: Any) -> bool:
    return _is_int_val(value) and value > 0


def _nonempty_str(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _parse_scalar(text: str) -> Any:
    text = text.strip()
    if text in ("None", "null"):
        return None
    if text == "True":
        return True
    if text == "False":
        return False
    if _INT_RE.fullmatch(text):
        return int(text)
    if text[:1] in ("{", "["):
        try:
            return ast.literal_eval(text)
        except (ValueError, SyntaxError):
            return text
    return text


def _parse_ready_kv_line(line: str) -> dict[str, Any]:
    """Parse the real ``[P3] ... evt=ready_host ...`` key=value line.

    The producer prints the fields with ``%s`` in a fixed order; values are
    Python ``str``/``int``/``None``/``dict``/``list`` reprs.  Splitting only on
    whitespace directly preceding a ``key=`` token keeps bracketed/dict reprs
    with internal spaces intact.
    """
    index = line.find("evt=ready_host")
    if index < 0:
        raise ValueError("evt=ready_host not present")
    payload = line[index:]
    fields: dict[str, Any] = {}
    for token in _KV_SPLIT_RE.split(payload):
        if "=" not in token:
            continue
        key, _, value = token.partition("=")
        key = key.strip()
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            continue
        fields[key] = _parse_scalar(value)
    return fields


# ---------------------------------------------------------------------------
# Raw records
# ---------------------------------------------------------------------------


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

    def v(self, name: str, default: Any = None) -> Any:
        if name in self.fields:
            return self.fields[name]
        for container in ("producer", "trace_context"):
            nested = self.fields.get(container)
            if isinstance(nested, dict) and name in nested:
                return nested[name]
        return default

    def producer_identity(self, name: str) -> Any:
        """Producer identity value; p0_durable keeps it under ``producer``."""
        if self.schema == DURABLE_TRACE:
            producer = self.fields.get("producer")
            if isinstance(producer, dict) and name in producer:
                return producer[name]
        return self.v(name)


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def parse_events(paths: Iterable[str]) -> tuple[list[RawEvent], list[str]]:
    """Parse product log lines and preserve ``file:line`` for every record."""
    events: list[RawEvent] = []
    errors: list[str] = []
    for given in paths:
        path = os.path.abspath(given)
        if not os.path.isfile(path):
            errors.append(f"raw event file is missing: {path}")
            continue
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            for line_number, line in enumerate(handle, 1):
                text = line.rstrip("\n")
                if not text.strip():
                    continue
                if "[HAE] " in text:
                    payload = text.split("[HAE] ", 1)[1]
                    try:
                        record = json.loads(payload)
                    except json.JSONDecodeError as exc:
                        errors.append(
                            f"invalid [HAE] JSON at {path}:{line_number}: {exc}"
                        )
                        continue
                    if not isinstance(record, dict):
                        errors.append(f"[HAE] record not an object at {path}:{line_number}")
                        continue
                    schema = record.get("schema")
                    event = record.get("evt")
                    if schema != HOST_ALLOC_SCHEMA or event not in HOST_ALLOC_EVENTS:
                        errors.append(
                            f"unsupported HOST_ALLOC event at {path}:{line_number}: "
                            f"schema={schema!r} evt={event!r}"
                        )
                        continue
                    forbidden = sorted(set(record) & FORBIDDEN_SUMMARY_KEYS)
                    if forbidden:
                        errors.append(
                            f"caller-authored summary field at {path}:{line_number}: "
                            f"{', '.join(forbidden)}"
                        )
                        continue
                    events.append(
                        RawEvent(
                            HOST_ALLOC_SCHEMA,
                            str(event),
                            record,
                            path,
                            line_number,
                            len(events),
                            record,
                        )
                    )
                elif "evt=ready_host" in text and "schema=rh_ready_host.v1" in text:
                    try:
                        fields = _parse_ready_kv_line(text)
                    except ValueError as exc:
                        errors.append(f"malformed ready_host line at {path}:{line_number}: {exc}")
                        continue
                    forbidden = sorted(set(fields) & FORBIDDEN_SUMMARY_KEYS)
                    if forbidden:
                        errors.append(
                            f"caller-authored summary field at {path}:{line_number}: "
                            f"{', '.join(forbidden)}"
                        )
                        continue
                    events.append(
                        RawEvent(
                            READY_SCHEMA,
                            "ready_host",
                            fields,
                            path,
                            line_number,
                            len(events),
                            fields,
                        )
                    )
                else:
                    stripped = text.strip()
                    if not (stripped.startswith("{") and stripped.endswith("}")):
                        continue
                    try:
                        record = json.loads(stripped)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(record, dict) or record.get("trace") != DURABLE_TRACE:
                        continue
                    event = record.get("evt")
                    if not isinstance(event, str) or not event:
                        errors.append(
                            f"p0_durable record without evt at {path}:{line_number}"
                        )
                        continue
                    forbidden = sorted(set(record) & FORBIDDEN_SUMMARY_KEYS)
                    if forbidden:
                        errors.append(
                            f"caller-authored summary field at {path}:{line_number}: "
                            f"{', '.join(forbidden)}"
                        )
                        continue
                    events.append(
                        RawEvent(
                            DURABLE_TRACE,
                            event,
                            record,
                            path,
                            line_number,
                            len(events),
                            record,
                        )
                    )
    return events, errors


# ---------------------------------------------------------------------------
# Input gate: raw provenance
# ---------------------------------------------------------------------------


def _contains_forbidden_key(value: Any) -> Optional[str]:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in FORBIDDEN_SUMMARY_KEYS:
                return str(key)
            found = _contains_forbidden_key(item)
            if found:
                return found
    elif isinstance(value, list):
        for item in value:
            found = _contains_forbidden_key(item)
            if found:
                return found
    return None


def verify_manifest(
    manifest_path: str, event_paths: Iterable[str]
) -> tuple[dict[str, Any], list[str]]:
    """Verify the raw-provenance input gate (not one of the eleven predicates).

    Hash mismatches, missing files, malformed/absent manifest fields, or any
    caller-authored summary/verdict key make the gate fail closed.
    """
    errors: list[str] = []
    try:
        with open(manifest_path, "r", encoding="utf-8") as handle:
            manifest = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        return {}, [f"invalid provenance manifest {manifest_path}: {exc}"]
    if not isinstance(manifest, dict):
        return {}, ["provenance manifest must be a JSON object"]

    forbidden = _contains_forbidden_key(manifest)
    if forbidden:
        errors.append(f"manifest carries caller-authored summary/verdict key: {forbidden}")
    if manifest.get("format") != MANIFEST_FORMAT:
        errors.append(f"unsupported manifest format: {manifest.get('format')!r}")

    runtime = manifest.get("runtime")
    if not isinstance(runtime, dict):
        errors.append("manifest runtime binding is missing")
        runtime = {}
    if not _positive_int(runtime.get("process_id")):
        errors.append("manifest runtime.process_id is missing")
    for name in ("run_id", "profile_id", "source_build"):
        if not _nonempty_str(runtime.get(name)):
            errors.append(f"manifest runtime.{name} is missing")

    target = manifest.get("target")
    if not isinstance(target, dict):
        errors.append("manifest target binding is missing")
        target = {}
    if not _nonempty_str(target.get("rid")):
        errors.append("manifest target.rid is missing")
    if not _nonempty_str(target.get("lifecycle_key")):
        errors.append("manifest target.lifecycle_key is missing")

    requested = {os.path.abspath(path) for path in event_paths}

    raw_files = manifest.get("raw_files")
    if not isinstance(raw_files, dict) or not raw_files:
        errors.append("manifest raw_files binding is missing")
    else:
        for name, digest in raw_files.items():
            if not (isinstance(name, str) and os.path.isabs(name)):
                errors.append(f"raw_files key is not an absolute path: {name!r}")
            if not (isinstance(digest, str) and _HEX64.fullmatch(digest)):
                errors.append(f"raw_files digest is not SHA256: {name!r}")
        for path in sorted(requested):
            if path not in raw_files:
                errors.append(f"raw event path is not bound by raw_files: {path}")
        for name, digest in raw_files.items():
            if not os.path.isfile(name):
                errors.append(f"raw file is missing: {name}")
            elif isinstance(digest, str) and _sha256_file(name) != digest.lower():
                errors.append(f"raw file hash mismatch: {name}")

    source_files = manifest.get("source_files")
    if not isinstance(source_files, dict) or not source_files:
        errors.append("manifest source_files binding is missing")
    else:
        for name, digest in source_files.items():
            if not (isinstance(name, str) and os.path.isabs(name)):
                errors.append(f"source_files key is not an absolute path: {name!r}")
            if not (isinstance(digest, str) and _HEX64.fullmatch(digest)):
                errors.append(f"source_files digest is not SHA256: {name!r}")
        for name, digest in source_files.items():
            if not os.path.isfile(name):
                errors.append(f"source file is missing: {name}")
            elif isinstance(digest, str) and _sha256_file(name) != digest.lower():
                errors.append(f"source file hash mismatch: {name}")
    return manifest, errors


# ---------------------------------------------------------------------------
# Predicate helpers
# ---------------------------------------------------------------------------


def _target_session_generation(lifecycle_key: Any) -> Optional[str]:
    if not _nonempty_str(lifecycle_key) or ":" not in lifecycle_key:
        return None
    return lifecycle_key.rsplit(":", 1)[1]


def _complete_trace_context(event: RawEvent) -> bool:
    return (
        _nonempty_str(event.v("session_id"))
        and _nonempty_str(event.v("build_rid"))
        and event.v("session_generation") is not None
        and _nonempty_str(event.v("node_id"))
        and _nonempty_str(event.v("final_kv_hash"))
    )


def _valid_park(event: RawEvent) -> bool:
    captured = event.v("captured_generations")
    blocked = event.v("blocked_domains")
    return (
        event.v("state") == "WAIT_CAPACITY"
        and event.v("reason") == "HOST_ALLOC"
        and _nonempty_str(event.v("wait_id"))
        and isinstance(captured, dict)
        and bool(captured)
        and all(_is_int_val(value) for value in captured.values())
        and isinstance(blocked, list)
        and bool(blocked)
        and _is_int_val(event.v("fifo_sequence"))
        and event.v("fifo_sequence") >= 0
        and _positive_int(event.v("requested_primary_tokens"))
    )


def _full_sidecars(event: RawEvent) -> bool:
    sidecars = event.v("sidecars")
    if not isinstance(sidecars, dict) or not sidecars:
        return False
    positive = False
    for value in sidecars.values():
        if not isinstance(value, dict):
            return False
        expected = value.get("expected")
        fetched = value.get("fetched")
        if not (_is_int_val(expected) and _is_int_val(fetched)):
            return False
        if expected != fetched:
            return False
        if expected > 0:
            positive = True
    return positive


def _is_post_wake_retry(event: RawEvent) -> bool:
    """Whether a ``restore_host_alloc_retry_result`` is a post-wake retry.

    Real emission (``unified_radix_cache.py:5460,6575``): the retry_result is
    emitted only on allocation failure.  The mandatory pre-wake failure carries
    ``attempt_id=None`` and ``retry_grant=False`` (``host_alloc_attempt_id`` is
    unset until the scheduler's post-wake ``RETRY_PREFETCH``,
    ``scheduler.py:4250-4254``); a post-wake failure carries a non-empty
    host-alloc attempt id and ``retry_grant=True``.
    """
    return event.v("retry_grant") is True or _nonempty_str(event.v("attempt_id"))


def _attempt_in_namespace(attempt_id: Any, rid: Any, *, prefetch: bool) -> bool:
    """Validate a real attempt id against its producer namespace.

    ``_claim_prefetch`` builds ``f"{rid}:prefetch:{seq}"``
    (``scheduler.py:3130-3139``); the HOST_ALLOC retry builds ``f"{rid}:{seq}"``
    (``scheduler.py:4251-4254``).  A finalize/retry carries the host-alloc
    namespace and READY the prefetch namespace.
    """
    if not _nonempty_str(attempt_id) or not _nonempty_str(rid):
        return False
    suffix = r":prefetch:(\d+)" if prefetch else r":(\d+)"
    return re.fullmatch(re.escape(str(rid)) + suffix, str(attempt_id)) is not None


def _accepted_finalize(event: RawEvent) -> bool:
    return (
        event.v("result") == "accepted"
        and event.v("all_or_nothing") is True
        and event.v("restore_state_after") == "READY"
        and _positive_int(event.v("kv_expected"))
        and event.v("kv_fetched") == event.v("kv_expected")
        and _full_sidecars(event)
        and _nonempty_str(event.v("attempt_id"))
        and _nonempty_str(event.v("wake_event_id"))
    )


def _blocked_domain_set(event: RawEvent) -> Optional[frozenset[str]]:
    domains = event.v("blocked_domains")
    if isinstance(domains, list) and domains:
        return frozenset(str(item) for item in domains)
    generations = event.v("blocked_pool_generations")
    if isinstance(generations, dict) and generations:
        return frozenset(str(key) for key in generations)
    return None


def _eligible_release_exists(grant: RawEvent, events: Iterable[RawEvent]) -> bool:
    """Whether a released predecessor that should have been named exists.

    Used only for the negative-safety predicate.  A release is eligible when
    it is in an accepted released terminal state, its FIFO sequence strictly
    precedes the grant's, its record precedes the grant, and its blocked-domain
    set is compatible with the grant's (compared only when both expose one).
    """
    sequence = grant.v("fifo_sequence")
    blocked = _blocked_domain_set(grant)
    for event in events:
        if event.event != "restore_host_alloc_wake_decision":
            continue
        if event.v("decision") != "release":
            continue
        if event.v("terminal_state") not in RELEASED_TERMINAL_STATES:
            continue
        if not (event.ordinal < grant.ordinal):
            continue
        release_sequence = event.v("fifo_sequence")
        if _is_int_val(sequence) and _is_int_val(release_sequence):
            if release_sequence >= sequence:
                continue
        release_blocked = _blocked_domain_set(event)
        if blocked is not None and release_blocked is not None and blocked != release_blocked:
            continue
        return True
    return False


# ---------------------------------------------------------------------------
# Reduction
# ---------------------------------------------------------------------------


def reduce_events(
    events: list[RawEvent], manifest: dict[str, Any]
) -> dict[str, Any]:
    predicates: dict[str, dict[str, Any]] = {
        name: {"name": name, "passed": False, "reason": "not evaluated"}
        for name in ORACLE_NAMES
    }

    def fail(name: str, reason: str) -> None:
        predicates[name]["passed"] = False
        predicates[name]["reason"] = reason

    def mark_ok(name: str) -> None:
        predicates[name]["passed"] = True
        predicates[name]["reason"] = ""

    runtime = manifest.get("runtime") if isinstance(manifest.get("runtime"), dict) else {}
    target = manifest.get("target") if isinstance(manifest.get("target"), dict) else {}
    target_rid = target.get("rid")
    target_lifecycle_key = target.get("lifecycle_key")

    # -- predicate 1: provenance (manifest/source/PID binding) --------------
    p1: list[str] = []
    if manifest.get("format") != MANIFEST_FORMAT:
        p1.append("manifest format missing/incorrect")
    if not _positive_int(runtime.get("process_id")):
        p1.append("runtime.process_id missing")
    for name in ("run_id", "profile_id", "source_build"):
        if not _nonempty_str(runtime.get(name)):
            p1.append(f"runtime.{name} missing")
    if not isinstance(manifest.get("raw_files"), dict) or not manifest.get("raw_files"):
        p1.append("raw_files binding missing")
    if not isinstance(manifest.get("source_files"), dict) or not manifest.get("source_files"):
        p1.append("source_files binding missing")
    if not _nonempty_str(target_rid):
        p1.append("target.rid missing")
    if not _nonempty_str(target_lifecycle_key):
        p1.append("target.lifecycle_key missing")
    if not events:
        p1.append("no consumed product records")
    if p1:
        fail("provenance", "; ".join(p1))
    else:
        mark_ok("provenance")

    # -- predicate 2: singular identity -------------------------------------
    target_events = [
        event
        for event in events
        if event.event != "host_allocability_change" and event.v("rid") == target_rid
    ]
    p2: list[str] = []
    tuples: set[tuple[Any, Any, Any]] = set()
    for event in target_events:
        lifecycle_key = event.v("lifecycle_key")
        run_id = event.producer_identity("run_id")
        process_id = event.producer_identity("process_id")
        if not _nonempty_str(lifecycle_key):
            p2.append(f"target record {event.source} missing lifecycle_key")
            continue
        if not _nonempty_str(run_id) or not _positive_int(process_id):
            p2.append(f"target record {event.source} missing run/process identity")
            continue
        tuples.add((process_id, run_id, lifecycle_key))
    if not target_events:
        p2.append("no target-scoped records")
    if len(tuples) > 1:
        p2.append(f"target records carry {len(tuples)} distinct lifecycle tuples")
    if tuples and target_lifecycle_key not in {item[2] for item in tuples}:
        p2.append("target lifecycle_key does not match the manifest")
    if p2:
        fail("singular_identity", "; ".join(p2))
    else:
        mark_ok("singular_identity")

    # -- predicate 3: pid/profile/source binding ----------------------------
    p3: list[str] = []
    for event in events:
        process_id = event.producer_identity("process_id")
        run_id = event.producer_identity("run_id")
        profile_id = event.producer_identity("profile_id")
        source_build = event.producer_identity("source_build")
        if not (
            _positive_int(process_id)
            and _nonempty_str(run_id)
            and _nonempty_str(profile_id)
            and _nonempty_str(source_build)
        ):
            p3.append(f"{event.source} missing producer identity fields")
            continue
        if (
            process_id != runtime.get("process_id")
            or run_id != runtime.get("run_id")
            or profile_id != runtime.get("profile_id")
            or source_build != runtime.get("source_build")
        ):
            p3.append(f"{event.source} producer identity != manifest runtime")
    if p3:
        fail("pid_profile_source_binding", "; ".join(p3))
    else:
        mark_ok("pid_profile_source_binding")

    # -- gathered facts -----------------------------------------------------
    target_wait_events = [
        event
        for event in events
        if event.event == "restore_host_alloc_wait" and event.v("rid") == target_rid
    ]
    valid_waits = [event for event in target_wait_events if _valid_park(event)]
    grants = [
        event
        for event in events
        if event.event == "restore_host_alloc_wake_decision"
        and event.v("rid") == target_rid
        and event.v("decision") == "grant"
        and event.v("retry_grant") is True
        and event.v("retry_skip") is False
        and _nonempty_str(event.v("event_id"))
        and event.v("event_id") == event.v("wake_event_id")
    ]
    finals = [
        event
        for event in events
        if event.event == "restore_hybrid_finalize" and event.v("rid") == target_rid
    ]
    readies = [
        event
        for event in events
        if event.event == "ready_host" and event.v("rid") == target_rid
    ]
    retries = [
        event
        for event in events
        if event.event == "restore_host_alloc_retry_result" and event.v("rid") == target_rid
    ]
    accepted = [event for event in finals if _accepted_finalize(event)]

    deciding_grant: Optional[RawEvent] = None
    if accepted and _nonempty_str(accepted[0].v("wake_event_id")):
        candidates = [
            grant for grant in grants if grant.v("event_id") == accepted[0].v("wake_event_id")
        ]
        if len(candidates) == 1:
            deciding_grant = candidates[0]

    deciding_park: Optional[RawEvent] = None
    if deciding_grant is not None and _is_int_val(deciding_grant.v("fifo_sequence")):
        candidates = [
            wait
            for wait in valid_waits
            if wait.v("fifo_sequence") == deciding_grant.v("fifo_sequence")
        ]
        if len(candidates) == 1:
            deciding_park = candidates[0]

    # -- predicate 4: positive full hit -------------------------------------
    target_generation = _target_session_generation(target_lifecycle_key)
    barriers = [
        event
        for event in events
        if event.schema == DURABLE_TRACE
        and event.event == "durability_barrier"
        and target_generation is not None
        and str(event.v("session_generation")) == target_generation
    ]
    full_barriers = [
        event
        for event in barriers
        if event.v("kv_durable") is True
        and event.v("mamba_durable") is True
        and _positive_int(event.v("kv_completed_tokens"))
        and _positive_int(event.v("kv_requested_tokens"))
        and event.v("kv_completed_tokens") == event.v("kv_requested_tokens")
        and _positive_int(event.v("mamba_expected_pages"))
        and event.v("mamba_succeeded_pages") == event.v("mamba_expected_pages")
        and _complete_trace_context(event)
    ]
    park_positive = any(
        wait.v("state") == "WAIT_CAPACITY"
        and wait.v("reason") == "HOST_ALLOC"
        and _positive_int(wait.v("positive_hit_tokens"))
        and wait.v("positive_hit_tokens") >= wait.v("requested_primary_tokens")
        for wait in target_wait_events
    )
    if not target_generation:
        fail("positive_full_hit", "target lifecycle_key has no session generation")
    elif not full_barriers:
        fail("positive_full_hit", "no complete positive KV+Mamba durability_barrier for the target")
    elif not park_positive:
        fail("positive_full_hit", "target park does not carry a positive full-hit token count")
    else:
        mark_ok("positive_full_hit")

    # -- predicate 5: host alloc park ---------------------------------------
    if not valid_waits:
        fail("host_alloc_park", "no target WAIT_CAPACITY/HOST_ALLOC park with captured generations and wait_id")
    else:
        mark_ok("host_alloc_park")

    # -- predicate 6: generation transition ---------------------------------
    # Authoritative signal: the producer-emitted ``captured_generations`` on the
    # deciding park and ``current_generations`` on the deciding grant
    # (``host_allocability_snapshot``, ``unified_radix_cache.py:3838-3882``).
    # ``host_allocability_change`` records are deliberately sampled
    # (HEAD 16 / stride 128 / max 64 per key / max 256 per instance;
    # ``unified_radix_cache.py:155-164,3784-3793``) and are CORROBORATING only:
    # absence never fails; a present edge for the pool in the park->grant
    # window must not contradict (wrong instance, non-monotonic, out of range).
    p6: list[str] = []
    sampled_edges_seen: dict[str, int] = {}
    if deciding_grant is None:
        p6.append("no deciding grant")
    if deciding_park is None:
        p6.append("no park matching the deciding grant fifo_sequence")
    instance: Any = None
    if not p6:
        instance = deciding_park.v("cache_instance_id")
        grant_instance = deciding_grant.v("cache_instance_id")
        if not _is_int_val(instance):
            p6.append("park cache_instance_id missing")
        elif grant_instance != instance:
            p6.append(
                f"grant cache_instance_id {grant_instance!r} != park cache "
                f"instance {instance!r}"
            )
        if deciding_park.ordinal >= deciding_grant.ordinal:
            p6.append("deciding park does not strictly precede the deciding grant")
    if not p6:
        captured_all = deciding_park.v("captured_generations") or {}
        current_all = deciding_grant.v("current_generations") or {}
        blocked = list(deciding_park.v("blocked_domains") or [])
        for pool in blocked:
            cap = captured_all.get(pool)
            target_current = current_all.get(pool)
            if not (_is_int_val(cap) and _is_int_val(target_current)):
                p6.append(f"pool {pool} generation missing on captured/current cursor")
                continue
            if target_current <= cap:
                p6.append(
                    f"pool {pool} not strictly advanced ({cap}->{target_current})"
                )
                continue
            window = [
                change
                for change in events
                if change.event == "host_allocability_change"
                and change.v("pool") == pool
                and deciding_park.ordinal < change.ordinal <= deciding_grant.ordinal
            ]
            sampled_edges_seen[pool] = 0
            for change in window:
                edge_instance = change.v("cache_instance_id")
                before = change.v("generation_before")
                after = change.v("generation_after")
                if edge_instance != instance:
                    p6.append(
                        f"pool {pool} contradictory sampled edge at {change.source}: "
                        f"cache_instance_id {edge_instance!r} != {instance!r}"
                    )
                    continue
                if not (
                    _is_int_val(before) and _is_int_val(after) and after == before + 1
                ):
                    p6.append(
                        f"pool {pool} contradictory sampled edge at {change.source}: "
                        f"non-monotonic {before!r}->{after!r}"
                    )
                    continue
                if before < cap or after > target_current:
                    p6.append(
                        f"pool {pool} contradictory sampled edge at {change.source}: "
                        f"{before}->{after} out of range {cap}..{target_current}"
                    )
                    continue
                sampled_edges_seen[pool] += 1
    predicates["generation_transition"]["sampled_edges_seen"] = sampled_edges_seen
    predicates["generation_transition"]["sampling"] = (
        "host_allocability_change is a deliberately sampled corroborating "
        "subsequence (HEAD 16 / stride 128 / max 64 per key / max 256 per "
        "instance; unified_radix_cache.py:155-164,3784-3793); absence never "
        "fails, only a contradictory present edge does"
    )
    if p6:
        fail("generation_transition", "; ".join(p6))
    else:
        mark_ok("generation_transition")

    # -- predicate 7: FIFO predecessor --------------------------------------
    p7: list[str] = []
    if deciding_grant is None:
        p7.append("no deciding grant")
    else:
        reason = deciding_grant.v("predecessor_lineage_reason")
        if reason is not None:
            if reason in FAIL_CLOSED_PREDECESSOR_REASONS:
                p7.append(f"fail-closed predecessor lineage reason: {reason}")
            else:
                p7.append(f"unrecognized predecessor lineage reason: {reason!r}")
        else:
            predecessor_wait = deciding_grant.v("predecessor_wait_id")
            terminal_event_id = deciding_grant.v("predecessor_terminal_event_id")
            terminal_state = deciding_grant.v("predecessor_terminal_state")
            if not (
                _nonempty_str(predecessor_wait)
                and _nonempty_str(terminal_event_id)
                and _nonempty_str(terminal_state)
            ):
                p7.append("incomplete predecessor identity")
            elif terminal_state not in RELEASED_TERMINAL_STATES:
                p7.append(
                    f"predecessor terminal state not an accepted release state: {terminal_state}"
                )
            else:
                terminals = [
                    event
                    for event in events
                    if event.event == "restore_host_alloc_wake_decision"
                    and event.v("decision") == "release"
                    and event.v("event_id") == terminal_event_id
                ]
                if len(terminals) != 1:
                    p7.append("predecessor terminal event not found uniquely")
                else:
                    terminal = terminals[0]
                    if terminal.v("wait_id") != predecessor_wait:
                        p7.append("predecessor terminal wait_id mismatch")
                    elif terminal.v("terminal_event_id") != terminal_event_id:
                        p7.append("predecessor terminal_event_id mismatch")
                    elif terminal.v("terminal_state") != terminal_state:
                        p7.append("predecessor terminal_state mismatch")
                    elif not (terminal.ordinal < deciding_grant.ordinal):
                        p7.append("predecessor terminal event does not precede the grant")
    if p7:
        fail("fifo_predecessor", "; ".join(p7))
    else:
        mark_ok("fifo_predecessor")

    # -- predicate 8: attempt lineage ---------------------------------------
    # Real emission:
    #   * ``restore_host_alloc_retry_result`` is emitted ONLY on allocation
    #     failure (``unified_radix_cache.py:5460`` forfeited_alloc_failed and
    #     ``unified_radix_cache.py:6575-6598`` revoked_alloc_failed).  Every
    #     park is caused by the initial pre-wake failure, which always carries
    #     ``attempt_id=None``/``retry_grant=False``; at most one post-wake
    #     failure may emit a second with a non-empty host-alloc attempt id.
    #   * The non-forgeable lineage join is the producer-emitted
    #     ``wake_event_id``: the accepted finalize (host-alloc namespace
    #     ``f"{rid}:{seq}"``, ``unified_radix_cache.py:5717-5737``) and READY
    #     (prefetch namespace ``f"{rid}:prefetch:{seq}"``,
    #     ``scheduler.py:3130-3139,4399-4457``) must both name the SAME captured
    #     deciding grant.
    p8: list[str] = []
    pre_retries = [retry for retry in retries if not _is_post_wake_retry(retry)]
    post_retries = [retry for retry in retries if _is_post_wake_retry(retry)]
    if len(pre_retries) != 1:
        p8.append(
            "expected exactly one pre-wake retry_result with attempt_id=null, "
            f"found {len(pre_retries)}"
        )
    else:
        pre = pre_retries[0]
        if pre.v("retry_outcome") not in RECOGNIZED_RETRY_OUTCOMES:
            p8.append(
                f"unrecognized pre-wake retry_outcome: {pre.v('retry_outcome')!r}"
            )
        if _nonempty_str(pre.v("wake_event_id")):
            p8.append("pre-wake retry_result unexpectedly carries a wake_event_id")
        if deciding_grant is not None and pre.ordinal >= deciding_grant.ordinal:
            p8.append("pre-wake retry_result does not precede the deciding grant")
    if len(post_retries) > 1:
        p8.append(f"more than one post-wake retry_result, found {len(post_retries)}")
    elif post_retries:
        post = post_retries[0]
        if post.v("retry_outcome") not in RECOGNIZED_RETRY_OUTCOMES:
            p8.append(
                f"unrecognized post-wake retry_outcome: {post.v('retry_outcome')!r}"
            )
        if not _attempt_in_namespace(
            post.v("attempt_id"), target_rid, prefetch=False
        ):
            p8.append("post-wake retry attempt_id is not a target host-alloc attempt id")
        grant_ids = {grant.v("event_id") for grant in grants}
        if post.v("wake_event_id") not in grant_ids:
            p8.append("post-wake retry wake_event_id does not name a captured grant")
        elif not any(
            grant.v("event_id") == post.v("wake_event_id")
            and grant.ordinal < post.ordinal
            for grant in grants
        ):
            p8.append(
                "post-wake retry wake_event_id names a grant that does not precede it"
            )
        later_parks = [wait for wait in valid_waits if wait.ordinal > post.ordinal]
        if later_parks and not any(
            wait.v("attempt_id") == post.v("attempt_id") for wait in later_parks
        ):
            p8.append("post-wake retry attempt id not preserved into a later park")
    if deciding_grant is None:
        p8.append("no deciding grant captured from the accepted finalization")
    if len(accepted) != 1:
        p8.append("no single accepted finalization")
    else:
        finalize = accepted[0]
        if not _attempt_in_namespace(
            finalize.v("attempt_id"), target_rid, prefetch=False
        ):
            p8.append("finalize attempt_id is not a target host-alloc attempt id")
        if deciding_grant is not None and finalize.v(
            "wake_event_id"
        ) != deciding_grant.v("event_id"):
            p8.append("finalize wake_event_id does not name the deciding grant")
        if len(readies) != 1:
            p8.append("no single READY record for the target")
        else:
            ready = readies[0]
            if not _attempt_in_namespace(
                ready.v("attempt_id"), target_rid, prefetch=True
            ):
                p8.append("READY attempt_id is not a target prefetch attempt id")
            if deciding_grant is not None and ready.v(
                "wake_event_id"
            ) != deciding_grant.v("event_id"):
                p8.append("READY does not carry the deciding wake_event_id")
    if p8:
        fail("attempt_lineage", "; ".join(p8))
    else:
        mark_ok("attempt_lineage")

    # -- predicate 9: accepted finalization ---------------------------------
    if len(accepted) != 1:
        fail(
            "accepted_finalization",
            "expected exactly one accepted all-or-nothing finalization, "
            f"found {len(accepted)}",
        )
    else:
        mark_ok("accepted_finalization")

    # -- predicate 10: ready after finalize ---------------------------------
    p10: list[str] = []
    if len(readies) != 1:
        p10.append(f"expected exactly one READY record, found {len(readies)}")
    elif len(accepted) != 1:
        p10.append("no accepted finalization to order against")
    else:
        ready = readies[0]
        finalize = accepted[0]
        if ready.ordinal <= finalize.ordinal:
            p10.append("READY is not strictly after the accepted finalization")
        if ready.v("lifecycle_key") != target_lifecycle_key:
            p10.append("READY lifecycle_key does not match the target")
        if ready.v("finalize_result") != "accepted":
            p10.append("READY finalize_result is not accepted")
        if not _positive_int(ready.v("completed_kv_tokens")):
            p10.append("READY completed_kv_tokens is missing")
        elif ready.v("completed_kv_tokens") != finalize.v("kv_fetched"):
            p10.append("READY completed_kv_tokens != finalize kv_fetched")
        if ready.v("wake_event_id") != finalize.v("wake_event_id"):
            p10.append("READY wake_event_id != finalize wake_event_id")
        if not _nonempty_str(ready.v("attempt_id")):
            p10.append("READY attempt_id is missing")
        sidecars = finalize.v("sidecars")
        if isinstance(sidecars, dict) and sidecars:
            required = ready.v("required_aux_pools")
            if isinstance(required, list) and sorted(map(str, required)) != sorted(
                map(str, sidecars)
            ):
                p10.append("READY required_aux_pools != finalize sidecar pools")
            completed = ready.v("completed_aux_units")
            if isinstance(completed, dict):
                expected_units = {
                    str(pool): int(details.get("fetched"))
                    for pool, details in sidecars.items()
                    if isinstance(details, dict) and _is_int_val(details.get("fetched"))
                }
                if completed != expected_units:
                    p10.append("READY completed_aux_units mismatch")
    if p10:
        fail("ready_after_finalize", "; ".join(p10))
    else:
        mark_ok("ready_after_finalize")

    # -- predicate 11: negative safety --------------------------------------
    violations: list[str] = []
    if any(event.v("genuine_miss") is True for event in events):
        violations.append("genuine_miss")
    if any(event.v("crop_attempted") is True for event in events):
        violations.append("crop_attempted")
    if any(event.v("lower_checkpoint_queried") is True for event in events):
        violations.append("lower_checkpoint_queried")
    for retry in retries:
        if retry.v("genuine_miss") is not False:
            violations.append("retry_result genuine_miss is not false")
        if retry.v("crop_attempted") is not False:
            violations.append("retry_result crop_attempted is not false")
        if retry.v("lower_checkpoint_queried") is not False:
            violations.append("retry_result lower_checkpoint_queried is not false")
    for grant in grants:
        captured = grant.v("captured_generations") or {}
        current = grant.v("current_generations") or {}
        for pool in grant.v("blocked_domains") or []:
            if not (
                _is_int_val(captured.get(pool))
                and _is_int_val(current.get(pool))
                and current[pool] > captured[pool]
            ):
                violations.append(f"same-generation self-wake on pool {pool}")
    if len([retry for retry in retries if _is_post_wake_retry(retry)]) > 1:
        violations.append("repeated_retry")
    for grant in grants:
        if grant.v("predecessor_lineage_reason") is not None and _eligible_release_exists(
            grant, events
        ):
            violations.append("skipped_eligible_predecessor")
    for finalize in finals:
        sidecars = finalize.v("sidecars")
        if isinstance(sidecars, dict) and not _full_sidecars(finalize):
            violations.append("partial_sidecar")
        if finalize.v("result") == "discarded" or finalize.v("restore_state_after") == "NONE":
            violations.append("discarded_hybrid")
    for retry in retries:
        outcome = str(retry.v("retry_outcome") or "").lower()
        terminal = str(retry.v("terminal") or "").lower()
        if "recompute" in outcome or "recompute" in terminal or outcome == "miss":
            violations.append("recompute_fallback")
    if len(accepted) == 1:
        for ready in readies:
            if ready.ordinal < accepted[0].ordinal:
                violations.append("ready_before_finalize")
    elif readies:
        violations.append("ready_without_finalization")
    if violations:
        fail("negative_safety", "; ".join(dict.fromkeys(violations)))
    else:
        mark_ok("negative_safety")

    predicate_list = [predicates[name] for name in ORACLE_NAMES]
    reasons = [
        f"{item['name']}: {item['reason']}"
        for item in predicate_list
        if not item["passed"]
    ]
    status = STATUS_VERIFIED if all(item["passed"] for item in predicate_list) else STATUS_NOT_VERIFIED
    return {
        "status": status,
        "task_id": TASK_ID,
        "epoch": EPOCH,
        "predicates": predicate_list,
        "oracle": [item["name"] for item in predicate_list],
        "reasons": reasons,
        "raw_event_count": len(events),
        "raw_references": [event.source for event in events],
        "target": target,
    }


def _all_not_verified(result: dict[str, Any], gate_reasons: list[str]) -> dict[str, Any]:
    why = "; ".join(dict.fromkeys(reason for reason in gate_reasons if reason))
    for index, item in enumerate(result.get("predicates", [])):
        item["passed"] = False
        if index == 0:
            item["reason"] = f"raw_provenance_gate_failed: {why}" if why else "raw_provenance_gate_failed"
        elif not item.get("reason"):
            item["reason"] = "raw_provenance_gate_failed"
    result["status"] = STATUS_NOT_VERIFIED
    result["reasons"] = (
        ([f"raw_provenance_gate_failed: {why}"] if why else ["raw_provenance_gate_failed"])
        + list(result.get("reasons", []))
    )
    return result


def reduce_paths(event_paths: list[str], manifest_path: str) -> dict[str, Any]:
    manifest, gate_errors = verify_manifest(manifest_path, event_paths)
    events, parse_errors = parse_events(event_paths)
    gate_errors = list(gate_errors) + list(parse_errors)
    if not events and not gate_errors:
        gate_errors.append("no consumed product records")
    result = reduce_events(events, manifest)
    if gate_errors:
        result = _all_not_verified(result, gate_errors)
    return result


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", nargs="+", required=True, help="raw product log files")
    parser.add_argument("--manifest", required=True, help="raw-provenance manifest JSON")
    args = parser.parse_args(argv)
    result = reduce_paths(list(args.events), args.manifest)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == STATUS_VERIFIED else 1


if __name__ == "__main__":
    sys.exit(main())
