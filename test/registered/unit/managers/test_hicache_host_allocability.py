"""Deterministic HOST_ALLOC generation and wake regressions."""

import inspect
import json
import unittest
from types import SimpleNamespace

from sglang.srt.managers.scheduler import Scheduler
from sglang.srt.managers.scheduler_components.hicache_restore import (
    HostAllocFailure,
    HostAllocabilitySnapshot,
    HostAllocWaitCursor,
    HostAllocWakeArbiter,
    RestoreEvent,
    RestoreState,
    RestoreWaitReason,
)
from sglang.srt.mem_cache.hicache_storage import PoolHitPolicy, PoolName, PoolTransfer
from sglang.srt.mem_cache.unified_radix_cache import _storage_hit_crop_is_safe


def _snapshot(kv=0, mamba=0, *, free_kv=0, free_mamba=0, evict_kv=0, evict_mamba=0):
    return HostAllocabilitySnapshot(
        cache_instance_id=1,
        generation_by_pool={"kv": kv, "mamba": mamba},
        free_units_by_pool={"kv": free_kv, "mamba": free_mamba},
        evictable_units_by_pool={"kv": evict_kv, "mamba": evict_mamba},
    )


def _request(rid, snapshot, blocked=("kv",), aux=None):
    return SimpleNamespace(
        rid=rid,
        hicache_restore_state=RestoreState.WAIT_CAPACITY,
        hicache_restore_wait_reason=RestoreWaitReason.HOST_ALLOC,
        hicache_host_alloc_wait_cursor=HostAllocWaitCursor(
            snapshot=snapshot,
            blocked_domains=frozenset(blocked),
            requested_primary_tokens=54976,
            required_aux_units=aux or {},
            fifo_sequence=0,
        ),
        hicache_host_alloc_attempt_id=None,
        hicache_host_alloc_last_attempt_id=None,
    )


class _SnapshotCache:
    def __init__(self, snapshot):
        self.snapshot = snapshot
        self.cache_controller = SimpleNamespace(prefetch_rate_limited=lambda: False)

    def host_allocability_snapshot(self, _required=None):
        return self.snapshot


