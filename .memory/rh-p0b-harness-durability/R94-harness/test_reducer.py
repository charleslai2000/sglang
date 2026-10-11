#!/usr/bin/env python3
"""Synthetic raw-record tests for every R94 fail-closed boundary."""

from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from p0b_driver import gate_a
from p0b_reducer import (
    IDENTITY,
    ORACLE,
    STATUS_INVALID_INPUT,
    STATUS_NOT_VERIFIED,
    load_provenance,
    parse_raw_jsonl,
    reduce_events,
)

IDENTITY_VALUES = dict(zip(IDENTITY, ("rid-r94", "session-r94", 1, "node-r94", "build-r94", 9, 3060, "profile-r94", "manifest-r94")))


def record(schema: str, event: str, event_id: str, ts_ns: int, **fields: object) -> dict[str, object]:
    return {"schema": schema, "event": event, "payload": {**IDENTITY_VALUES, "event_id": event_id, "ts_ns": ts_ns, **fields}}


def valid_events() -> list[dict[str, object]]:
    return [
        record("admission.v2", "request_created", "e1", 1, role="target", admission_state="accepted"),
        record("host_alloc.v1", "kv_lookup", "e2", 2, span_id="kv-span", requested_units=54976, resident_units=54976, lookup_outcome="HIT", lookup_generation=4),
        record("host_alloc.v1", "sidecar_lookup", "e3", 3, sidecar_id="mamba-span", required_units=1024, resident_units=1024, lookup_outcome="HIT", lookup_generation=2),
        record("host_alloc.v1", "wait_entered", "e4", 4, wait_id="wait-r94", state="WAIT_CAPACITY", reason="HOST_ALLOC", blocked_pool_generations={"kv": 4, "mamba": 2}, fifo_ticket=20),
        record("rh_holder.v1", "holder_staged", "e5", 5, holder_state="STAGED", holder_rid="holder-r94"),
        record("host_alloc.v1", "predecessor_terminal", "e6", 6, wait_id="wait-prev", terminal_state="RELEASED"),
        record("host_alloc.v1", "generation_edge", "e7", 7, wait_id="wait-r94", pool="kv", from_generation=4, to_generation=5, edge_seq=1, cause="release"),
        record("host_alloc.v1", "generation_edge", "e8", 8, wait_id="wait-r94", pool="mamba", from_generation=2, to_generation=3, edge_seq=2, cause="release"),
        record("host_alloc.v1", "fifo_predecessor", "e9", 9, wait_id="wait-r94", fifo_ticket=20, predecessor_wait_id="wait-prev", predecessor_ticket=19, predecessor_terminal_event_id="e6"),
        record("host_alloc.v1", "wake_grant", "e10", 10, wait_id="wait-r94", attempt_id="attempt-r94", required_pools=["kv", "mamba"], observed_generations={"kv": 5, "mamba": 3}, predecessor_event_id="e9", grant_state="RETRY_ELIGIBLE"),
        record("host_alloc.v1", "retry_attempt", "e11", 11, wait_id="wait-r94", attempt_id="attempt-r94", wake_event_id="e10", retry_outcome="REVOKED_ALLOC_FAILED", attempt_number=1, attempt_origin="HOST_ALLOC_WAKE"),
        record("restore.v1", "restore_completed", "e12", 12, attempt_id="attempt-r94", restore_state="COMPLETE", restored_units=54976, restored_sidecar_units=1024, origin_event_id="e11"),
        record("finalization.v1", "finalization_accepted", "e13", 13, attempt_id="attempt-r94", finalization_state="ACCEPTED", atomicity="ALL_OR_NOTHING", commit_id="commit-r94", origin_event_id="e12"),
        record("rh_ready_host.v1", "ready", "e14", 14, attempt_id="attempt-r94", ready_state="READY", admission_state="ACCEPTED", finalization_event_id="e13"),
    ]


