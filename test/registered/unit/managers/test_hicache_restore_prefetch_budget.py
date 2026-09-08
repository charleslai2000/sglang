"""Regression coverage for cache-mode PREFETCH_BUDGET wake-ups."""

import time
import unittest
from types import SimpleNamespace

import sglang.srt.managers.scheduler as scheduler_mod
from sglang.srt.managers.scheduler import Scheduler
from sglang.srt.managers.scheduler_components.hicache_restore import (
    RestoreState,
    RestoreWaitReason,
)


class PrefetchBudgetWakeTests(unittest.TestCase):
    def _scheduler(self):
        allocator = SimpleNamespace(
            size_full=0,
            available_size=lambda: 0,
        )

        class Controller:
            prefetch_tokens_occupied = 0
            prefetch_capacity_limit = 10

            def prefetch_rate_limited(self):
                return self.prefetch_tokens_occupied >= self.prefetch_capacity_limit

        tree_cache = SimpleNamespace(
            cache_controller=Controller(),
            token_to_kv_pool_allocator=allocator,
            inflight_promotion_reserved=0,
            supports_mamba=lambda: False,
            evictable_size=lambda: 0,
            prefetch_threshold=1,
        )
        scheduler = Scheduler.__new__(Scheduler)
        scheduler.server_args = SimpleNamespace(
            hicache_restore_wait_timeout_s=60.0,
            hicache_promotion_margin_tokens=0,
        )
        scheduler.tree_cache = tree_cache
        scheduler.req_to_token_pool = allocator
        scheduler.page_size = 1
        scheduler.enable_hicache_storage = True
        scheduler.enable_ready_horizon = False
        return scheduler

    def _request(self, reason):
        return SimpleNamespace(
            rid="rate-denied",
            hicache_restore_state=RestoreState.WAIT_CAPACITY,
            hicache_restore_wait_reason=reason,
            hicache_restore_state_ts=time.perf_counter(),
            hicache_restore_miss_epoch=None,
            hicache_restore_miss_generation=None,
            hicache_restore_miss_anchor=None,
            full_untruncated_fill_ids=[0],
            prefix_indices=[],
            host_hit_length=0,
            output_ids=[],
            sampling_params=SimpleNamespace(max_new_tokens=0),
        )

    def test_rate_denied_waiter_retries_after_prefetch_release(self):
        scheduler = self._scheduler()
        controller = scheduler.tree_cache.cache_controller
        request = self._request(RestoreWaitReason.PREFETCH_BUDGET)
        controller.prefetch_tokens_occupied = controller.prefetch_capacity_limit

        self.assertFalse(scheduler._restore_wait_capacity_fits(request))

        # The in-flight prefetch finalized and released its host reservation;
        # device admission remains unavailable in this test.
        controller.prefetch_tokens_occupied = 0
        self.assertTrue(scheduler._restore_wait_capacity_fits(request))

        scheduler.waiting_queue = [request]
        scheduler._prefetch_kvcache = lambda req, *, demand_restore=False: None
        scheduler.tree_cache.pop_storage_prefetch_terminal = lambda rid: None
        scheduler.tree_cache.pop_storage_prefetch_miss = lambda rid: False
        scheduler.tree_cache.pop_frontier_ready = lambda rid: False

        original_get_memory = scheduler_mod.get_memory
        scheduler_mod.get_memory = lambda: SimpleNamespace(
            hicache_storage_prefetch_retry_poll_interval=0,
            hicache_storage_prefetch_retry_max_attempts=0,
        )
        try:
            scheduler._reconcile_restore_states()
        finally:
            scheduler_mod.get_memory = original_get_memory

        self.assertIs(request.hicache_restore_state, RestoreState.RESTORING)

    def test_device_quota_waiter_still_requires_device_capacity(self):
        scheduler = self._scheduler()
        request = self._request(RestoreWaitReason.DEVICE_QUOTA)

        self.assertFalse(scheduler._restore_wait_capacity_fits(request))


if __name__ == "__main__":
    unittest.main()
