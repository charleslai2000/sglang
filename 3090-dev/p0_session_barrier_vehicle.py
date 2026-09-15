#!/usr/bin/env python3
"""Isolated P0 S=25 session/barrier vehicle.

The live path is deliberately small and fail-closed.  It uses the normal
OpenAI-compatible chat-completions endpoint and the existing
``gate3_parked.build_history_prompt`` builder, but it does not reuse the old
parked driver because that driver cannot gate a warm request on a per-session
V3 barrier.  The product is expected to emit top-level, exact identity fields
on p0_durable.v3 events.

This file is a vehicle, not a gate decision.  It never starts an engine and it
does not turn a timeout, a sleep, or a client-side label into PASS.
"""

from __future__ import annotations

import argparse
import csv
import concurrent.futures
import hashlib
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Iterable


SCHEMA = "p0_durable.v3"
REQUIRED_IDENTITY = ("session_id", "build_rid", "node_id", "final_kv_hash")
BRANCHES = (
    "A_omitted_transfer",
    "B_write_failure",
    "C_key_mismatch",
    "D_recycle_or_remove",
    "E_late_write_or_barrier",
    "F_unresolved",
)
FROZEN = {
    "sessions": 25,
    "history_target": 55000,
    "active": 8,
    "build_workers": 8,
    "rh": "off",
    "mamba_ratio": 0.42,
    "hicache_ratio": 1.3,
    "kv_dtype": "fp8_e4m3",
    "cuda_graph_max_batch": 8,
    "file_size": "120G",
    "restore_threshold_tokens": 256,
}
CHURN_COUNT = FROZEN["active"] + 1

# V3 must use explicit evidence.  ``storage_persisted`` is accepted only when
# it also carries kv_durable=true; an ACK alone is not treated as durability.
KV_EVIDENCE_EVENTS = {"kv_durable", "storage_persisted"}
MAMBA_EVIDENCE_EVENTS = {"mamba_durable", "mamba_persisted"}
SCOPED_EVENT_NAMES = {
    "build_complete",
    "backup_submit",
    "batch_set_result",
    "backup_ack_enqueue",
    "backup_ack_drain",
    "storage_persisted",
    "kv_durable",
    "mamba_persisted",
    "mamba_durable",
    "durability_barrier",
    "residency_barrier",
    "storage_query",
    "warm_lookup_start",
    "warm_request",
    "restore_outcome",
    "restore_complete",
    "storage_invalidate",
    "storage_remove",
    "extent_recycle",
}


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value: Any) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _wall_ns() -> int:
    return time.time_ns()


def _identity(event: dict[str, Any]) -> tuple[Any, ...]:
    return tuple(event.get(field) for field in REQUIRED_IDENTITY)


def _has_identity(event: dict[str, Any]) -> bool:
    return all(isinstance(event.get(field), str) and event[field] for field in REQUIRED_IDENTITY)


def _event_is_true(event: dict[str, Any], field: str) -> bool:
    return event.get(field) is True


def _is_kv_evidence(event: dict[str, Any]) -> bool:
    name = event.get("evt")
    if name not in KV_EVIDENCE_EVENTS:
        return False
    return _event_is_true(event, "kv_durable")


def _is_mamba_evidence(event: dict[str, Any]) -> bool:
    name = event.get("evt")
    if name not in MAMBA_EVIDENCE_EVENTS:
        return False
    return _event_is_true(event, "mamba_durable")


def _is_restore_success(event: dict[str, Any]) -> bool:
    return (
        event.get("evt") in {"restore_outcome", "restore_complete"}
        and event.get("restore_success") is True
        and event.get("full_restore") is True
    )


def _classify(state: dict[str, Any]) -> str:
    if state["lookup_before_barrier"]:
        return "E_late_write_or_barrier"
    if state["write_failure"]:
        return "B_write_failure"
    if state["omitted_transfer"]:
        return "A_omitted_transfer"
    if state["key_mismatch"]:
        return "C_key_mismatch"
    if state["recycled"]:
        return "D_recycle_or_remove"
    return "F_unresolved"


