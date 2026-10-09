#!/usr/bin/env python3
"""R97 deterministic reducer/driver self-tests (no server and no product import)."""

from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import urllib.error

from p0b_driver import gate_a, main as driver_main
from p0b_reducer import (
    IDENTITY,
    ORACLE,
    STATUS_INVALID_INPUT,
    STATUS_NOT_VERIFIED,
    InputError,
    MissingEvidence,
    load_provenance,
    parse_raw_jsonl,
    reduce_events,
)

IDENTITY_VALUES = dict(zip(IDENTITY, ("run-r97", "session-r97", 1, "build-r97", "node-r97", "hash-r97")))
COMMON = {"ts_mono_ns": 1, "ts_wall_ms": 2, "worker": "worker-r97", "rank": 0}
PROVENANCE_BASE = {
    "format": "p0b.raw-bundle.v2",
    "task_id": "P0-B-HARNESS-IMPLEMENT-20260911-R97",
    "epoch": "2026-09-11",
    "target": "RTX 3060 12G",
    "immutable": True,
    "runtime": {"pid": 3060, "worker": "worker-r97"},
    "profile": {"profile_id": "rtx3060-sm86-r97", "gpu": "RTX 3060 12G", "compute_capability": "8.6"},
    "source_files": {},
    "raw_files": {},
    "event_sources": {},
    "capture": {"complete": True, "collector": "raw-jsonl"},
}


def event(schema: str, name: str, **fields: object) -> dict[str, object]:
    return {"schema": schema, "evt": name, **COMMON, **IDENTITY_VALUES, **fields}


def valid_events() -> list[dict[str, object]]:
    return [
        event("p0_durable.v3", "durability_barrier", kv_durable=True, mamba_durable=True, kv_completed_tokens=54976, kv_requested_tokens=54976, mamba_expected_pages=32, mamba_succeeded_pages=32),
        event("p0_durable.v3", "storage_query", kv_hit_pages=54976, storage_hit_count=54976, sidecar_hits={"mamba": 32}),
        event("host_alloc.v1", "restore_host_alloc_wait", rid="target-r97", attempt_id="attempt-0", cache_instance_id="cache-r97", trace_context={"profile_id": "rtx3060-sm86-r97"}, state="WAIT_CAPACITY", reason="HOST_ALLOC", positive_hit_tokens=54976, sidecar_hit_pages={"mamba": 32}, requested_primary_tokens=54976, required_aux_units={"mamba": 32}, blocked_domains=["kv", "mamba"], captured_generations={"kv": 4, "mamba": 2}, current_generations={"kv": 4, "mamba": 2}, free_units={"kv": 0, "mamba": 0}, evictable_units={"kv": 0, "mamba": 0}, prefetch_reservation_held=False, fifo_sequence=1, wait_started_mono_ns=10, deadline_mono_ns=600, retry_grant=False, retry_skip=False, retry_outcome="parked"),
        event("host_alloc.v1", "host_allocability_change", rid=None, attempt_id=None, cache_instance_id="cache-r97", trace_context=None, pool="kv", generation_before=4, generation_after=5, cause="queued_release_drain", returned_units=16, evictable_before=0, evictable_after=0, telemetry_seq=10),
        event("host_alloc.v1", "host_allocability_change", rid=None, attempt_id=None, cache_instance_id="cache-r97", trace_context=None, pool="mamba", generation_before=2, generation_after=3, cause="queued_release_drain", returned_units=32, evictable_before=0, evictable_after=0, telemetry_seq=11),
        event("host_alloc.v1", "restore_host_alloc_wake_decision", rid="target-r97", attempt_id="attempt-0", cache_instance_id="cache-r97", trace_context={"profile_id": "rtx3060-sm86-r97"}, decision="grant", captured_generations={"kv": 4, "mamba": 2}, current_generations={"kv": 5, "mamba": 2}, blocked_domains=["kv", "mamba"], required_aux_units={"mamba": 32}, requested_primary_tokens=54976, fifo_sequence=1, generation_vector_id="cache-r97:kv=5,mamba=2", global_grant_used=True, budget_available=True, free_units={"kv": 16}, evictable_units={"kv": 0}, retry_grant=True, retry_skip=False, retry_outcome="grant"),
        event("host_alloc.v1", "restore_host_alloc_retry_result", rid="target-r97", attempt_id="attempt-1", cache_instance_id="cache-r97", trace_context={"profile_id": "rtx3060-sm86-r97"}, generation_vector_id="cache-r97:kv=5,mamba=2", full_frontier_tokens=54976, crop_attempted=False, lower_checkpoint_queried=False, per_pool={"kv": {"required": 54976, "free_before": 0, "evictable_before": 0, "alloc1": None, "reclaimed": 0, "alloc2": None, "free_after": 0, "evictable_after": 0}}, failed_domains=["kv"], terminal="revoked_alloc_failed", genuine_miss=False, captured_generations_after={"kv": 5, "mamba": 2}, reservation_released=True, retry_outcome="revoked_alloc_failed"),
        event("host_alloc.v1", "restore_hybrid_finalize", rid="target-r97", attempt_id="attempt-1", cache_instance_id="cache-r97", trace_context={"profile_id": "rtx3060-sm86-r97"}, kv_expected=54976, kv_fetched=54976, sidecars={"mamba": {"expected": 32, "fetched": 32}}, per_sidecar={"mamba": {"expected": 32, "fetched": 32}}, all_or_nothing=True, result="accepted", restore_state_after="READY"),
        event("rh_ready_host.v1", "ready_host", rid="target-r97", attempt_id="attempt-1", issue_origin="DEMAND_RETRY", completed_kv_tokens=54976, required_aux_pools=["mamba"], completed_aux_units={"mamba": 32}, restore_state_before="WAIT_CAPACITY", restore_state_after="READY", finalize_result="accepted", ready_monotonic_ns=100),
    ]


