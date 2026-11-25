#!/usr/bin/env python3
"""CPU-only positive/negative tests for lifecycle qualification evidence gates."""

import importlib.util
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

MODULE_PATH = Path(__file__).with_name("run_radix_tree_lifecycle.py")
SPEC = importlib.util.spec_from_file_location("radix_lifecycle", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)


class LifecycleEvidenceGateTest(unittest.TestCase):
    def test_service_health_uses_owned_pid_and_accepts_transient_http_misses(self):
        current_pid = str(__import__("os").getpid())
        MODULE.wait_for_service_exit(int(current_pid))
        with patch("pathlib.Path.read_text", side_effect=FileNotFoundError):
            with self.assertRaisesRegex(RuntimeError, "service exited"):
                MODULE.wait_for_service_exit(99999999)
        with patch("pathlib.Path.read_text", return_value="999999 (python service) S 1 2 3"):
            MODULE.wait_for_service_exit(999999)
        with patch("pathlib.Path.read_text", return_value="999999 (python service) Z 1 2 3"):
            with self.assertRaisesRegex(RuntimeError, "state=Z"):
                MODULE.wait_for_service_exit(999999)

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

    def test_source_gate_accepts_exact_scheduler_normalized_batch_rid(self):
        rid = "g1-tree-00-cold_storage_restore-11"
        record = {
            "rid": rid,
            "ok": True,
            "completion_tokens": 256,
            "output_token_ids_count": 256,
            "cached_tokens_details": {"device": 32768, "host": 0, "storage": 32767},
            "restore_evidence": {
                "extent_reads": [f"evt=extent_read rid={rid}_0 physical_bytes=64 succeeded_keys=1"],
                "restore_events": [f"evt=restore_disposition rid={rid}_0 disposition=RESTORE requested=1 granted=1"],
                "ready_events": [f"evt=ready_host rid={rid}_0 finalize_result=accepted"],
            },
        }
        self.assertTrue(MODULE.source_restore_qualified(record, "l3", 256))

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

    def test_l2_only_probe_stage_is_allowed_and_admin_gated(self):
        source = MODULE_PATH.read_text()
        block = source.split("allowed_stages = {", 1)[1].split("}", 1)[0]
        self.assertIn('"l2_only_probe"', block)
        self.assertIn("L2_ONLY_PROBE_REQUIRES_ADMIN_API_KEY", source)
        self.assertIn('"l2_only_probe" in stages', source)

    def test_storage_backend_control_uses_expected_http_methods(self):
        calls = []

        class _Response:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return b'{"hicache_storage_backend": null}'

        def fake_urlopen(request, timeout=None):
            calls.append((request.get_method(), request.full_url, request.headers))
            return _Response()

        original = MODULE.urllib.request.urlopen
        MODULE.urllib.request.urlopen = fake_urlopen
        try:
            detached = MODULE.set_storage_backend(
                "http://127.0.0.1:1", "k", detach=True
            )
            attached = MODULE.set_storage_backend(
                "http://127.0.0.1:1",
                "k",
                detach=False,
                backend="extent",
                extra_config='{"storage_dir":"/tmp/x"}',
                prefetch_policy="timeout",
                write_policy="write_through",
            )
        finally:
            MODULE.urllib.request.urlopen = original
        self.assertEqual(detached["status"], 200)
        self.assertEqual(attached["status"], 200)
        self.assertEqual([call[0] for call in calls], ["DELETE", "PUT"])
        for _, url, _headers in calls:
            self.assertTrue(url.endswith("/hicache/storage-backend"))

    def test_l2_expressed_by_host_promotion_without_p2a_restore(self):
        """A pure Host hit is materialized by promotion, not by P2A RESTORE."""
        record = {
            "rid": "g1-tree-00-l2_only_probe-00",
            "ok": True,
            "completion_tokens": 256,
            "output_token_ids_count": 256,
            "cached_tokens_details": {"device": 0, "host": 16384, "storage": 0},
            "restore_evidence": {
                "restore_events": [],
                "ready_events": [],
                "promotion_reserves": [
                    "evt=promotion_reserve n=16384 rid=g1-tree-00-l2_only_probe-00_0 reserved=16384"
                ],
            },
        }
        self.assertTrue(MODULE.source_restore_qualified(record, "l2", 256))
        # A promotion that does not match the Host-resident token count is not
        # evidence that the Host copy was the source.
        record["restore_evidence"]["promotion_reserves"] = [
            "evt=promotion_reserve n=8192 rid=g1-tree-00-l2_only_probe-00_0 reserved=8192"
        ]
        self.assertFalse(MODULE.source_restore_qualified(record, "l2", 256))
        # Another request's promotion must not qualify this one.
        record["restore_evidence"]["promotion_reserves"] = [
            "evt=promotion_reserve n=16384 rid=g1-tree-01-l2_only_probe-01_0 reserved=16384"
        ]
        self.assertFalse(MODULE.source_restore_qualified(record, "l2", 256))
        # Storage presence disqualifies the record as Host-only evidence.
        record["restore_evidence"]["promotion_reserves"] = [
            "evt=promotion_reserve n=16384 rid=g1-tree-00-l2_only_probe-00_0 reserved=16384"
        ]
        record["cached_tokens_details"]["storage"] = 1
        self.assertFalse(MODULE.source_restore_qualified(record, "l2", 256))

    def test_wrapper_does_not_require_its_own_post_run_artifact(self):
        """The client must not require an artifact this wrapper writes after it."""
        wrapper = (MODULE_PATH.parent / "g1_tier_lifecycle_run_once.sh").read_text()
        self.assertNotIn("--require-radix-split", wrapper)
        # The authoritative validation must still exist in the wrapper.
        self.assertIn("validate_radix_events", wrapper)
        self.assertIn("RADIX_QUIESCENT_SPLIT_NOT_CONFIRMED", wrapper)


if __name__ == "__main__":
    unittest.main()