class ReducerTests(unittest.TestCase):
    def reduce(self, records: list[dict[str, object]], **provenance_overrides: object) -> dict[str, object]:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            events_path = root / "events.jsonl"
            events_path.write_text("".join(json.dumps(item, sort_keys=True) + "\n" for item in records), encoding="utf-8")
            digest = hashlib.sha256(events_path.read_bytes()).hexdigest()
            provenance = {
                "task_id": "P0-B-HARNESS-IMPLEMENT-20260911-R94",
                "epoch": "2026-09-11",
                "target": "RTX 3060 12G",
                "server_pid": 3060,
                "profile": "profile-r94",
                "source_manifest_id": "manifest-r94",
                "source_files": {str(events_path.resolve()): digest},
                "bounds": {"max_seconds": 600, "max_requests": 6},
            }
            provenance.update(provenance_overrides)
            provenance_path = root / "provenance.json"
            provenance_path.write_text(json.dumps(provenance, sort_keys=True), encoding="utf-8")
            return reduce_events(parse_raw_jsonl([events_path]), load_provenance(provenance_path))

    def test_positive_raw_authoritative_chain_passes_exact_oracle(self) -> None:
        result = self.reduce(valid_events())
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(tuple(result["oracle"]), ORACLE)
        self.assertTrue(all(result["oracle"].values()))

    def test_every_identity_generation_provenance_edge_is_not_verified(self) -> None:
        cases = []
        for field in ("rid", "session_id", "session_generation", "node_id", "build_rid", "generation", "server_pid", "profile", "source_manifest_id"):
            records = valid_events()
            records[0]["payload"].pop(field)
            cases.append(records)
        records = valid_events()
        records[6]["payload"].pop("from_generation")
        cases.append(records)
        for records in cases:
            self.assertEqual(self.reduce(records)["status"], STATUS_NOT_VERIFIED)
        self.assertEqual(self.reduce(valid_events(), source_files={})["status"], STATUS_NOT_VERIFIED)
        self.assertEqual(self.reduce(valid_events(), server_pid=None)["status"], STATUS_NOT_VERIFIED)
        self.assertEqual(self.reduce(valid_events(), source_manifest_id="wrong")["status"], STATUS_INVALID_INPUT)

    def test_summary_booleans_are_invalid_not_evidence(self) -> None:
        records = valid_events()
        records[1]["payload"]["full_kv_hit"] = True
        with self.assertRaises(ValueError):
            self.reduce(records)

    def test_wrong_schema_and_wrong_pid_profile_are_invalid(self) -> None:
        records = valid_events()
        records[0]["schema"] = "p0b.trace.v1"
        with self.assertRaises(ValueError):
            parse_raw_jsonl_from_records(records)
        records = valid_events()
        records[0]["payload"]["server_pid"] = 999
        self.assertEqual(self.reduce(records)["status"], STATUS_INVALID_INPUT)
        records = valid_events()
        records[0]["payload"]["profile"] = "wrong"
        self.assertEqual(self.reduce(records)["status"], STATUS_INVALID_INPUT)

    def test_noncontiguous_generation_is_invalid(self) -> None:
        records = valid_events()
        records[6]["payload"]["to_generation"] = 6
        self.assertEqual(self.reduce(records)["status"], STATUS_INVALID_INPUT)

    def test_fifo_predecessor_missing_and_retry_lineage_mismatch(self) -> None:
        records = valid_events()
        records.pop(8)
        self.assertEqual(self.reduce(records)["status"], STATUS_NOT_VERIFIED)
        records = valid_events()
        records[10]["payload"]["wake_event_id"] = "other"
        self.assertEqual(self.reduce(records)["status"], STATUS_INVALID_INPUT)

    def test_incomplete_finalization_and_ready_are_not_verified(self) -> None:
        for index in (12, 13):
            records = valid_events()
            records.pop(index)
            self.assertEqual(self.reduce(records)["status"], STATUS_NOT_VERIFIED)

    def test_timeout_and_over_limit_are_not_verified(self) -> None:
        records = valid_events()
        records[-1]["payload"]["ts_ns"] = 600_000_000_002
        self.assertEqual(self.reduce(records)["status"], STATUS_NOT_VERIFIED)
        records = valid_events()
        for index in range(7):
            records.insert(1, record("admission.v2", "request_created", f"extra-{index}", 1, role="auxiliary", admission_state="accepted"))
        self.assertEqual(self.reduce(records)["status"], STATUS_NOT_VERIFIED)

    def test_negative_crop_miss_same_generation_and_repeated_retry(self) -> None:
        for index, field, value in ((1, "lookup_outcome", "CROP"), (2, "lookup_outcome", "MISS"), (9, "grant_state", "SAME_GENERATION"), (10, "attempt_number", 2)):
            records = valid_events()
            records[index]["payload"][field] = value
            self.assertEqual(self.reduce(records)["status"], STATUS_NOT_VERIFIED)

    def test_rh_ready_host_v1_accepted_semantics(self) -> None:
        result = self.reduce(valid_events())
        self.assertTrue(result["oracle"]["ready_after_finalize"])

    def test_public_create_gate_a_inability_is_not_verified(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            events = root / "events.jsonl"
            provenance = root / "provenance.json"
            events.write_text(json.dumps(valid_events()[0]) + "\n", encoding="utf-8")
            provenance.write_text(json.dumps({"bad": "manifest"}), encoding="utf-8")
            passed, message = gate_a(events, provenance)
        self.assertFalse(passed)
        self.assertIn("not established", message.lower())


def parse_raw_jsonl_from_records(records: list[dict[str, object]]) -> list[object]:
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "events.jsonl"
        path.write_text(json.dumps(records[0]) + "\n", encoding="utf-8")
        return parse_raw_jsonl([path])


if __name__ == "__main__":
    unittest.main()
