from __future__ import annotations

import unittest
from types import SimpleNamespace

from sglang.srt.managers.scheduler_components.hicache_restore import RestoreState
from sglang.srt.managers.scheduler_components.ready_horizon import ReadyHorizonPolicy


class ReadyPrefetchResidencyReconcileTests(unittest.TestCase):
    def test_stale_completion_marker_is_cleared_after_host_eviction(self):
        class Cache:
            def __init__(self):
                self.markers = {"b": 8}

            def peek_prefetch_loaded_tokens(self, rid):
                return self.markers.get(rid, 0)

            def reconcile_prefetch_loaded_tokens(self, rid, resident):
                if not resident:
                    self.markers.pop(rid, None)

        cache = Cache()
        req = SimpleNamespace(
            rid="b",
            priority=None,
            hicache_restore_state=RestoreState.READY,
            hicache_ready_residency_valid=True,
        )
        policy = ReadyHorizonPolicy(frontier_n=4, watermark_low=1, watermark_high=2)
        # Before the LRU event, the last verified residency snapshot counts.
        self.assertTrue(policy._req_is_ready_resident(req, cache, False))
        # Ordinary LRU removed the prefix; fresh matching reports zero Host hit.
        cache.reconcile_prefetch_loaded_tokens(req.rid, resident=False)
        req.hicache_ready_residency_valid = False
        self.assertEqual(cache.peek_prefetch_loaded_tokens(req.rid), 0)
        self.assertFalse(policy._req_is_ready_resident(req, cache, False))

    def test_residency_mismatch_invalidates_ready_and_clears_stale_count(self):
        class Cache:
            def __init__(self):
                self.markers = {"b": 8}

            def peek_prefetch_loaded_tokens(self, rid):
                return self.markers.get(rid, 0)

            def reconcile_prefetch_loaded_tokens(self, rid, resident):
                if not resident:
                    self.markers.pop(rid, None)

        cache = Cache()
        req = SimpleNamespace(
            rid="b",
            priority=None,
            hicache_restore_state=RestoreState.READY,
            hicache_ready_residency_valid=True,
        )
        policy = ReadyHorizonPolicy(frontier_n=4, watermark_low=1, watermark_high=2)
        # A fresh rematch that finds no current Host tokens cannot consume the
        # historical prefetch-completion marker as present residency.
        cache.reconcile_prefetch_loaded_tokens(req.rid, resident=False)
        req.hicache_ready_residency_valid = False
        self.assertEqual(cache.peek_prefetch_loaded_tokens(req.rid), 0)
        self.assertFalse(policy._req_is_ready_resident(req, cache, False))

    def test_current_ready_requires_residency_reconciliation(self):
        class Cache:
            def peek_prefetch_loaded_tokens(self, _rid):
                return 8

        req = SimpleNamespace(
            rid="b",
            priority=None,
            hicache_restore_state=RestoreState.READY,
            hicache_ready_residency_valid=True,
        )
        policy = ReadyHorizonPolicy(frontier_n=4, watermark_low=1, watermark_high=2)
        self.assertTrue(policy._req_is_ready_resident(req, Cache(), False))
        req.hicache_ready_residency_valid = False
        self.assertFalse(policy._req_is_ready_resident(req, Cache(), False))
