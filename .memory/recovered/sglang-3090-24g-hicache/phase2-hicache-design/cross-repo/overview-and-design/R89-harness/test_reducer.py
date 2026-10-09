#!/usr/bin/env python3
"""Deterministic reducer tests, including every required fail-closed seam."""

from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from p0b_reducer import (
    IDENTITY,
    ORACLE,
    STATUS_INVALID_INPUT,
    STATUS_NOT_VERIFIED,
    load_provenance,
    parse_raw_jsonl,
    reduce_events,
)
from p0b_driver import gate_a

IDENTITY_VALUES = dict(zip(IDENTITY, ("run-r89", "session-r89", 7, "build-r89", "node-r89", "hash-r89")))
PROVENANCE = {
    "task_id": "P0-B-HARNESS-IMPLEMENT-20260911-R89",
    "epoch": "2026-09-11",
    "target": "RTX 3060 12G",
    "source_files": {"events.jsonl": "0" * 64},
}


def event(schema: str, name: str, **fields: object) -> dict[str, object]:
    return {"schema": schema, "event": name, "payload": {**IDENTITY_VALUES, **fields}}


def valid_events() -> list[dict[str, object]]:
    return [
        event(
            "p0_durable.v3",
            "durable_hit",
            positive_hit=True,
            full_kv_hit=True,
            complete_kv=True,
            all_sidecars=True,
        ),
        event("host_alloc.v1", "restore_host_alloc_wait", state="WAIT_CAPACITY", reason="HOST_ALLOC",
              positive_hit_tokens=54976, full_span=True, fifo_sequence=1, cache_instance_id="cache-r89",
              captured_generations={"kv": 4, "mamba": 2}),
        event("host_alloc.v1", "host_allocability_change", cache_instance_id="cache-r89", pool="kv",
              generation_before=4, generation_after=5, cause="queued_release_drain", returned_units=16,
              telemetry_sequence=10),
        event("host_alloc.v1", "restore_host_alloc_wake_decision", decision="grant",
              required_generations_advanced=True, generation_advanced=True, fifo_eligible=True,
              predecessor_check_passed=True, same_generation_self_wake=False,
              cache_instance_id="cache-r89", attempt_id="attempt-r89"),
        event("host_alloc.v1", "restore_host_alloc_retry_result", attempt_id="attempt-r89",
              retry_outcome="revoked_alloc_failed", positive_hit_tokens=54976, repeated_retry=False,
              skipped_eligible_predecessor=False, cache_instance_id="cache-r89"),
        event("host_alloc.v1", "restore_host_alloc_finalize", attempt_id="attempt-r89",
              all_or_nothing=True, complete_kv=True, all_sidecars=True, accepted=True,
              crop_attempted=False, lower_checkpoint_queried=False, partial_sidecar=False,
              discarded_hybrid=False, recompute_fallback=False),
        event("restore_ready", "restore_ready", attempt_id="attempt-r89", ready=True, admitted=True),
    ]


class ReducerTests(unittest.TestCase):
    def reduce(self, records: list[dict[str, object]], provenance: dict[str, object] | None = None) -> dict[str, object]:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            events_path = root / "events.jsonl"
            provenance_path = root / "provenance.json"
            events_path.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")
            provenance_path.write_text(json.dumps(provenance or PROVENANCE), encoding="utf-8")
            return reduce_events(parse_raw_jsonl([events_path]), load_provenance(provenance_path))

    def test_valid_input_has_exact_oracle_and_passes(self) -> None:
        result = self.reduce(valid_events())
        self.assertEqual(tuple(result["oracle"]), ORACLE)
        self.assertEqual(result["status"], "PASS")

    def test_missing_identity_and_generation_fail_closed(self) -> None:
        records = valid_events()
        records[0]["payload"] = {"positive_hit": True, "full_kv_hit": True, "complete_kv": True, "all_sidecars": True}
        records[2]["payload"].pop("generation_after")
        result = self.reduce(records)
        self.assertEqual(result["status"], STATUS_NOT_VERIFIED)
        self.assertFalse(result["oracle"]["singular_identity"])
        self.assertFalse(result["oracle"]["generation_transition"])

    def test_negative_crop_genuine_miss_same_generation_and_repeated_retry(self) -> None:
        for flag, event_index in (
            ("crop_attempted", 1),
            ("genuine_miss", 1),
            ("same_generation_self_wake", 3),
            ("repeated_retry", 4),
        ):
            records = copy.deepcopy(valid_events())
            records[event_index]["payload"][flag] = True
            result = self.reduce(records)
            self.assertEqual(result["status"], STATUS_NOT_VERIFIED, flag)
            self.assertFalse(result["oracle"]["negative_safety"], flag)

    def test_synthetic_trace_is_invalid_input(self) -> None:
        records = [{"schema": "p0b.trace.v1", "event": "synthetic", "payload": {}}]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            event_path = root / "events.jsonl"
            provenance_path = root / "provenance.json"
            event_path.write_text(json.dumps(records[0]) + "\n", encoding="utf-8")
            provenance_path.write_text(json.dumps(PROVENANCE), encoding="utf-8")
            with self.assertRaises(ValueError):
                parse_raw_jsonl([event_path])
        self.assertEqual(STATUS_INVALID_INPUT, "INVALID_INPUT")

    def test_gate_a_inputs_without_park_cannot_be_pass(self) -> None:
        records = valid_events()
        records.pop(1)
        result = self.reduce(records)
        self.assertEqual(result["status"], STATUS_NOT_VERIFIED)
        self.assertFalse(result["oracle"]["host_alloc_park"])

    def test_gate_a_blocks_before_abort_when_park_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            events_path = root / "events.jsonl"
            provenance_path = root / "provenance.json"
            events_path.write_text(json.dumps(valid_events()[0]) + "\n", encoding="utf-8")
            provenance_path.write_text(json.dumps(PROVENANCE), encoding="utf-8")
            passed, message = gate_a(events_path, provenance_path)
        self.assertFalse(passed)
        self.assertIn("blocked", message.lower())


if __name__ == "__main__":
    unittest.main()
