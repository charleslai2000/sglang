#!/usr/bin/env python3
"""Adversarial stdlib ``unittest`` suite for the R115 coverage gate.

Every test builds a small synthetic bundle in a temporary directory and runs
``coverage_gate.py`` as a subprocess, asserting both the process exit code and
the parsed JSON verdict.  No pytest, no product imports.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
CHECKER = os.path.join(HERE, "coverage_gate.py")

MANIFEST_FORMAT = "p0b.raw-bundle.v3"

SID = "sess-1"
GEN = 5
BUILD = "b" * 32
LK = "rid-1:5"
R = 100
NODE = "10"
HASH = "a" * 64


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------


def _finalize(**over):
    record = {
        "schema": "host_alloc.v1",
        "evt": "restore_hybrid_finalize",
        "result": "accepted",
        "lifecycle_key": LK,
        "kv_expected": R,
        "kv_fetched": R,
        "trace_context": {
            "session_id": SID,
            "session_generation": GEN,
            "build_rid": BUILD,
        },
    }
    record.update(over)
    return record


def _park(**over):
    record = {
        "schema": "host_alloc.v1",
        "evt": "restore_host_alloc_wait",
        "state": "WAIT_CAPACITY",
        "reason": "HOST_ALLOC",
        "lifecycle_key": LK,
        "requested_primary_tokens": R,
        "positive_hit_tokens": R,
    }
    record.update(over)
    return record


def _residency(evt="residency_detach", node=NODE, final_kv_hash=HASH, **over):
    record = {
        "evt": evt,
        "trace": "p0_durable",
        "session_id": SID,
        "session_generation": GEN,
        "build_rid": BUILD,
        "node_id": node,
        "final_kv_hash": final_kv_hash,
    }
    record.update(over)
    return record


def _barrier(
    node=NODE,
    final_kv_hash=HASH,
    completed=R,
    requested=None,
    expected_pages=4,
    succeeded_pages=4,
    **over,
):
    if requested is None:
        requested = completed
    record = {
        "evt": "durability_barrier",
        "trace": "p0_durable",
        "session_id": SID,
        "session_generation": GEN,
        "build_rid": BUILD,
        "node_id": node,
        "final_kv_hash": final_kv_hash,
        "kv_durable": True,
        "mamba_durable": True,
        "kv_completed_tokens": completed,
        "kv_requested_tokens": requested,
        "mamba_expected_pages": expected_pages,
        "mamba_succeeded_pages": succeeded_pages,
    }
    record.update(over)
    return record


def _persisted(node=NODE, frontier=R, **over):
    record = {
        "evt": "storage_persisted",
        "trace": "p0_durable",
        "session_id": SID,
        "session_generation": GEN,
        "build_rid": BUILD,
        "node_id": node,
        "frontier_end": frontier,
    }
    record.update(over)
    return record


def _manifest(**over):
    manifest = {
        "format": MANIFEST_FORMAT,
        "task_id": "R115-test",
        "target": {"rid": "rid-1", "lifecycle_key": LK},
    }
    manifest.update(over)
    return manifest


def _run_gate(*, raw_records, probe_records, manifest):
    """Write a temp bundle and run the checker CLI as a subprocess."""
    with tempfile.TemporaryDirectory() as tmpdir:
        raw_path = os.path.join(tmpdir, "raw.log")
        probe_path = os.path.join(tmpdir, "probe.log")
        manifest_path = os.path.join(tmpdir, "manifest.json")
        with open(raw_path, "w", encoding="utf-8") as handle:
            for record in raw_records:
                handle.write("[HAE] " + json.dumps(record, sort_keys=True) + "\n")
        with open(probe_path, "w", encoding="utf-8") as handle:
            for record in probe_records:
                handle.write(json.dumps(record, sort_keys=True) + "\n")
        with open(manifest_path, "w", encoding="utf-8") as handle:
            json.dump(manifest, handle)
        proc = subprocess.run(
            [
                sys.executable,
                CHECKER,
                "--events",
                raw_path,
                probe_path,
                "--manifest",
                manifest_path,
                "--json",
            ],
            capture_output=True,
            text=True,
        )
    verdict = json.loads(proc.stdout) if proc.stdout.strip() else None
    return proc.returncode, verdict, proc


class CoverageGateTests(unittest.TestCase):
    def _assert_verdict(self, proc, code, verdict, expected_exit, expected_reason=None):
        self.assertIsNotNone(verdict, msg=f"no JSON verdict; stderr={proc.stderr!r}")
        self.assertEqual(expected_exit, code, msg=f"verdict={verdict}")
        if expected_exit == 0:
            self.assertEqual("PASS", verdict["status"])
            self.assertIsNone(verdict["reason"])
        else:
            self.assertEqual("FAIL", verdict["status"])
            if expected_reason is not None:
                self.assertEqual(expected_reason, verdict["reason"], msg=f"verdict={verdict}")

    def test_exact_prefix_coverage_passes(self):
        code, verdict, proc = _run_gate(
            raw_records=[_park(), _finalize()],
            probe_records=[
                _residency("residency_detach", node=NODE, final_kv_hash=HASH),
                _barrier(node=NODE, final_kv_hash=HASH, completed=R),
                _persisted(node=NODE, frontier=R),
            ],
            manifest=_manifest(),
        )
        self._assert_verdict(proc, code, verdict, 0)
        self.assertEqual(R, verdict["required_frontier"])
        self.assertEqual(R, verdict["covered_frontier"])
        self.assertIsNotNone(verdict["linked_barrier"])
        self.assertGreaterEqual(verdict["target_restore_node_count"], 1)

    def test_small_early_barrier_larger_target_fails(self):
        # A complete barrier exists, but it (and its persisted frontier) covers
        # far fewer tokens than the target restore requires: false-PASS guard.
        code, verdict, proc = _run_gate(
            raw_records=[_park(), _finalize()],
            probe_records=[
                _residency("residency_detach", node=NODE, final_kv_hash=HASH),
                _barrier(node=NODE, final_kv_hash=HASH, completed=40),
                _persisted(node=NODE, frontier=40),
            ],
            manifest=_manifest(),
        )
        self._assert_verdict(proc, code, verdict, 1, "frontier_below_required")
        self.assertEqual(R, verdict["required_frontier"])
        self.assertEqual(40, verdict["covered_frontier"])
        self.assertIsNotNone(verdict["linked_barrier"])

    def test_barrier_wrong_build_or_session_fails(self):
        for wrong in (
            {"build_rid": "c" * 32},
            {"session_id": "other-session"},
        ):
            with self.subTest(wrong=wrong):
                code, verdict, proc = _run_gate(
                    raw_records=[_park(), _finalize()],
                    probe_records=[
                        _residency("residency_detach", node=NODE, final_kv_hash=HASH),
                        _barrier(node=NODE, final_kv_hash=HASH, completed=R, **wrong),
                        _persisted(node=NODE, frontier=R),
                    ],
                    manifest=_manifest(),
                )
                self._assert_verdict(proc, code, verdict, 1, "no_durable_barrier")
                self.assertEqual([], verdict["barrier_candidates"])

    def test_barrier_node_not_on_target_chain_fails(self):
        code, verdict, proc = _run_gate(
            raw_records=[_park(), _finalize()],
            probe_records=[
                _residency("residency_detach", node=NODE, final_kv_hash=HASH),
                _barrier(node="99", final_kv_hash="d" * 64, completed=R),
                _persisted(node=NODE, frontier=R),
            ],
            manifest=_manifest(),
        )
        self._assert_verdict(proc, code, verdict, 1, "no_linked_barrier")
        self.assertEqual(1, len(verdict["barrier_candidates"]))
        self.assertIsNone(verdict["linked_barrier"])

    def test_missing_target_trace_context_fails_closed(self):
        finalize = _finalize()
        del finalize["trace_context"]
        code, verdict, proc = _run_gate(
            raw_records=[_park(), finalize],
            probe_records=[
                _residency("residency_detach", node=NODE, final_kv_hash=HASH),
                _barrier(node=NODE, final_kv_hash=HASH, completed=R),
                _persisted(node=NODE, frontier=R),
            ],
            manifest=_manifest(),
        )
        self._assert_verdict(proc, code, verdict, 1, "insufficient_target_identity")

    def test_missing_target_lineage_fails_closed(self):
        code, verdict, proc = _run_gate(
            raw_records=[_park(), _finalize()],
            probe_records=[],
            manifest=_manifest(),
        )
        self._assert_verdict(proc, code, verdict, 1, "insufficient_target_lineage")
        self.assertEqual(0, verdict["target_restore_node_count"])

    def test_barrier_without_persisted_frontier_does_not_pass(self):
        # A complete, linked barrier exists, but there is no
        # storage_persisted-derived frontier on the target chain.  The gate
        # must not default to PASS on barrier presence alone.
        code, verdict, proc = _run_gate(
            raw_records=[_park(), _finalize()],
            probe_records=[
                _residency("residency_detach", node=NODE, final_kv_hash=HASH),
                _barrier(node=NODE, final_kv_hash=HASH, completed=R),
            ],
            manifest=_manifest(),
        )
        self._assert_verdict(proc, code, verdict, 1, "insufficient_frontier_evidence")
        self.assertIsNotNone(verdict["linked_barrier"])
        self.assertIsNone(verdict["covered_frontier"])

    def test_invalid_input_exit_2(self):
        manifest = _manifest()
        del manifest["format"]
        code, verdict, proc = _run_gate(
            raw_records=[_park(), _finalize()],
            probe_records=[
                _residency("residency_detach", node=NODE, final_kv_hash=HASH),
                _barrier(node=NODE, final_kv_hash=HASH, completed=R),
                _persisted(node=NODE, frontier=R),
            ],
            manifest=manifest,
        )
        self.assertIsNotNone(verdict, msg=f"no JSON verdict; stderr={proc.stderr!r}")
        self.assertEqual(2, code, msg=f"verdict={verdict}")
        self.assertEqual("INVALID_INPUT", verdict["status"])


if __name__ == "__main__":
    unittest.main()