class HostAllocabilityWakeTests(unittest.TestCase):
    def _scheduler(self, cache):
        scheduler = Scheduler.__new__(Scheduler)
        scheduler.tree_cache = cache
        scheduler.waiting_queue = []
        scheduler.server_args = SimpleNamespace(hicache_restore_wait_timeout_s=60.0)
        scheduler._host_alloc_wake_arbiter = HostAllocWakeArbiter()
        return scheduler

    def test_unlock_to_evict_and_actual_free_are_generation_opportunities(self):
        cache = _SnapshotCache(_snapshot(free_kv=1024, evict_kv=0))
        scheduler = self._scheduler(cache)
        req = _request("unlock", _snapshot(free_kv=1024, evict_kv=0))
        scheduler.waiting_queue = [req]
        scheduler._host_alloc_wake_arbiter.enqueue(req.rid)

        # Unlock-to-evict: free count stays below the full span, but the
        # tree-owned evictable amount changes and grants the normal allocator.
        cache.snapshot = _snapshot(kv=1, free_kv=1024, evict_kv=54976)
        self.assertEqual(scheduler._select_host_alloc_waiter(), "unlock")

        # Actual free is another causal opportunity; no fit proof is needed
        # before the authoritative alloc -> evict -> alloc path runs.
        cache.snapshot = _snapshot(kv=2, free_kv=54976)
        self.assertTrue(scheduler._host_alloc_wait_eligible(req))

    def test_no_change_no_spin_and_failed_retry_rotates_fifo(self):
        initial = _snapshot(free_kv=1024)
        cache = _SnapshotCache(initial)
        scheduler = self._scheduler(cache)
        first = _request("first", initial)
        second = _request("second", initial)
        scheduler.waiting_queue = [first, second]
        scheduler._host_alloc_wake_arbiter.enqueue(first.rid)
        scheduler._host_alloc_wake_arbiter.enqueue(second.rid)

        # HAE-03: unchanged state never grants a retry.
        self.assertIsNone(scheduler._select_host_alloc_waiter())

        cache.snapshot = _snapshot(kv=1, free_kv=1024, evict_kv=2048)
        self.assertEqual(scheduler._select_host_alloc_waiter(), "first")
        scheduler._host_alloc_wake_arbiter.record_attempt_result(
            first.rid, cache.snapshot, first.hicache_host_alloc_wait_cursor.blocked_domains
        )
        first.hicache_host_alloc_wait_cursor = HostAllocWaitCursor(
            snapshot=cache.snapshot,
            blocked_domains=frozenset({"kv"}),
            requested_primary_tokens=54976,
            required_aux_units={},
            fifo_sequence=1,
        )
        # The failed attempt's post-cleanup vector cannot immediately wake
        # itself, and the single grant was consumed for this generation.
        self.assertIsNone(scheduler._select_host_alloc_waiter())

        cache.snapshot = _snapshot(kv=2, free_kv=1024, evict_kv=4096)
        self.assertEqual(scheduler._select_host_alloc_waiter(), "second")

    def test_auxiliary_blocked_hybrid_requires_auxiliary_generation(self):
        initial = _snapshot(free_kv=1024, free_mamba=0)
        cache = _SnapshotCache(initial)
        scheduler = self._scheduler(cache)
        req = _request("hybrid", initial, blocked=("kv", "mamba"), aux={"mamba": 1})
        scheduler.waiting_queue = [req]
        scheduler._host_alloc_wake_arbiter.enqueue(req.rid)

        cache.snapshot = _snapshot(kv=1, mamba=0, free_kv=54976, free_mamba=0)
        self.assertIsNone(scheduler._select_host_alloc_waiter())
        cache.snapshot = _snapshot(kv=1, mamba=1, free_kv=54976, free_mamba=1)
        self.assertEqual(scheduler._select_host_alloc_waiter(), "hybrid")

    def test_failure_is_full_span_and_trailing_sidecar_cannot_be_cropped(self):
        snapshot = _snapshot(kv=3, mamba=1)
        failure = HostAllocFailure(
            requested_primary_tokens=54976,
            required_aux_units={PoolName.MAMBA.value: 1},
            failed_domains=frozenset({PoolName.MAMBA.value}),
            positive_hit_tokens=54976,
            sidecar_hit_pages={PoolName.KV.value: 54976, PoolName.MAMBA.value: 1},
            allocability_snapshot=snapshot,
        )
        self.assertTrue(failure.full_span_only)
        self.assertEqual(failure.failed_domains, frozenset({"mamba"}))
        operation = SimpleNamespace(
            storage_hit_count=54976,
            pool_transfers=[
                PoolTransfer(
                    name=PoolName.MAMBA,
                    hit_policy=PoolHitPolicy.TRAILING_PAGES,
                )
            ],
        )
        self.assertFalse(_storage_hit_crop_is_safe(operation, 54975))

    def test_positive_hit_retry_has_no_lower_frontier_crop_path(self):
        from sglang.srt.mem_cache.unified_radix_cache import UnifiedRadixCache

        source = inspect.getsource(
            UnifiedRadixCache._drain_storage_control_queues_impl
        )
        self.assertNotIn("_storage_hit_crop_is_safe(operation", source)

    def test_waiter_departure_removes_fifo_entry_immediately(self):
        cache = _SnapshotCache(_snapshot())
        scheduler = self._scheduler(cache)
        req = _request("depart", _snapshot())
        scheduler._host_alloc_wake_arbiter.enqueue(req.rid)
        scheduler._apply_restore_event(req, RestoreEvent.TIMEOUT)
        self.assertEqual(scheduler._host_alloc_wake_arbiter.ordered_rids(), ())

    def test_lock_release_telemetry_uses_numeric_zero_units_and_schema(self):
        from sglang.srt.mem_cache.unified_radix_cache import UnifiedRadixCache

        cache = UnifiedRadixCache.__new__(UnifiedRadixCache)
        cache._host_allocability_generations = {"kv": 0}
        cache._host_allocability_instance_id = 1
        cache._host_allocability_telemetry_seq = 0
        cache._host_evictable_signature = lambda _pool: (0, frozenset())
        with self.assertLogs(
            "sglang.srt.mem_cache.unified_radix_cache", level="INFO"
        ) as records:
            cache._bump_host_allocability("kv", "lock_release_evictable")
        payload = json.loads(records.output[-1].split("[HAE] ", 1)[1])
        self.assertEqual(payload["schema"], "host_alloc.v1")
        self.assertEqual(payload["returned_units"], 0)
        self.assertIsInstance(payload["ts_mono_ns"], int)
        self.assertIn("rank", payload)

    def test_cache_generation_bumps_only_for_completed_or_changed_mutations(self):
        from sglang.srt.mem_cache.unified_radix_cache import UnifiedRadixCache

        cache = UnifiedRadixCache.__new__(UnifiedRadixCache)
        cache._host_allocability_generations = {"kv": 0}
        cache._host_allocability_instance_id = 1
        cache._host_allocability_telemetry_seq = 0
        signatures = {"kv": (0, frozenset())}
        cache._host_evictable_signature = lambda pool: signatures[pool]
        cache._bump_host_allocability("kv", "direct_free", 0)
        self.assertEqual(cache._host_allocability_generations["kv"], 0)
        cache._bump_host_allocability("kv", "direct_free", 8)
        self.assertEqual(cache._host_allocability_generations["kv"], 1)
        signatures["kv"] = (8, frozenset({7}))
        cache._bump_changed_host_allocability(
            {"kv": (0, frozenset())}, "lock_release_evictable"
        )
        self.assertEqual(cache._host_allocability_generations["kv"], 2)


if __name__ == "__main__":
    unittest.main()
