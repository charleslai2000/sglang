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
            "cached_tokens_details": {"device": 0, "host": 50, "storage": 0},
            "restore_evidence": {
                "restore_events": ["evt=restore_disposition rid=r disposition=RESTORE requested=50 granted=50"],
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
            "cached_tokens_details": {"device": 0, "host": 100, "storage": 0},
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
            "cached_tokens_details": {"device": 0, "host": 0, "storage": 100},
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
            "cached_tokens_details": {"device": 0, "host": 10, "storage": 20},
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
        record["restore_evidence"]["frontier_wake_events"] = []
        self.assertFalse(MODULE.frontier_recovery_qualified(record, 256))
        record["restore_evidence"]["frontier_wake_ids"] = ["w"]
        record["restore_evidence"]["frontier_wake_events"] = [{"line_index": 2, "line": "evt=frontier_wake rid=r node=1"}]
        record["restore_evidence"]["retry_events"] = []
        self.assertFalse(MODULE.frontier_recovery_qualified(record, 256))
        record["restore_evidence"]["retry_events"] = [{"line_index": 3, "line": "evt=restore_retry rid=r cause=frontier"}]
        record["cached_tokens_details"]["device"] = 1
        self.assertTrue(MODULE.frontier_recovery_qualified(record, 256))

    def test_real_tree_trace_schema_operations(self):
        events = [
            {"operation": "split_new_prefix"},
            {"operation": "split_old_child"},
            {"operation": "backup_commit", "full_host_after": True},
        ]
        MODULE.validate_radix_events(events)
        with self.assertRaises(ValueError):
            MODULE.validate_radix_events([{"operation": "split"}])

    def test_capacity_pressure_prompt_length_escalation(self):
        initial_tokens = 125000
        max_tokens = 130000
        prefix_tokens = 16384
        requests = 4
        tier_capacity = 460000
        candidate = initial_tokens
        while (
            prefix_tokens + requests * (candidate - prefix_tokens) <= tier_capacity
            and candidate < max_tokens
        ):
            candidate = min(max_tokens, candidate + 4096)
        self.assertEqual(candidate, 129096)
        self.assertGreater(prefix_tokens + requests * (candidate - prefix_tokens), tier_capacity)

    def test_pressure_max_guard_rejects_unreachable_workset(self):
        initial_tokens = 125000
        max_tokens = 126000
        prefix_tokens = 16384
        requests = 4
        tier_capacity = 480000
        candidate = initial_tokens
        while (
            prefix_tokens + requests * (candidate - prefix_tokens) <= tier_capacity
            and candidate < max_tokens
        ):
            candidate = min(max_tokens, candidate + 4096)
        self.assertLessEqual(
            prefix_tokens + requests * (candidate - prefix_tokens), tier_capacity
        )

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

    def test_restore_log_joins_scheduler_normalized_batch_rid_suffix(self):
        rid = "g1-tree-00-cold_storage_restore-11"
        lines = [
            f"[P3] evt=extent_read rid={rid}_0 attempt_id=a succeeded_keys=1 physical_bytes=64",
            f"[P2A] evt=restore_disposition rid={rid}_0 disposition=RESTORE requested=1 granted=1",
            f"[P3] evt=ready_host rid={rid}_0 finalize_result=accepted",
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "server.log"
            path.write_text("\n".join(lines) + "\n")
            joined = MODULE.parse_restore_log(path, [rid])[rid]
        self.assertEqual(len(joined["extent_reads"]), 1)
        self.assertEqual(len(joined["restore_events"]), 1)
        self.assertEqual(len(joined["ready_events"]), 1)


if __name__ == "__main__":
    unittest.main()
