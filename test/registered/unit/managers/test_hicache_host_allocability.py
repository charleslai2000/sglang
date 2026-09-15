"""Deterministic HOST_ALLOC generation and wake regressions."""

import inspect
import json
import time
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
from sglang.srt.mem_cache.telemetry_context import (
    DEPLOYMENT_MANIFEST_DIGEST,
    SOURCE_HEAD,
    producer_context,
)


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
        # Keep the synthetic request inside the same monotonic-clock timeout
        # window used by the scheduler while retaining a deterministic age.
        hicache_restore_state_ts=time.perf_counter() - 1.0,
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
    def test_producer_context_is_internal_and_stable(self):
        first = producer_context(profile_values={"tp_size": 1})
        second = producer_context(profile_values={"tp_size": 1})
        self.assertEqual(first["run_id"], second["run_id"])
        self.assertEqual(first["profile_id"], second["profile_id"])
        self.assertEqual(first["source_head"], SOURCE_HEAD)
        self.assertEqual(
            first["deployment_manifest_digest"], DEPLOYMENT_MANIFEST_DIGEST
        )
        self.assertTrue(first["source_build"].startswith(f"{SOURCE_HEAD}:"))

    def test_host_alloc_records_have_producer_identity_and_join_slots(self):
        from sglang.srt.managers.scheduler import _log_host_alloc_telemetry

        with self.assertLogs("sglang.srt.managers.scheduler", level="INFO") as records:
            event_id = _log_host_alloc_telemetry(
                "restore_host_alloc_wait",
                worker="test",
                rank=0,
                rid="rid",
                wait_id="wait-1",
                lifecycle_key="rid:run",
                deadline_mono_ns=10,
            )
        payload = json.loads(records.output[-1].split("[HAE] ", 1)[1])
        self.assertEqual(payload["event_id"], event_id)
        self.assertEqual(payload["wait_id"], "wait-1")
        self.assertEqual(payload["lifecycle_key"], "rid:run")
        self.assertIsInstance(payload["run_id"], str)
        self.assertIsInstance(payload["source_build"], str)

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
            first.rid, cache.snapshot
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

    def test_aux_cleanup_satisfiable_domain_allows_self_wake(self):
        before_cleanup = _snapshot(kv=0, mamba=0, free_kv=1024, free_mamba=0)
        cache = _SnapshotCache(before_cleanup)
        scheduler = self._scheduler(cache)
        req = _request(
            "aux-failure",
            before_cleanup,
            blocked=("mamba",),
            aux={"mamba": 1},
        )
        scheduler.waiting_queue = [req]

        # The staged auxiliary allocation failure releases its mamba slots
        # before the cursor is captured, so the cursor's generation is already
        # the post-cleanup one and its own release does not read as an advance.
        # Under per-domain eligibility the released capacity (free mamba 1 >=
        # required 1) is itself a wake opportunity: the domain is no longer a
        # real constraint, so the request retries instead of starving.  (The
        # old all-generations-advanced rule held this request to timeout.)
        after_cleanup = _snapshot(kv=0, mamba=1, free_kv=1024, free_mamba=1)
        req.hicache_host_alloc_wait_cursor = HostAllocWaitCursor(
            snapshot=after_cleanup,
            blocked_domains=frozenset({"mamba"}),
            requested_primary_tokens=54976,
            required_aux_units={"mamba": 1},
            fifo_sequence=0,
        )
        cache.snapshot = after_cleanup
        scheduler._host_alloc_wake_arbiter.enqueue(req.rid)
        self.assertEqual(scheduler._select_host_alloc_waiter(), "aux-failure")

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