class ReducerTests(unittest.TestCase):
    def reduce(self, records: list[dict[str, object]], provenance: dict[str, object] | None = None) -> dict[str, object]:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            events_path = root / "events.jsonl"
            source_path = root / "source.py"
            source_path.write_text("# checked-out source\n", encoding="utf-8")
            events_path.write_text("".join(json.dumps(record, sort_keys=True) + "\n" for record in records), encoding="utf-8")
            manifest = copy.deepcopy(provenance or PROVENANCE_BASE)
            manifest["source_files"] = {str(source_path): hashlib.sha256(source_path.read_bytes()).hexdigest()}
            manifest["raw_files"] = {str(events_path): hashlib.sha256(events_path.read_bytes()).hexdigest()}
            manifest["event_sources"] = {
                "durability_barrier": [f"{events_path.resolve()}:1"],
                "storage_query": [f"{events_path.resolve()}:2"],
                "restore_host_alloc_wait": [f"{events_path.resolve()}:3"],
                "host_allocability_change": [f"{events_path.resolve()}:4", f"{events_path.resolve()}:5"],
                "restore_host_alloc_wake_decision": [f"{events_path.resolve()}:6"],
                "restore_host_alloc_retry_result": [f"{events_path.resolve()}:7"],
                "restore_hybrid_finalize": [f"{events_path.resolve()}:8"],
                "ready_host": [f"{events_path.resolve()}:9"],
            }
            return reduce_events(parse_raw_jsonl([events_path]), load_provenance(self._manifest(root, manifest), [events_path]))

    @staticmethod
    def _manifest(root: Path, manifest: dict[str, object]) -> Path:
        path = root / "provenance.json"
        path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
        return path

    def test_positive_raw_event_chain_passes_exact_oracle(self) -> None:
        result = self.reduce(valid_events())
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(tuple(result["oracle"]), ORACLE)
        self.assertEqual(len(result["raw_references"]), 9)

    def test_missing_identity_is_not_verified(self) -> None:
        records = valid_events(); records[0].pop("session_id")
        result = self.reduce(records)
        self.assertEqual(result["status"], STATUS_NOT_VERIFIED)
        self.assertFalse(result["oracle"]["singular_identity"])

    def test_missing_generation_edge_is_not_verified(self) -> None:
        records = valid_events(); records[3]["generation_after"] = 7
        result = self.reduce(records)
        self.assertEqual(result["status"], STATUS_NOT_VERIFIED)
        self.assertFalse(result["oracle"]["generation_transition"])

    def test_fifo_predecessor_skip_is_not_verified(self) -> None:
        records = valid_events(); predecessor = copy.deepcopy(records[2]); predecessor["rid"] = "predecessor"; predecessor["fifo_sequence"] = 0; records.insert(3, predecessor); records[5]["fifo_sequence"] = 1
        result = self.reduce(records)
        self.assertEqual(result["status"], STATUS_NOT_VERIFIED)
        self.assertFalse(result["oracle"]["fifo_predecessor"])

    def test_attempt_lineage_break_is_not_verified(self) -> None:
        records = valid_events(); records[4]["attempt_id"] = "forged-attempt"; records[5]["attempt_id"] = "attempt-1"
        result = self.reduce(records)
        self.assertEqual(result["status"], STATUS_NOT_VERIFIED)
        self.assertFalse(result["oracle"]["attempt_lineage"])

    def test_partial_finalization_is_not_verified(self) -> None:
        records = valid_events(); records[7]["result"] = "discarded"
        result = self.reduce(records)
        self.assertEqual(result["status"], STATUS_NOT_VERIFIED)
        self.assertFalse(result["oracle"]["accepted_finalization"])

    def test_ready_before_finalize_is_not_verified(self) -> None:
        records = valid_events(); records[8], records[7] = records[7], records[8]
        result = self.reduce(records)
        self.assertEqual(result["status"], STATUS_NOT_VERIFIED)
        self.assertFalse(result["oracle"]["ready_after_finalize"])

    def test_missing_provenance_is_not_verified(self) -> None:
        records = valid_events()
        with self.assertRaises(MissingEvidence):
            self.reduce(records, {"format": "p0b.raw-bundle.v2"})

    def test_ready_event_missing_is_not_verified(self) -> None:
        records = valid_events()[:-1]
        result = self.reduce(records)
        self.assertEqual(result["status"], STATUS_NOT_VERIFIED)
        self.assertFalse(result["oracle"]["ready_after_finalize"])

    def test_summary_boolean_is_invalid_input(self) -> None:
        records = valid_events(); records[0]["positive_hit"] = True
        with self.assertRaises(InputError):
            parse_raw_jsonl([self._raw_path(records)])

    @staticmethod
    def _raw_path(records: list[dict[str, object]]) -> Path:
        directory = Path(tempfile.mkdtemp())
        path = directory / "events.jsonl"
        path.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")
        return path

    def test_synthetic_schema_is_invalid_input(self) -> None:
        with self.assertRaises(InputError):
            parse_raw_jsonl([self._raw_path([{"schema": "p0b.trace.v1", "evt": "synthetic"}])])

    def test_contradictory_identity_is_invalid_input(self) -> None:
        records = valid_events(); records[-1]["session_id"] = "other-session"
        with self.assertRaises(InputError):
            reduce_events(parse_raw_jsonl([self._raw_path(records)]), PROVENANCE_BASE)

    def test_gate_a_does_not_accept_incomplete_chain(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); events = root / "events.jsonl"; source = root / "source.py"; source.write_text("source\n")
            events.write_text(json.dumps(valid_events()[2]) + "\n")
            manifest = copy.deepcopy(PROVENANCE_BASE); manifest["source_files"] = {str(source): hashlib.sha256(source.read_bytes()).hexdigest()}; manifest["raw_files"] = {str(events): hashlib.sha256(events.read_bytes()).hexdigest()}; manifest["event_sources"] = {"restore_host_alloc_wait": [f"{events.resolve()}:1"]}
            provenance = self._manifest(root, manifest)
            passed, message = gate_a(events, provenance)
        self.assertFalse(passed); self.assertIn("not verified", message.lower())

    def _driver_files(self, root: Path) -> tuple[Path, Path]:
        events = root / "events.jsonl"; source = root / "source.py"
        events.write_text("".join(json.dumps(record, sort_keys=True) + "\n" for record in valid_events()), encoding="utf-8")
        source.write_text("source\n", encoding="utf-8")
        manifest = copy.deepcopy(PROVENANCE_BASE)
        manifest["source_files"] = {str(source): hashlib.sha256(source.read_bytes()).hexdigest()}
        manifest["raw_files"] = {str(events): hashlib.sha256(events.read_bytes()).hexdigest()}
        manifest["event_sources"] = {
            "durability_barrier": [f"{events.resolve()}:1"],
            "storage_query": [f"{events.resolve()}:2"],
            "restore_host_alloc_wait": [f"{events.resolve()}:3"],
            "host_allocability_change": [f"{events.resolve()}:4", f"{events.resolve()}:5"],
            "restore_host_alloc_wake_decision": [f"{events.resolve()}:6"],
            "restore_host_alloc_retry_result": [f"{events.resolve()}:7"],
            "restore_hybrid_finalize": [f"{events.resolve()}:8"],
            "ready_host": [f"{events.resolve()}:9"],
        }
        provenance = self._manifest(root, manifest)
        return events, provenance

    def test_driver_rejects_non_3060_and_timeout_bounds(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); events, provenance = self._driver_files(root); output = root / "out"
            with patch("builtins.print"):
                self.assertEqual(driver_main(["--target-label", "RTX 3090 24G", "--profile-id", "x", "--events", str(events), "--provenance", str(provenance), "--evidence-dir", str(output)]), 0)
                self.assertEqual(driver_main(["--target-label", "RTX 3060 12G", "--profile-id", "x", "--events", str(events), "--provenance", str(provenance), "--evidence-dir", str(output), "--deadline-seconds", "601"]), 0)

    def test_driver_rejects_holder_prefix_collision(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); events, provenance = self._driver_files(root); output = root / "out"
            with patch("builtins.print") as printer:
                driver_main(["--target-label", "RTX 3060 12G", "--profile-id", "rtx3060-sm86-r97", "--events", str(events), "--provenance", str(provenance), "--evidence-dir", str(output), "--holder-rid", "rid", "--target-rid", "rid-child"])
            report = json.loads(printer.call_args.args[0])
        self.assertEqual(report["status"], "INVALID_INPUT")

    def test_driver_unavailable_endpoint_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); events, provenance = self._driver_files(root); output = root / "out"
            with patch("p0b_driver._http_json", side_effect=urllib.error.URLError("offline")):
                with patch("builtins.print") as printer:
                    driver_main(["--target-label", "RTX 3060 12G", "--profile-id", "rtx3060-sm86-r97", "--events", str(events), "--provenance", str(provenance), "--evidence-dir", str(output)])
            report = json.loads(printer.call_args.args[0])
        self.assertEqual(report["status"], "BLOCKED")
        self.assertIn("unavailable", report["reason"])
        self.assertFalse(any(item.get("path") == "/abort_request" for item in report["transcript"]))

    def test_driver_uses_exact_holder_abort_payload(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); events, provenance = self._driver_files(root); output = root / "out"; calls = []
            def fake_http(url: str, payload: dict[str, object], timeout: float) -> tuple[int, str]:
                calls.append((url, payload)); return 200, "{}"
            with patch("p0b_driver._http_json", side_effect=fake_http):
                with patch("builtins.print"):
                    driver_main(["--target-label", "RTX 3060 12G", "--profile-id", "rtx3060-sm86-r97", "--events", str(events), "--provenance", str(provenance), "--evidence-dir", str(output)])
        self.assertEqual(calls[-1][1], {"rid": "p0b-r97-holder", "abort_all": False})


if __name__ == "__main__":
    unittest.main()
