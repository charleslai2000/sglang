"""Host staging capacity crop and ack-drain recovery (r60 C-8 defect).

C-8 measured 525 demand restores whose host staging allocation failed while the
requested span was 3.8-13.8 K tokens and only 0.2-0.9 K were free; every one was
revoked after the Extent read had already been performed.  These tests cover the
two bounded recoveries added for that chain:

* ``_staging_crop_length`` -- stage the prefix that fits instead of nothing,
  while never shortening a validated ``TRAILING_PAGES`` frontier.
* ``UnifiedRadixCache._drain_acks_and_reclaim_host`` -- one ack drain plus one
  eviction pass, mirroring the F1 recovery already used by
  ``_execute_kv_backup``.
"""

import unittest
from unittest import mock

from sglang.srt.mem_cache.hicache_storage import PoolHitPolicy
from sglang.srt.mem_cache.unified_radix_cache import (
    UnifiedRadixCache,
    _staging_crop_length,
)


class _Transfer:
    def __init__(self, hit_policy=None):
        self.hit_policy = hit_policy


class _Operation:
    def __init__(self, storage_hit_count=0, pool_transfers=None):
        self.storage_hit_count = storage_hit_count
        self.pool_transfers = pool_transfers


class TestStagingCropLength(unittest.TestCase):
    def test_no_crop_without_free_units(self):
        op = _Operation(storage_hit_count=4864)
        self.assertEqual(_staging_crop_length(op, 4864, 0, 1), 0)

    def test_no_crop_when_the_crop_is_too_small_to_pay_for_itself(self):
        op = _Operation(storage_hit_count=4864)
        # 512 of 4864 is below the 1/8 floor.
        self.assertEqual(_staging_crop_length(op, 4864, 512, 1), 0)

    def test_crops_to_the_free_prefix(self):
        op = _Operation(storage_hit_count=4864)
        self.assertEqual(_staging_crop_length(op, 4864, 1024, 1), 1024)

    def test_crop_is_page_aligned(self):
        op = _Operation(storage_hit_count=4864)
        self.assertEqual(_staging_crop_length(op, 4864, 1000, 64), 960)

    def test_full_grant_is_not_reported_as_a_crop(self):
        op = _Operation(storage_hit_count=4864)
        self.assertEqual(_staging_crop_length(op, 4864, 8192, 1), 4864)

    def test_trailing_pages_frontier_is_never_shortened(self):
        op = _Operation(
            storage_hit_count=4864,
            pool_transfers=[_Transfer(PoolHitPolicy.TRAILING_PAGES)],
        )
        self.assertEqual(_staging_crop_length(op, 4864, 1024, 1), 0)

    def test_all_pages_transfer_may_be_cropped(self):
        op = _Operation(
            storage_hit_count=4864,
            pool_transfers=[_Transfer(PoolHitPolicy.ALL_PAGES)],
        )
        self.assertEqual(_staging_crop_length(op, 4864, 1024, 1), 1024)


class _CacheShim:
    """Exercises the real method body without building a full cache."""

    drain_and_reclaim = UnifiedRadixCache._drain_acks_and_reclaim_host

    def __init__(self, reclaimed, drain_error=None):
        self.drained = 0
        self.evict_calls = []
        self._reclaimed = reclaimed
        self._drain_error = drain_error

    def drain_storage_control_queues_local(self):
        self.drained += 1
        if self._drain_error is not None:
            raise self._drain_error

    def evict_host(self, num_tokens):
        self.evict_calls.append(num_tokens)
        return self._reclaimed


class TestAckDrainReclaim(unittest.TestCase):
    def test_drains_once_then_evicts_the_shortfall(self):
        shim = _CacheShim(reclaimed=769)
        self.assertEqual(shim.drain_and_reclaim(4095), 769)
        self.assertEqual(shim.drained, 1)
        self.assertEqual(shim.evict_calls, [4095])

    def test_no_work_for_a_non_positive_request(self):
        shim = _CacheShim(reclaimed=769)
        self.assertEqual(shim.drain_and_reclaim(0), 0)
        self.assertEqual(shim.drained, 0)
        self.assertEqual(shim.evict_calls, [])

    def test_drain_failure_is_contained(self):
        shim = _CacheShim(reclaimed=769, drain_error=RuntimeError("boom"))
        with mock.patch("sglang.srt.mem_cache.unified_radix_cache.logger"):
            self.assertEqual(shim.drain_and_reclaim(4095), 0)
        self.assertEqual(shim.evict_calls, [])


if __name__ == "__main__":
    unittest.main()


class TestBackupShortfall(unittest.TestCase):
    """The margin-aware pre-check that keeps write-through feeding L3.

    r61 floor arm: with the staging floor set, the pre-check used raw
    ``available_size`` (which already includes the floor), saw room, skipped
    eviction, and the backup was dropped by ``alloc_writeback`` -- host backing
    up stopped after exactly one pool fill (169,630 of 6,670,455 tokens) and no
    L3 hit was ever served.
    """

    def test_room_accounts_for_the_floor(self):
        from sglang.srt.mem_cache.unified_radix_cache import _backup_shortfall

        # 16,384 free of which 16,384 is the floor -> no room for 1,024.
        self.assertEqual(_backup_shortfall(16384, 16384, 1024), 1024)

    def test_no_shortfall_when_the_floor_is_respected(self):
        from sglang.srt.mem_cache.unified_radix_cache import _backup_shortfall

        # 20,480 free, floor 16,384 -> 4,096 usable for a 1,024-token backup.
        self.assertEqual(_backup_shortfall(20480, 16384, 1024), 0)

    def test_zero_floor_matches_the_legacy_check(self):
        from sglang.srt.mem_cache.unified_radix_cache import _backup_shortfall

        self.assertEqual(_backup_shortfall(512, 0, 1024), 512)
        self.assertEqual(_backup_shortfall(4096, 0, 1024), 0)

    def test_floor_larger_than_the_pool_still_requests_the_whole_backup(self):
        from sglang.srt.mem_cache.unified_radix_cache import _backup_shortfall

        self.assertEqual(_backup_shortfall(100, 5000, 1024), 1024)


if __name__ == "__main__":
    unittest.main()