class HostAllocWaitEligibilityTests(unittest.TestCase):
    """Per-domain ``_host_alloc_wait_eligible`` semantics.

    A blocked domain stops blocking when either its generation advanced or it
    is already capacity-satisfiable (``free + evictable >= required``).  The
    second clause fixes the mamba-generation starvation case where a domain
    admitted at park time was never a real constraint.

    Protection #1 (allocator is authority): ``_host_alloc_wait_eligible`` only
    gates WAKE/RETRY -- it is a liveness predicate, never an allocation
    guarantee.  Allocation success/failure is decided by the cache allocator
    (``free + evictable >= required`` is only a pre-condition for attempting a
    retry), and a failed allocation re-parks the request via
    ``Scheduler._capture_host_alloc_wait`` ->
    ``HostAllocWakeArbiter.record_attempt_result`` (scheduler.py:3805-3812,
    hicache_restore.py:215).  No test here forces allocation success.
    """

    def _scheduler(self, cache):
        scheduler = Scheduler.__new__(Scheduler)
        scheduler.tree_cache = cache
        scheduler.waiting_queue = []
        scheduler.server_args = SimpleNamespace(hicache_restore_wait_timeout_s=60.0)
        scheduler._host_alloc_wake_arbiter = HostAllocWakeArbiter()
        return scheduler

    def test_all_blocked_domains_advanced_is_eligible(self):
        # Regression: the original invalidation signal still grants.
        initial = _snapshot(kv=0, mamba=0)
        cache = _SnapshotCache(initial)
        scheduler = self._scheduler(cache)
        req = _request(
            "all-advanced", initial, blocked=("kv", "mamba"), aux={"mamba": 1}
        )

        cache.snapshot = _snapshot(kv=1, mamba=1)
        self.assertTrue(scheduler._host_alloc_wait_eligible(req))

    def test_unchanged_but_satisfiable_domain_is_eligible(self):
        # The bug: mamba's generation is unchanged (0 -> 0) yet its requirement
        # (1 unit) is already covered by free (1).  kv advanced and is the only
        # real constraint, so the waiter must be eligible.
        initial = _snapshot(kv=0, mamba=0, free_kv=0, free_mamba=0)
        cache = _SnapshotCache(initial)
        scheduler = self._scheduler(cache)
        req = _request(
            "kv-advanced-mamba-satisfiable",
            initial,
            blocked=("kv", "mamba"),
            aux={"mamba": 1},
        )

        cache.snapshot = _snapshot(kv=1, mamba=0, free_kv=54976, free_mamba=1)
        self.assertTrue(scheduler._host_alloc_wait_eligible(req))

    def test_unchanged_and_unsatisfiable_domain_is_ineligible(self):
        # Fail-closed: mamba neither advanced nor has capacity, so it is a real
        # constraint and eligibility must be False.
        initial = _snapshot(kv=0, mamba=0, free_kv=0, free_mamba=0)
        cache = _SnapshotCache(initial)
        scheduler = self._scheduler(cache)
        req = _request(
            "kv-advanced-mamba-unsat",
            initial,
            blocked=("kv", "mamba"),
            aux={"mamba": 1},
        )

        cache.snapshot = _snapshot(kv=1, mamba=0, free_kv=54976, free_mamba=0)
        self.assertFalse(scheduler._host_alloc_wait_eligible(req))

    def test_advanced_but_unsatisfiable_domain_is_eligible(self):
        # Existing behavior preserved: a generation advance is sufficient even
        # when the pool currently has no free/evictable capacity.
        initial = _snapshot(kv=0, mamba=0, free_kv=0, free_mamba=0)
        cache = _SnapshotCache(initial)
        scheduler = self._scheduler(cache)
        req = _request(
            "mamba-advanced", initial, blocked=("kv", "mamba"), aux={"mamba": 1}
        )

        cache.snapshot = _snapshot(kv=1, mamba=1, free_kv=0, free_mamba=0)
        self.assertTrue(scheduler._host_alloc_wait_eligible(req))

    def test_zero_requirement_domain_does_not_block(self):
        # A blocked domain with no positive requirement is not a real
        # constraint and must not starve the waiter.
        initial = _snapshot(kv=0, mamba=0, free_kv=0, free_mamba=0)
        cache = _SnapshotCache(initial)
        scheduler = self._scheduler(cache)
        req = _request("aux-zero", initial, blocked=("kv", "mamba"), aux={"mamba": 0})

        cache.snapshot = _snapshot(kv=0, mamba=0, free_kv=54976, free_mamba=0)
        self.assertTrue(scheduler._host_alloc_wait_eligible(req))

    def test_both_domains_unchanged_but_both_satisfiable_is_eligible(self):
        # Protection #3c ("两个 domain 都无需等待"): NEITHER blocked domain
        # advanced (kv 0->0, mamba 0->0) yet BOTH are currently satisfiable --
        # kv ``free + evictable = 24672 + 42942 = 67614 >= 54976`` and mamba
        # ``free 75 >= 1``.  Neither domain is a real constraint, so the
        # waiter must be eligible (the R121 t_feasible state, with no
        # generation move at all).
        initial = _snapshot(kv=0, mamba=0, free_kv=0, free_mamba=0)
        cache = _SnapshotCache(initial)
        scheduler = self._scheduler(cache)
        req = _request(
            "both-satisfiable",
            initial,
            blocked=("kv", "mamba"),
            aux={"mamba": 1},
        )

        cache.snapshot = _snapshot(
            kv=0,
            mamba=0,
            free_kv=24672,
            free_mamba=75,
            evict_kv=42942,
        )
        self.assertTrue(scheduler._host_alloc_wait_eligible(req))

    def test_wake_then_allocation_failure_repark_does_not_spin(self):
        # Protection #3d -- anti-busy-loop.  Eligibility is NOT allocation
        # success: it only grants a WAKE/RETRY, and the cache allocator stays
        # authoritative.  When a granted retry's allocation fails, the product
        # re-parks via ``_capture_host_alloc_wait`` ->
        # ``record_attempt_result`` (scheduler.py:3805-3812), which suppresses
        # the post-cleanup generation vector so the SAME unchanged vector
        # cannot re-grant on every scheduler tick.
        #
        # Here neither blocked domain advances and both are satisfiable, so the
        # capacity clause alone would grant every pass; the arbiter's
        # last-granted-vector suppression is what prevents the spin.
        parked = _snapshot(kv=0, mamba=0, free_kv=0, free_mamba=0)
        cache = _SnapshotCache(parked)
        scheduler = self._scheduler(cache)
        req = _request(
            "repark",
            parked,
            blocked=("kv", "mamba"),
            aux={"mamba": 1},
        )
        scheduler.waiting_queue = [req]
        scheduler._host_alloc_wake_arbiter.enqueue(req.rid)

        # Current state: both domains satisfiable, generation vector unchanged.
        satisfiable = _snapshot(
            kv=0,
            mamba=0,
            free_kv=24672,
            free_mamba=75,
            evict_kv=42942,
        )
        cache.snapshot = satisfiable
        self.assertTrue(scheduler._host_alloc_wait_eligible(req))

        # 1-2) First wake is a genuine grant; the arbiter records its vector.
        self.assertEqual(scheduler._select_host_alloc_waiter(), "repark")
        self.assertEqual(
            scheduler._host_alloc_wake_arbiter.last_granted_vector,
            satisfiable.generation_vector(),
        )

        # 3) Retry allocation RACE FAILURE -> re-park.  Mirror the product
        #    branch for ``req.hicache_host_alloc_attempt_id is not None``: the
        #    global post-cleanup snapshot is handed to the arbiter and the
        #    attempt id is cleared.
        req.hicache_host_alloc_attempt_id = "repark:1"
        req.hicache_host_alloc_last_attempt_id = "repark:1"
        scheduler._host_alloc_wake_arbiter.record_attempt_result(
            req.rid,
            scheduler._host_alloc_global_snapshot() or satisfiable,
        )
        req.hicache_host_alloc_attempt_id = None

        # 4) Same unchanged vector: the capacity clause is still True, but the
        #    suppressed vector means no immediate re-grant (no busy loop).
        self.assertTrue(scheduler._host_alloc_wait_eligible(req))
        self.assertIsNone(scheduler._select_host_alloc_waiter())

        # Non-vacuous check: with the suppression removed, the identical
        # unchanged-vector state WOULD re-grant, so the None above is caused by
        # the guard and not by an inert predicate.
        suppressed = scheduler._host_alloc_wake_arbiter.last_granted_vector
        scheduler._host_alloc_wake_arbiter._last_granted_vector = None
        self.assertEqual(scheduler._select_host_alloc_waiter(), "repark")
        scheduler._host_alloc_wake_arbiter._last_granted_vector = suppressed

        # 5) A real state change (kv generation advances) re-enables the retry.
        cache.snapshot = _snapshot(
            kv=1,
            mamba=0,
            free_kv=24672,
            free_mamba=75,
            evict_kv=42942,
        )
        self.assertEqual(scheduler._select_host_alloc_waiter(), "repark")


if __name__ == "__main__":
    unittest.main()