class Reducer:
    """Exact tuple reducer; event arrival order is the causal order.

    A monotonic local sequence is assigned as lines are observed.  Event wall
    timestamps are retained for evidence but are never used to establish
    happens-before.  Any session-scoped event without the complete identity is
    an invalid join for that session.
    """

    def __init__(self, run_id: str):
        self.run_id = run_id
        self.events: list[dict[str, Any]] = []
        self.states: dict[str, dict[str, Any]] = {}
        self.errors: list[str] = []
        self._seq = 0
        self.lock = threading.RLock()

    def _state(self, session_id: str) -> dict[str, Any]:
        return self.states.setdefault(
            session_id,
            {
                "session_id": session_id,
                "identities": set(),
                "build_rid": None,
                "node_id": None,
                "final_kv_hash": None,
                "identity_established": False,
                "build_event_seen": False,
                "build_order": None,
                "eligible": False,
                "short_suffix": False,
                "kv_durable": False,
                "kv_order": None,
                "mamba_durable": False,
                "mamba_order": None,
                "durable": False,
                "cold": False,
                "warm_issued": False,
                "warm_rid": None,
                "restore_success": False,
                "restore_metrics": {},
                "lookup_before_barrier": False,
                "write_failure": False,
                "omitted_transfer": False,
                "key_mismatch": False,
                "recycled": False,
                "invalid_join": False,
                "barrier_error": None,
                "lookup_order": None,
                "durable_order": None,
                "cold_order": None,
                "warm_order": None,
                "product_warm_order": None,
                "restore_order": None,
                "event_refs": [],
            },
        )

    def establish_build(self, session_id: str, build_rid: str, history_tokens: int, short: bool) -> None:
        with self.lock:
            state = self._state(session_id)
            state["build_rid"] = build_rid
            if any(identity[1] != build_rid for identity in state["identities"]):
                state["invalid_join"] = True
                self.errors.append(f"session_id={session_id}: pre-response build_rid mismatch")
            state["eligible"] = bool(history_tokens >= FROZEN["history_target"] * 0.9)
            state["short_suffix"] = bool(short)

    def ingest(self, event: dict[str, Any], source: str = "trace") -> None:
        with self.lock:
            self._seq += 1
            item = dict(event)
            item["_vehicle_order"] = self._seq
            self.events.append(item)

            if item.get("schema_version") != SCHEMA:
                self.errors.append(f"event {_json(item)[:180]}: schema mismatch")
                return
            if item.get("run_id") != self.run_id:
                self.errors.append(f"event_id={item.get('event_id')}: run_id mismatch")
                return
            session_id = item.get("session_id")
            if not isinstance(session_id, str) or not session_id:
                if item.get("evt") in SCOPED_EVENT_NAMES or any(field in item for field in REQUIRED_IDENTITY[1:]):
                    self.errors.append(
                        f"event_id={item.get('event_id')}: scoped event missing session_id"
                    )
                # Unscoped control events do not participate in an eligible join.
                return
            state = self._state(session_id)
            state["event_refs"].append(item.get("event_id") or f"line:{self._seq}")
            if not _has_identity(item):
                state["invalid_join"] = True
                self.errors.append(
                    f"event_id={item.get('event_id')}: missing exact identity fields "
                    f"{','.join(REQUIRED_IDENTITY)}"
                )
                return

            identity = _identity(item)
            state["identities"].add(identity)
            if state["build_rid"] is not None and item["build_rid"] != state["build_rid"]:
                state["invalid_join"] = True
                self.errors.append(f"session_id={session_id}: build_rid mismatch")
                return
            if any(
                existing != identity
                and existing[1] == identity[1]
                and existing[2:] != identity[2:]
                for existing in state["identities"]
            ):
                state["invalid_join"] = True
                self.errors.append(
                    f"session_id={session_id}: conflicting node_id/final_kv_hash identity"
                )
                return
            state["node_id"] = item["node_id"]
            state["final_kv_hash"] = item["final_kv_hash"]
            name = item.get("evt")
            order = item["_vehicle_order"]

            if name == "build_complete":
                state["build_event_seen"] = True
                state["identity_established"] = True
                state["build_order"] = state["build_order"] or order
            if _is_kv_evidence(item):
                state["kv_durable"] = True
                state["kv_order"] = state["kv_order"] or order
            if _is_mamba_evidence(item):
                state["mamba_durable"] = True
                state["mamba_order"] = state["mamba_order"] or order
            if name == "durability_barrier" and item.get("combined_durable") is True:
                ordered_evidence = bool(
                    state["identity_established"]
                    and state["build_order"] is not None
                    and state["kv_order"] is not None
                    and state["mamba_order"] is not None
                    and state["build_order"] < state["kv_order"] < order
                    and state["build_order"] < state["mamba_order"] < order
                )
                if not ordered_evidence:
                    state["barrier_error"] = "durability barrier preceded ordered exact KV/Mamba evidence"
                else:
                    state["durable"] = True
                    state["durable_order"] = order
            if name == "residency_barrier" and item.get("cold_residency") is True:
                if not state["durable"]:
                    state["barrier_error"] = "residency barrier preceded durability barrier"
                else:
                    state["cold"] = True
                    state["cold_order"] = order
            if name in {"warm_lookup_start", "warm_request"}:
                state["warm_issued"] = True
                state["warm_rid"] = item.get("warm_rid") or state["warm_rid"]
                if source == "vehicle":
                    # The client marker is only a fallback.  A product lookup
                    # observed before or after it owns the causal order.
                    if state["product_warm_order"] is None and state["warm_order"] is None:
                        state["warm_order"] = order
                        state["lookup_order"] = order
                else:
                    state["product_warm_order"] = state["product_warm_order"] or order
                    state["warm_order"] = state["product_warm_order"]
                    state["lookup_order"] = state["product_warm_order"]
                if not (state["durable"] and state["cold"]):
                    state["lookup_before_barrier"] = True
            if _is_restore_success(item):
                if not state["warm_issued"]:
                    state["invalid_join"] = True
                state["restore_success"] = True
                state["restore_order"] = order
                state["restore_metrics"] = {
                    key: item.get(key)
                    for key in ("restore_ms", "lookup_ms", "kv_pages", "mamba_pages", "final_pages")
                    if key in item
                }
            if name in {"batch_set_result", "backup_ack_enqueue", "backup_ack_drain"} and item.get("result") is False:
                state["write_failure"] = True
            if name == "backup_submit" and item.get("mamba_key") is None:
                state["omitted_transfer"] = True
            if name == "storage_query" and item.get("tested_present") is False:
                state["key_mismatch"] = True
            if name in {"storage_invalidate", "storage_remove", "extent_recycle"}:
                state["recycled"] = True

    def record_build_complete(self, session_id: str, build_rid: str, node_id: str, final_kv_hash: str) -> None:
        self.ingest(
            {
                "schema_version": SCHEMA,
                "run_id": self.run_id,
                "event_id": f"vehicle-build:{session_id}",
                "evt": "build_complete",
                "session_id": session_id,
                "build_rid": build_rid,
                "node_id": node_id,
                "final_kv_hash": final_kv_hash,
            },
            source="vehicle",
        )

    def record_warm_request(self, session_id: str, warm_rid: str | None) -> None:
        with self.lock:
            state = self._state(session_id)
            if not (state["durable"] and state["cold"]):
                state["lookup_before_barrier"] = True
                state["invalid_join"] = True
                return
            identity = {
                "schema_version": SCHEMA,
                "run_id": self.run_id,
                "event_id": f"vehicle-warm:{session_id}:{self._seq + 1}",
                "evt": "warm_request",
                "session_id": session_id,
                "build_rid": state["build_rid"],
                "node_id": state["node_id"],
                "final_kv_hash": state["final_kv_hash"],
                "warm_rid": warm_rid,
            }
        self.ingest(identity, source="vehicle")

    def ready_for_warm(self, session_id: str) -> bool:
        with self.lock:
            state = self._state(session_id)
            return bool(
                state["identity_established"]
                and state["kv_durable"]
                and state["mamba_durable"]
                and state["durable"]
                and state["cold"]
                and len(state["identities"]) == 1
                and not state["lookup_before_barrier"]
                and not state["invalid_join"]
                and state["barrier_error"] is None
                and not self.errors
            )

    def warm_rejection_reason(self, session_id: str) -> str | None:
        with self.lock:
            if self._state(session_id)["lookup_before_barrier"]:
                return "lookup_before_barrier"
            return None

    def restore_ready(self, session_id: str) -> bool:
        with self.lock:
            state = self._state(session_id)
            return bool(
                state["warm_issued"]
                and state["restore_success"]
                and state["restore_order"] is not None
                and state["warm_order"] is not None
                and state["warm_order"] < state["restore_order"]
                and not state["invalid_join"]
            )

    def row(self, session_id: str, build_row: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            state = self._state(session_id)
            ordered = bool(
                state["build_order"] is not None
                and state["kv_order"] is not None
                and state["mamba_order"] is not None
                and state["durable_order"] is not None
                and state["cold_order"] is not None
                and state["warm_order"] is not None
                and state["build_order"] < state["kv_order"] < state["durable_order"]
                and state["build_order"] < state["mamba_order"] < state["durable_order"]
                and state["durable_order"] < state["cold_order"] < state["warm_order"]
            )
            result = dict(state)
            result.pop("identities", None)
            result["identity_count"] = len(state["identities"])
            result["exact_identity"] = bool(
                state["build_rid"]
                and state["node_id"]
                and state["final_kv_hash"]
                and len(state["identities"]) == 1
                and state["build_rid"] == build_row.get("build_rid")
            )
            result["barrier_ordered"] = ordered
            result["build_http"] = build_row.get("http")
            result["build_finished"] = build_row.get("finished")
            result["build_rid_source"] = build_row.get("build_rid_source")
            result["warm_http"] = build_row.get("warm_http")
            result["warm_finished"] = build_row.get("warm_finished")
            result["warm_metrics"] = build_row.get("warm_metrics", {})
            result["branch"] = _classify(result)
            result["evidence_ref"] = _digest(state["event_refs"])
            return result


class EventTailer:
    def __init__(self, path: Path, reducer: Reducer):
        self.path = path
        self.reducer = reducer
        self.condition = threading.Condition()
        self.stop_event = threading.Event()
        self.error: str | None = None
        self.thread = threading.Thread(target=self._run, name="p0-v3-tailer", daemon=True)

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        with self.condition:
            self.condition.notify_all()
        self.thread.join(timeout=2.0)

    def _publish_error_locked(self, message: str) -> None:
        if self.error is None:
            self.error = message
        self.condition.notify_all()

    def _publish_error(self, message: str) -> None:
        with self.condition:
            self._publish_error_locked(message)

    def _run(self) -> None:
        try:
            with self.path.open("r", encoding="utf-8") as handle:
                pending = ""
                while not self.stop_event.is_set():
                    line = handle.readline()
                    if not line:
                        with self.condition:
                            self.condition.wait(timeout=0.25)
                        continue
                    pending += line
                    if not pending.endswith("\n"):
                        continue
                    line, pending = pending, ""
                    if not line.strip():
                        continue
                    with self.condition:
                        try:
                            event = json.loads(line)
                        except json.JSONDecodeError as exc:
                            self._publish_error_locked(f"invalid JSONL: {exc}")
                            continue
                        if not isinstance(event, dict):
                            self._publish_error_locked("JSONL event is not an object")
                            continue
                    self.reducer.ingest(event)
                    with self.condition:
                        self.condition.notify_all()
        except OSError as exc:
            self._publish_error(str(exc))

    def wait_for(self, predicate: Any, timeout_s: float) -> bool:
        deadline = time.monotonic() + timeout_s
        while True:
            with self.condition:
                if self.error:
                    return False
            predicate_result = predicate()
            with self.condition:
                if self.error:
                    return False
                if predicate_result:
                    return True
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                self.condition.wait(timeout=min(0.25, remaining))


def _endpoint_url(endpoint: str) -> str:
    value = endpoint.rstrip("/")
    if value.endswith("/chat/completions"):
        return value
    if value.endswith("/v1"):
        return value + "/chat/completions"
    return value + "/v1/chat/completions"


def _parse_stream(body: bytes) -> tuple[str | None, str, dict[str, Any], str | None, bool]:
    request_id = None
    text_parts: list[str] = []
    usage: dict[str, Any] = {}
    finish_reason = None
    stream_done = False
    for raw_line in body.decode("utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if data == "[DONE]":
            stream_done = True
            continue
        try:
            chunk = json.loads(data)
        except json.JSONDecodeError:
            continue
        request_id = request_id or chunk.get("id")
        if isinstance(chunk.get("usage"), dict):
            usage = chunk["usage"]
        for choice in chunk.get("choices") or []:
            if isinstance(choice, dict):
                delta = choice.get("delta") or {}
                if isinstance(delta, dict) and isinstance(delta.get("content"), str):
                    text_parts.append(delta["content"])
                finish_reason = choice.get("finish_reason") or finish_reason
    return request_id, "".join(text_parts), usage, finish_reason, stream_done


def post_chat(endpoint: str, payload: dict[str, Any], timeout_s: float, api_key: str | None) -> dict[str, Any]:
    started = time.monotonic()
    request = urllib.request.Request(
        _endpoint_url(endpoint),
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            **({"Authorization": f"Bearer {api_key}"} if api_key else {}),
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as response:
            body = response.read()
            status = response.status
    except urllib.error.HTTPError as exc:
        body = exc.read()
        status = exc.code
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return {
            "http": None,
            "finished": False,
            "rid": None,
            "rid_source": None,
            "error": str(exc),
            "wall_s": round(time.monotonic() - started, 6),
            "usage": {},
            "output_sha16": None,
        }

    request_id = None
    output = ""
    usage: dict[str, Any] = {}
    finish_reason = None
    stream_done = False
    try:
        decoded = json.loads(body)
        request_id = decoded.get("id")
        usage = decoded.get("usage") or {}
        choices = decoded.get("choices") or []
        if choices:
            message = choices[0].get("message") or {}
            output = message.get("content") or ""
            finish_reason = choices[0].get("finish_reason")
    except (json.JSONDecodeError, AttributeError):
        request_id, output, usage, finish_reason, stream_done = _parse_stream(body)
    return {
        "http": status,
        "finished": bool(status == 200 and (finish_reason is not None or stream_done)),
        "rid": request_id if isinstance(request_id, str) and request_id else None,
        "rid_source": "response.id" if request_id else None,
        "finish_reason": finish_reason,
        "stream_done": stream_done,
        "usage": usage,
        "output_sha16": hashlib.sha256(output.encode("utf-8")).hexdigest()[:16] if output else None,
        "wall_s": round(time.monotonic() - started, 6),
        "error": None if status == 200 else body.decode("utf-8", errors="replace")[:500],
    }


def _load_builder(model_path: str):
    here = Path(__file__).resolve().parent
    if str(here) not in sys.path:
        sys.path.insert(0, str(here))
    try:
        import gate3_parked
        from transformers import AutoTokenizer
    except Exception as exc:  # pragma: no cover - environment dependent
        raise RuntimeError(f"existing build_history_prompt/tokenizer path unavailable: {exc}") from exc
    tokenizer = AutoTokenizer.from_pretrained(model_path)
    return lambda seed: gate3_parked.build_history_prompt(FROZEN["history_target"], tokenizer, seed)


def _fixture(run_id: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for index in range(FROZEN["sessions"]):
        sid = f"p0-s25-s{index:05d}"
        build_rid = f"fixture-build-{index:05d}"
        node = f"fixture-node-{index:05d}"
        kv_hash = hashlib.sha256(f"fixture-kv-{index}".encode()).hexdigest()
        common = {
            "schema_version": SCHEMA,
            "run_id": run_id,
            "session_id": sid,
            "build_rid": build_rid,
            "node_id": node,
            "final_kv_hash": kv_hash,
        }
        for name, fields in (
            ("build_complete", {}),
            ("kv_durable", {"kv_durable": True}),
            ("mamba_durable", {"mamba_durable": True}),
            ("durability_barrier", {"combined_durable": True}),
            ("residency_barrier", {"cold_residency": True}),
            ("warm_request", {"warm_rid": f"fixture-warm-{index:05d}"}),
            ("restore_outcome", {"restore_success": True, "full_restore": True, "final_pages": 1}),
        ):
            event = dict(common)
            event.update({"evt": name, "event_id": f"fixture:{index}:{name}"})
            event.update(fields)
            events.append(event)
    return events


def _read_events(path: Path, run_id: str) -> list[dict[str, Any]]:
    events = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"line {line_number}: invalid JSONL: {exc}") from exc
            if not isinstance(event, dict):
                raise ValueError(f"line {line_number}: event is not an object")
            events.append(event)
    return events


def _build_rows_from_dry_run(events: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for event in events:
        if event.get("evt") != "build_complete" or not event.get("session_id"):
            continue
        rows[event["session_id"]] = {
            "session_id": event["session_id"],
            "build_rid": event.get("build_rid"),
            "history_tokens": FROZEN["history_target"],
            "short_suffix": False,
            "http": 200,
            "finished": True,
            "rid_source": "dry-run-trace",
        }
    return rows


def _validate_frozen(args: argparse.Namespace) -> None:
    values = {
        "sessions": args.sessions,
        "active": args.active,
        "build_workers": args.build_workers,
        "history_target": args.history_target,
        "rh": args.rh,
    }
    for name, expected in (("sessions", 25), ("active", 8), ("build_workers", 8), ("history_target", 55000), ("rh", "off")):
        if values[name] != expected:
            raise SystemExit(f"frozen P0 config mismatch: {name}={values[name]!r}, expected {expected!r}")


def _write_bundle(
    evidence_dir: Path,
    args: argparse.Namespace,
    reducer: Reducer,
    build_rows: dict[str, dict[str, Any]],
    barrier_waits: list[dict[str, Any]],
    execution_started: bool,
    fatal_errors: list[str],
    dry_run: bool,
    churn_evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    evidence_dir.mkdir(parents=True, exist_ok=True)
    churn_evidence = churn_evidence or {
        "phase": "not-run",
        "expected_count": CHURN_COUNT,
        "count": 0,
        "session_ids": [],
        "rows": [],
        "failures": [],
    }
    rows = {sid: reducer.row(sid, row) for sid, row in build_rows.items()}
    planned = set(build_rows)
    eligible = [row for row in rows.values() if row["eligible"] and not row["short_suffix"]]
    churn_ids = set(churn_evidence.get("session_ids", []))
    churn_scope_error = sorted(planned & churn_ids)
    churn_ok = bool(
        churn_evidence.get("phase") == "complete"
        and churn_evidence.get("count") == CHURN_COUNT
        and len(churn_ids) == CHURN_COUNT
        and not churn_evidence.get("failures")
        and not churn_scope_error
    )
    all_good = bool(
        len(planned) == args.sessions
        and len(eligible) == args.sessions
        and churn_ok
        and not fatal_errors
        and not reducer.errors
        and all(
            row["exact_identity"]
            and row["barrier_ordered"]
            and row["restore_success"]
            and row["warm_issued"]
            and row["build_http"] == 200
            and row["build_finished"] is True
            and isinstance(row.get("build_rid"), str)
            and row["build_rid"]
            and row["build_rid_source"] == "response.id"
            and row["warm_http"] == 200
            and row["warm_finished"] is True
            and isinstance(row["warm_rid"], str)
            and row["warm_rid"]
            and row["warm_metrics"].get("rid_source") == "response.id"
            and not row["invalid_join"]
            for row in eligible
        )
    )
    if dry_run:
        verdict = "NOT_VERIFIED"
    elif all_good:
        verdict = "PASS"
    elif any(row.get("warm_http") not in (None, 200) for row in rows.values()):
        verdict = "FAIL"
    else:
        verdict = "NOT_VERIFIED"

    manifest = {
        "task_id": args.task_id,
        "epoch": args.epoch,
        "run_id": args.run_id,
        "trace_schema": SCHEMA,
        "vehicle": "p0_session_barrier_vehicle",
        "vehicle_readiness": "parser_reducer_only" if dry_run else "live-capable",
        "execution_started": execution_started,
        "remote_process_started": False,
        "endpoint": args.endpoint if not dry_run else None,
        "events": str(args.events) if args.events else None,
        "config": {**FROZEN, "model": args.model, "model_path": args.model_path},
        "identity_join": list(REQUIRED_IDENTITY),
        "causal_order": "vehicle arrival sequence; wall timestamps are evidence only",
        "warm_gate": ["build_identity", "kv_durable", "mamba_durable", "durability_barrier.combined_durable", "residency_barrier.cold_residency"],
        "client_api": "OpenAI-compatible POST /v1/chat/completions; top-level session_id",
        "auxiliary_churn": {
            "count": CHURN_COUNT,
            "session_prefix": "p0-s25-churn-",
            "excluded_from_planned_eligible": True,
        },
    }
    (evidence_dir / "config-resolved.json").write_text(_json(manifest) + "\n", encoding="utf-8")
    with (evidence_dir / "trace-copy.jsonl").open("w", encoding="utf-8") as handle:
        for event in reducer.events:
            handle.write(_json(event) + "\n")
    with (evidence_dir / "build-warm.jsonl").open("w", encoding="utf-8") as handle:
        for sid in sorted(rows):
            handle.write(_json({"session_id": sid, **build_rows.get(sid, {}), "reduced": rows[sid]}) + "\n")
    with (evidence_dir / "barrier-waits.jsonl").open("w", encoding="utf-8") as handle:
        for wait in barrier_waits:
            handle.write(_json(wait) + "\n")
    with (evidence_dir / "churn-builds.jsonl").open("w", encoding="utf-8") as handle:
        for row in churn_evidence.get("rows", []):
            handle.write(_json(row) + "\n")
    reducer_result = {
        "schema": SCHEMA,
        "required_identity": list(REQUIRED_IDENTITY),
        "errors": reducer.errors,
        "rows": rows,
        "missing_sessions": sorted(set(f"p0-s25-s{i:05d}" for i in range(args.sessions)) - set(rows)),
    }
    (evidence_dir / "reducer-result.json").write_text(_json(reducer_result) + "\n", encoding="utf-8")
    verdict_result = {
        "verdict": verdict,
        "vehicle_readiness": manifest["vehicle_readiness"],
        "execution_started": execution_started,
        "eligible_full_sessions": len(eligible),
        "planned_sessions": args.sessions,
        "planned_row_count": len(planned),
        "churn_expected_count": CHURN_COUNT,
        "churn_count": churn_evidence.get("count", 0),
        "churn_session_ids": sorted(churn_ids),
        "churn_failures": churn_evidence.get("failures", []),
        "churn_scope_error": churn_scope_error,
        "barrier_waits": len(barrier_waits),
        "restore_success": sum(bool(row["restore_success"]) for row in eligible),
        "missing_event_join": bool(reducer.errors or fatal_errors),
        "branches": {branch: sum(row["branch"] == branch for row in rows.values()) for branch in BRANCHES},
        "fail_closed": True,
        "no_fixed_sleep_success": True,
        "errors": fatal_errors,
    }
    (evidence_dir / "verdict.json").write_text(_json(verdict_result) + "\n", encoding="utf-8")
    (evidence_dir / "vehicle.log").write_text(
        "No engine or remote process is started by this vehicle.\n"
        "Warm requests are issued only after exact keyed barriers observed by the tailer.\n",
        encoding="utf-8",
    )
    files = sorted(path for path in evidence_dir.iterdir() if path.name != "MD5SUMS" and path.is_file())
    (evidence_dir / "MD5SUMS").write_text(
        "".join(f"{hashlib.md5(path.read_bytes()).hexdigest()}  {path.name}\n" for path in files),
        encoding="utf-8",
    )
    return verdict_result


def _run_build_phase(
    args: argparse.Namespace,
    build_prompt: Any,
    reducer: Reducer,
    build_rows: dict[str, dict[str, Any]],
    fatal_errors: list[str],
    lock: threading.Lock,
) -> dict[str, dict[str, Any]]:
    """Submit every build independently of the later durability gate."""

    def build_session(index: int) -> dict[str, Any] | None:
        session_id = f"p0-s25-s{index:05d}"
        build_row: dict[str, Any] = {
            "session_id": session_id,
            "build_rid": None,
            "build_rid_source": None,
            "history_tokens": 0,
            "short_suffix": False,
            "http": None,
            "finished": False,
            "build_metrics": {},
        }
        try:
            history, history_tokens = build_prompt(index)
            build_payload = {
                "model": args.model,
                "messages": [{"role": "user", "content": history}],
                "max_tokens": 12,
                "temperature": 0.0,
                "stream": True,
                "session_id": session_id,
            }
            build_metrics = post_chat(args.endpoint, build_payload, args.build_timeout_s, args.api_key)
            build_rid = build_metrics.get("rid")
            build_row.update(
                {
                    "build_rid": build_rid,
                    "build_rid_source": build_metrics.get("rid_source"),
                    "history_tokens": history_tokens,
                    "build_metrics": build_metrics,
                    "http": build_metrics.get("http"),
                    "finished": build_metrics.get("finished"),
                }
            )
            if (
                build_metrics.get("http") != 200
                or build_metrics.get("finished") is not True
                or not isinstance(build_rid, str)
                or not build_rid
                or build_metrics.get("rid_source") != "response.id"
            ):
                raise RuntimeError(
                    "build response failed HTTP/finished/response.id admission"
                )
            reducer.establish_build(session_id, build_rid, history_tokens, False)
            return {
                "session_id": session_id,
                "history": history,
                "history_tokens": history_tokens,
                "build_rid": build_rid,
            }
        except Exception as exc:  # noqa: BLE001
            with lock:
                fatal_errors.append(f"{session_id}: {type(exc).__name__}: {exc}")
            return None
        finally:
            with lock:
                build_rows[session_id] = build_row

    with concurrent.futures.ThreadPoolExecutor(
        max_workers=args.build_workers, thread_name_prefix="p0-build"
    ) as pool:
        contexts = list(pool.map(build_session, range(args.sessions)))
    return {
        context["session_id"]: context
        for context in contexts
        if context is not None
    }


def _run_churn_phase(
    args: argparse.Namespace,
    build_prompt: Any,
    build_contexts: dict[str, dict[str, Any]],
    reducer: Reducer,
    fatal_errors: list[str],
    lock: threading.Lock,
) -> dict[str, Any]:
    """Submit bounded auxiliary builds to create post-build eviction pressure.

    Churn sessions are intentionally kept out of ``build_rows`` and therefore
    out of planned, eligible, warm, and final PASS accounting.  They still
    receive an exact reducer build identity so any product trace for the
    request can join without becoming an unkeyed session error.
    """

    target_history_hashes = {
        hashlib.sha256(context["history"].encode("utf-8")).hexdigest()
        for context in build_contexts.values()
        if isinstance(context.get("history"), str)
    }
    rows: list[dict[str, Any]] = []
    failures: list[str] = []
    row_lock = threading.Lock()

    def churn_session(index: int) -> dict[str, Any]:
        session_id = f"p0-s25-churn-{index:05d}"
        builder_seed = args.sessions + index
        row: dict[str, Any] = {
            "session_id": session_id,
            "builder_seed": builder_seed,
            "build_rid": None,
            "build_rid_source": None,
            "history_tokens": 0,
            "history_sha256": None,
            "http": None,
            "finished": False,
            "build_metrics": {},
            "failure": None,
        }
        try:
            history, history_tokens = build_prompt(builder_seed)
            history_hash = hashlib.sha256(history.encode("utf-8")).hexdigest()
            row.update(
                {
                    "history_tokens": history_tokens,
                    "history_sha256": history_hash,
                }
            )
            if history_hash in target_history_hashes:
                raise RuntimeError("churn history duplicates a target build history")
            build_payload = {
                "model": args.model,
                "messages": [{"role": "user", "content": history}],
                "max_tokens": 12,
                "temperature": 0.0,
                "stream": True,
                "session_id": session_id,
            }
            build_metrics = post_chat(
                args.endpoint, build_payload, args.build_timeout_s, args.api_key
            )
            build_rid = build_metrics.get("rid")
            row.update(
                {
                    "build_rid": build_rid,
                    "build_rid_source": build_metrics.get("rid_source"),
                    "build_metrics": build_metrics,
                    "http": build_metrics.get("http"),
                    "finished": build_metrics.get("finished"),
                }
            )
            if (
                build_metrics.get("http") != 200
                or build_metrics.get("finished") is not True
                or not isinstance(build_rid, str)
                or not build_rid
                or build_metrics.get("rid_source") != "response.id"
            ):
                raise RuntimeError(
                    "churn response failed HTTP/finished/response.id admission"
                )
            reducer.establish_build(session_id, build_rid, history_tokens, False)
        except Exception as exc:  # noqa: BLE001
            row["failure"] = f"{type(exc).__name__}: {exc}"
            with lock:
                message = f"{session_id}: {row['failure']}"
                fatal_errors.append(message)
            with row_lock:
                failures.append(f"{session_id}: {row['failure']}")
        return row

    with concurrent.futures.ThreadPoolExecutor(
        max_workers=args.build_workers, thread_name_prefix="p0-churn"
    ) as pool:
        rows = list(pool.map(churn_session, range(CHURN_COUNT)))

    session_ids = [row["session_id"] for row in rows]
    if len(set(row["history_sha256"] for row in rows if row["history_sha256"])) != len(
        [row for row in rows if row["history_sha256"]]
    ):
        message = "churn phase produced duplicate auxiliary histories"
        with lock:
            fatal_errors.append(message)
        failures.append(message)
    return {
        "phase": "complete",
        "expected_count": CHURN_COUNT,
        "count": len(rows),
        "session_ids": session_ids,
        "rows": rows,
        "failures": failures,
    }


def _run_warm_scheduler(
    args: argparse.Namespace,
    reducer: Reducer,
    tailer: EventTailer,
    build_rows: dict[str, dict[str, Any]],
    build_contexts: dict[str, dict[str, Any]],
    fatal_errors: list[str],
    lock: threading.Lock,
) -> list[dict[str, Any]]:
    """Gate warm requests without occupying build workers on durability waits."""

    planned = [f"p0-s25-s{index:05d}" for index in range(args.sessions)]
    barrier_pending = set(planned)
    ready_to_warm: dict[str, dict[str, Any]] = {}
    barrier_waits: dict[str, dict[str, Any]] = {}
    warm_futures: dict[concurrent.futures.Future[Any], str] = {}
    deadline = time.monotonic() + args.watchdog_s

    def add_fatal(message: str) -> None:
        with lock:
            fatal_errors.append(message)

    def record_barrier_wait(session_id: str, ready: bool, reason: str | None = None) -> None:
        if session_id in barrier_waits:
            return
        build_row = build_rows.get(session_id, {"session_id": session_id})
        wait_row = {
            "session_id": session_id,
            "build_rid": build_row.get("build_rid"),
            "ready": ready,
            "reason": reason,
            "tailer_error": tailer.error,
            "observed_order": reducer.row(session_id, build_row),
        }
        barrier_waits[session_id] = wait_row

    def warm_session(context: dict[str, Any]) -> None:
        session_id = context["session_id"]
        build_row = build_rows[session_id]
        try:
            # Recheck immediately before the HTTP request so a tailer error or
            # invalidated exact join cannot turn a stale readiness observation
            # into a warm request.
            if tailer.error:
                add_fatal(f"{session_id}: tailer error before warm: {tailer.error}")
                return
            if not reducer.ready_for_warm(session_id):
                add_fatal(f"{session_id}: readiness lost before warm submission")
                return
            warm_payload = {
                "model": args.model,
                "messages": [
                    {"role": "user", "content": context["history"]},
                    {"role": "assistant", "content": ""},
                    {"role": "user", "content": "现在请用一句话总结刚才这段资料的核心观点，不要展开。"},
                ],
                "max_tokens": 64,
                "temperature": 0.0,
                "stream": True,
                "session_id": session_id,
            }
            remaining = max(0.001, deadline - time.monotonic())
            warm_metrics = post_chat(
                args.endpoint,
                warm_payload,
                min(args.warm_timeout_s, remaining),
                args.api_key,
            )
            with lock:
                build_row["warm_rid"] = warm_metrics.get("rid")
                build_row["warm_metrics"] = warm_metrics
                build_row["warm_http"] = warm_metrics.get("http")
                build_row["warm_finished"] = warm_metrics.get("finished")
            warm_rid = warm_metrics.get("rid")
            if (
                warm_metrics.get("http") != 200
                or warm_metrics.get("finished") is not True
                or not isinstance(warm_rid, str)
                or not warm_rid
                or warm_metrics.get("rid_source") != "response.id"
            ):
                add_fatal(
                    f"{session_id}: warm response failed HTTP/finished/response.id admission"
                )
                return
            reducer.record_warm_request(session_id, warm_metrics.get("rid"))
            restore_remaining = max(0.001, deadline - time.monotonic())
            restore_ready = tailer.wait_for(
                lambda: reducer.restore_ready(session_id), restore_remaining
            )
            with lock:
                build_row["restore_checked"] = True
                build_row["restore_ready"] = restore_ready
            if not restore_ready:
                reason = tailer.error or "restore watchdog timeout"
                add_fatal(f"{session_id}: restore check failed: {reason}")
        except Exception as exc:  # noqa: BLE001
            with lock:
                build_row["restore_checked"] = True
                build_row["restore_ready"] = False
            add_fatal(f"{session_id}: {type(exc).__name__}: {exc}")

    pool = concurrent.futures.ThreadPoolExecutor(
        max_workers=args.build_workers, thread_name_prefix="p0-warm"
    )
    try:
        while barrier_pending or ready_to_warm or warm_futures:
            for future in list(warm_futures):
                if not future.done():
                    continue
                session_id = warm_futures.pop(future)
                try:
                    future.result()
                except Exception as exc:  # pragma: no cover - defensive worker boundary
                    add_fatal(f"{session_id}: {type(exc).__name__}: {exc}")

            tailer_error = tailer.error
            if tailer_error:
                for session_id in sorted(barrier_pending):
                    record_barrier_wait(session_id, False, "tailer_error")
                    add_fatal(f"{session_id}: barrier wait failed: {tailer_error}")
                barrier_pending.clear()
                for session_id in sorted(ready_to_warm):
                    add_fatal(f"{session_id}: warm not submitted after tailer error")
                ready_to_warm.clear()
            else:
                for session_id in list(barrier_pending):
                    if session_id not in build_contexts:
                        record_barrier_wait(session_id, False, "build_failed")
                        barrier_pending.remove(session_id)
                        continue
                    rejection_reason = reducer.warm_rejection_reason(session_id)
                    if rejection_reason is not None:
                        record_barrier_wait(session_id, False, rejection_reason)
                        add_fatal(
                            f"{session_id}: warm not submitted: {rejection_reason}"
                        )
                        barrier_pending.remove(session_id)
                        continue
                    if reducer.ready_for_warm(session_id):
                        record_barrier_wait(session_id, True)
                        ready_to_warm[session_id] = build_contexts[session_id]
                        barrier_pending.remove(session_id)

                while ready_to_warm and len(warm_futures) < args.build_workers:
                    session_id, context = ready_to_warm.popitem()
                    future = pool.submit(warm_session, context)
                    warm_futures[future] = session_id

            if not barrier_pending and not ready_to_warm and not warm_futures:
                break
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                for session_id in sorted(barrier_pending):
                    record_barrier_wait(session_id, False, "watchdog_timeout")
                    add_fatal(f"{session_id}: barrier wait watchdog timeout")
                barrier_pending.clear()
                for session_id in sorted(ready_to_warm):
                    add_fatal(f"{session_id}: warm not submitted before watchdog timeout")
                ready_to_warm.clear()
                break
            with tailer.condition:
                if not tailer.error:
                    tailer.condition.wait(timeout=min(0.25, remaining))

        # Warm HTTP calls and restore waits are bounded by the same watchdog
        # deadline.  Account for every submitted future without waiting for a
        # running worker after the deadline; the executor is shut down below
        # with wait=False so a stuck transport cannot delay final accounting.
        for future, session_id in list(warm_futures.items()):
            if not future.done():
                future.cancel()
                add_fatal(f"{session_id}: warm worker exceeded watchdog timeout")
                continue
            try:
                future.result()
            except Exception as exc:  # pragma: no cover - defensive worker boundary
                add_fatal(f"{session_id}: {type(exc).__name__}: {exc}")

        if tailer.error:
            add_fatal(f"run: terminal tailer error: {tailer.error}")
    finally:
        pool.shutdown(wait=False, cancel_futures=True)

    return [barrier_waits[session_id] for session_id in planned]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="parser/reducer sanity only; always NOT_VERIFIED")
    parser.add_argument("--events", type=Path, help="configured live p0_durable.v3 JSONL event file")
    parser.add_argument("--endpoint", help="explicit OpenAI-compatible endpoint or base URL")
    parser.add_argument("--model", help="explicit served model name")
    parser.add_argument("--model-path", help="explicit tokenizer/model path used by build_history_prompt")
    parser.add_argument("--api-key", default=os.environ.get("OPENAI_API_KEY"))
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--run-id", default="p0-session-barrier")
    parser.add_argument("--task-id", default="COD-20260908-P0-SESSION-BARRIER-VEHICLE")
    parser.add_argument("--epoch", default="E20260908-P0P1P2")
    parser.add_argument("--sessions", type=int, default=25)
    parser.add_argument("--active", type=int, default=8)
    parser.add_argument("--build-workers", type=int, default=8)
    parser.add_argument("--history-target", type=int, default=55000)
    parser.add_argument("--rh", choices=("off", "on"), default="off")
    parser.add_argument("--build-timeout-s", type=float, default=1500.0)
    parser.add_argument("--warm-timeout-s", type=float, default=1200.0)
    parser.add_argument("--watchdog-s", type=float, default=1800.0)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    _validate_frozen(args)
    if args.dry_run:
        source_events = _read_events(args.events, args.run_id) if args.events else _fixture(args.run_id)
        reducer = Reducer(args.run_id)
        build_rows = _build_rows_from_dry_run(source_events)
        for session_id, row in build_rows.items():
            reducer.establish_build(session_id, row["build_rid"], row["history_tokens"], row["short_suffix"])
        for event in source_events:
            reducer.ingest(event)
        result = _write_bundle(
            args.evidence_dir, args, reducer, build_rows, [], False, [], True
        )
        print(_json(result))
        return 0

    for name, value in (("--events", args.events), ("--endpoint", args.endpoint), ("--model", args.model), ("--model-path", args.model_path)):
        if not value:
            raise SystemExit(f"live mode requires explicit {name}")
    if not args.events.is_file():
        raise SystemExit(f"live event file does not exist: {args.events}")

    build_prompt = _load_builder(args.model_path)
    reducer = Reducer(args.run_id)
    tailer = EventTailer(args.events, reducer)
    tailer.start()
    build_rows: dict[str, dict[str, Any]] = {}
    barrier_waits: list[dict[str, Any]] = []
    fatal_errors: list[str] = []
    lock = threading.Lock()
    build_contexts = _run_build_phase(args, build_prompt, reducer, build_rows, fatal_errors, lock)
    churn_evidence = _run_churn_phase(
        args, build_prompt, build_contexts, reducer, fatal_errors, lock
    )
    if churn_evidence["failures"]:
        with lock:
            fatal_errors.append("churn phase failed; warm scheduler not started")
        barrier_waits = []
    else:
        barrier_waits = _run_warm_scheduler(
            args,
            reducer,
            tailer,
            build_rows,
            build_contexts,
            fatal_errors,
            lock,
        )
    tailer.stop()
    if tailer.error:
        with lock:
            message = f"run: terminal tailer error: {tailer.error}"
            if message not in fatal_errors:
                fatal_errors.append(message)
    result = _write_bundle(
        args.evidence_dir,
        args,
        reducer,
        build_rows,
        barrier_waits,
        True,
        fatal_errors,
        False,
        churn_evidence,
    )
    print(_json(result))
    return 0 if result["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
