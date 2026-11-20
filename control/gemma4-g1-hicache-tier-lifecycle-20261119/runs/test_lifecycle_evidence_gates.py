#!/usr/bin/env python3
"""CPU-only positive/negative tests for lifecycle qualification evidence gates."""

import importlib.util
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).with_name("run_radix_tree_lifecycle.py")
SPEC = importlib.util.spec_from_file_location("radix_lifecycle", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)


class LifecycleEvidenceGateTest(unittest.TestCase):
    def test_l1_source_is_device_only_with_decode(self):
        record = {
            "ok": True,
            "completion_tokens": 256,
            "output_token_ids_count": 256,
            "cached_tokens_details": {"device": 10, "host": 0, "storage": 0},
        }
        self.assertTrue(MODULE.source_restore_qualified(record, "l1", 256))
        record["cached_tokens_details"]["host"] = 1
        self.assertFalse(MODULE.source_restore_qualified(record, "l1", 256))

    def test_l2_allows_shared_ancestor_in_device_with_lower_tier_ready(self):
        record = {
            "rid": "r",
            "ok": True,
            "completion_tokens": 256,
            "output_token_ids_count": 256,
            "cached_tokens_details": {"device": 100, "host": 50, "storage": 0},
            "restore_evidence": {
                "ready_events": ["evt=ready_host rid=r finalize_result=accepted"]
            },
        }
        self.assertTrue(MODULE.source_restore_qualified(record, "l2", 256))
        record["cached_tokens_details"]["storage"] = 10
        self.assertFalse(MODULE.source_restore_qualified(record, "l2", 256))

    def test_l2_requires_accepted_restore_ready_and_decode(self):
        record = {
            "rid": "r",
            "ok": True,
            "completion_tokens": 256,
            "output_token_ids_count": 256,
            "cached_tokens_details": {"device": 40, "host": 100, "storage": 0},
            "restore_evidence": {
                "restore_events": ["restore"],
                "ready_events": ["evt=ready_host finalize_result=accepted"],
            },
        }
        record["restore_evidence"]["restore_events"] = ["evt=restore_disposition rid=r disposition=RESTORE requested=100 granted=100 reason=full"]
        record["restore_evidence"]["ready_events"] = [
            "evt=ready_host rid=r finalize_result=accepted"
        ]
        self.assertTrue(MODULE.source_restore_qualified(record, "l2", 256))
        record["restore_evidence"]["ready_events"] = [
            "evt=ready_host rid=r finalize_result=rejected"
        ]
        self.assertFalse(MODULE.source_restore_qualified(record, "l2", 256))
        record["restore_evidence"]["ready_events"] = [
            "evt=ready_host rid=other finalize_result=accepted"
        ]
        self.assertFalse(MODULE.source_restore_qualified(record, "l2", 256))
        record["restore_evidence"]["ready_events"] = [
            "evt=ready_host rid=r finalize_result=accepted"
        ]
        record["restore_evidence"]["restore_events"] = []
        record["restore_evidence"]["ready_events"] = []
        self.assertFalse(MODULE.source_restore_qualified(record, "l2", 256))
        record["restore_evidence"]["ready_events"] = ["evt=ready_host rid=r finalize_result=accepted"]
        record["restore_evidence"]["restore_events"] = ["evt=restore_disposition rid=r disposition=RESTORE requested=100 granted=100"]
        self.assertTrue(MODULE.source_restore_qualified(record, "l2", 256))
        record["completion_tokens"] = 255
        self.assertFalse(MODULE.source_restore_qualified(record, "l2", 256))

    def test_l3_requires_rid_correlated_physical_read_and_ready(self):
        read = "evt=extent_read rid=r succeeded_keys=4 physical_bytes=4096"
        record = {
            "rid": "r",
            "ok": True,
            "completion_tokens": 256,
            "output_token_ids_count": 256,
            "cached_tokens_details": {"device": 25, "host": 0, "storage": 100},
            "restore_evidence": {
                "extent_reads": [read],
                "restore_events": ["evt=restore_disposition rid=r disposition=RESTORE requested=100 granted=100 reason=full"],
                "ready_events": ["evt=ready_host rid=r finalize_result=accepted"],
            },
        }
        self.assertTrue(MODULE.source_restore_qualified(record, "l3", 256))
        record["cached_tokens_details"]["device"] = 1
        self.assertTrue(MODULE.source_restore_qualified(record, "l3", 256))
        record["cached_tokens_details"]["device"] = 0
        record["restore_evidence"]["ready_events"] = ["evt=ready_host rid=r finalize_result=rejected"]
        self.assertFalse(MODULE.source_restore_qualified(record, "l3", 256))
        record["restore_evidence"]["ready_events"] = ["evt=ready_host rid=r finalize_result=accepted"]
        # The parser's RID join is the required boundary: unrelated RIDs never
        # enter this record's extent_reads list.
        record["restore_evidence"]["extent_reads"] = []
        self.assertFalse(MODULE.source_restore_qualified(record, "l3", 256))
        record["restore_evidence"]["extent_reads"] = [
            read.replace("physical_bytes=4096", "physical_bytes=0")
        ]
        record["cached_tokens_details"]["storage"] = 0
        self.assertFalse(MODULE.source_restore_qualified(record, "l3", 256))

    def test_mixed_restore_requires_host_and_storage(self):
        record = {
            "rid": "r",
            "ok": True,
            "completion_tokens": 256,
            "output_token_ids_count": 256,
            "cached_tokens_details": {"device": 25, "host": 10, "storage": 20},
            "restore_evidence": {
                "extent_reads": ["evt=extent_read rid=r succeeded_keys=2 physical_bytes=10"],
                "restore_events": ["evt=restore_disposition rid=r disposition=RESTORE requested=20 granted=20 reason=full"],
                "ready_events": ["evt=ready_host rid=r finalize_result=accepted"],
            },
        }
        self.assertTrue(MODULE.source_restore_qualified(record, "mixed", 256))
        record["cached_tokens_details"]["host"] = 0
        self.assertFalse(MODULE.source_restore_qualified(record, "mixed", 256))

    def test_frontier_wait_grant_retry_ready_join(self):
        record = {
            "rid": "r",
            "ok": True,
            "completion_tokens": 256,
            "output_token_ids_count": 256,
            "cached_tokens_details": {"device": 0, "host": 64, "storage": 0},
            "restore_evidence": {
                "frontier_wait_events": [{"line_index": 1, "line": "evt=frontier_wait rid=r wait_id=w", "wait_id": "w"}],
                "frontier_wake_events": [{"line_index": 2, "line": "evt=frontier_wake rid=r wait_id=w", "wait_id": "w"}],
                "frontier_wait_ids": ["w"],
                "frontier_wake_ids": ["w"],
                "retry_events": [{"line_index": 3, "line": "evt=restore_retry rid=r cause=frontier"}],
                "ready_line_indices": [4],
                "ready_events": [
                    "evt=ready_host rid=r finalize_result=accepted"
                ],
            },
        }
        self.assertTrue(MODULE.frontier_recovery_qualified(record, 256))
        record["restore_evidence"]["frontier_wake_events"][0]["line_index"] = 0
        self.assertFalse(MODULE.frontier_recovery_qualified(record, 256))
        record["restore_evidence"]["frontier_wake_events"][0]["line_index"] = 2
        record["restore_evidence"]["frontier_wake_ids"] = ["different"]
        self.assertFalse(MODULE.frontier_recovery_qualified(record, 256))
        record["restore_evidence"]["frontier_wake_ids"] = ["w"]
        record["restore_evidence"]["retry_events"] = []
        self.assertFalse(MODULE.frontier_recovery_qualified(record, 256))

    def test_real_tree_trace_schema_operations(self):
        events = [
            {"operation": "split_new_prefix"},
            {"operation": "split_old_child"},
            {"operation": "backup_commit", "full_host_after": True},
        ]
        MODULE.validate_radix_events(events)
        with self.assertRaises(ValueError):
            MODULE.validate_radix_events([{"operation": "split"}])

    def test_restore_log_joins_only_exact_rids(self):
        lines = [
            "[P3] evt=extent_read rid=r1 attempt_id=a1 succeeded_keys=1 physical_bytes=64 requested_bytes=64 preads=1",
            "[P3] evt=extent_read rid=r10 attempt_id=a10 succeeded_keys=1 physical_bytes=64 requested_bytes=64 preads=1",
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "server.log"
            path.write_text("\n".join(lines) + "\n")
            joined = MODULE.parse_restore_log(path, ["r1", "r10"])
        self.assertEqual(len(joined["r1"]["extent_reads"]), 1)
        self.assertIn("rid=r1 ", joined["r1"]["extent_reads"][0])
        self.assertIn("rid=r10 ", joined["r10"]["extent_reads"][0])


if __name__ == "__main__":
    unittest.main()
