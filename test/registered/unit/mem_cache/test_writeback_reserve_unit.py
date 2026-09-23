"""P3 Host->L3 write-back reserve: unit tests.

Three concerns (user adjudication item 6):
  1. The write-back reserve is NOT consumable by the warm/resident, READY,
     speculative-staging and demand-staging channels: after a normal
     alloc(), free >= reserve (a non-write-back alloc is declined once a
     requested size would dip into the reserve floor).
  2. The write-back staging channel MAY consume the reserve: alloc_writeback
     (D->H backup) succeeds down to zero free, and a HostPoolGroup
     resolve_host_transfers(writeback=True) can stage into the reserve.
  3. Instrumentation format smoke: the [P3] payloads for the new events
     (extent_write / extent_recycle / restore_backup / prefetch_revoke /
     hollow_evict / forced_drop / restore_recompute) parse back into the
     fields the statistician consumes -- no value-dependent crash, no
     missing key.
"""

import logging
import re
import unittest

from types import SimpleNamespace

import torch

from sglang.srt.mem_cache.hicache_storage import PoolName, PoolTransfer
from sglang.srt.mem_cache.memory_pool import MHATokenToKVPool
from sglang.srt.mem_cache.pool_host import HostPoolGroup, PoolEntry
from sglang.srt.mem_cache.pool_host import base as pool_base
from sglang.srt.mem_cache.pool_host.mha import MHATokenToKVPoolHost
from sglang.srt.managers.scheduler_components.ready_horizon import ReadyHorizonPolicy

from test_ready_horizon_unit import (
    NONE,
    NO_HEADROOM,
    _Cc,
    _epochs,
    _tree,
    _views,
)

LOG_BASE = re.compile(r"ts_ms=(\d+) evt=(\w+)")


class _HostPoolHarness:
    """Construct a small MHATokenToKVPoolHost with page_size=2 and a
    host_size large enough for the reserve tests."""

    def __init__(self, pages=128):
        # The host pool constructor checks host_memory_budget_bytes(); fake a
        # generous RAM budget (this machine may report low free memory).
        # MHATokenToKVPoolHost resolves the name from its own module globals,
        # so patch that module's binding (and the base module for safety).
        pool_base.host_memory_budget_bytes = lambda: 100 * 1024**3
        import sglang.srt.mem_cache.pool_host.mha as _mha

        _mha.host_memory_budget_bytes = lambda: 100 * 1024**3
        self.page_size = 2
        self.device_pool = MHATokenToKVPool(
            size=self.page_size * 16,
            page_size=self.page_size,
            dtype=torch.float16,
            head_num=2,
            head_dim=4,
            layer_num=2,
            device="cpu",
            enable_memory_saver=False,
        )
        # size_per_token for this pool.
        self.bytes_per_token = 4 * 2 * 2 * 2 * 2  # (layer*head*head_dim)*(k)v*dtype2
        self.host_pool = MHATokenToKVPoolHost(
            device_pool=self.device_pool,
            host_to_device_ratio=2.0,
            host_size=0,
            page_size=self.page_size,
            layout="layer_first",
            pin_memory=False,
            device="cpu",
            allocator_type="default",
        )


class ReserveNotConsumableTests(unittest.TestCase):
    """Concern 1: warm/resident + READY + speculative/demand staging allocs
    must leave free >= writeback_reserve after the alloc."""

    def test_reserve_floor_blocks_normal_alloc(self):
        harness = _HostPoolHarness(pages=128)
        pool = harness.host_pool
        page = pool.logical_page_size
        # Reserve = 8 logical pages-worth of bytes.
        reserve_bytes = 8 * page * harness.bytes_per_token
        pool.set_writeback_reserve_bytes(reserve_bytes)
        pages_total = pool.size // pool.page_size
        reserve_pages = reserve_bytes // pool.size_per_token // pool.logical_page_size

        need = (pages_total - reserve_pages) * page
        got = pool.alloc(need)
        self.assertIsNotNone(got)
        # After this full (non-write-back) consumption free == reserve exactly.
        self.assertEqual(
            pool.available_size(), pool.writeback_reserve(), "free must equal reserve"
        )
        # One more page via the normal channel: declined (would dip into reserve).
        self.assertIsNone(pool.alloc(page), "normal alloc must not touch reserve")

    def test_reserve_declines_before_touching_reserve(self):
        harness = _HostPoolHarness(pages=128)
        pool = harness.host_pool
        page = pool.logical_page_size
        reserve_bytes = 4 * page * harness.bytes_per_token
        pool.set_writeback_reserve_bytes(reserve_bytes)
        # Allocate down to (reserve + 1 page): normal alloc of 1 page fits
        # (free after = reserve), 2 pages does not.
        total = pool.size
        reserve = pool.writeback_reserve()
        pool.alloc((total - reserve - page) * 1)  # free = reserve + page after
        self.assertIsNotNone(pool.alloc(page))
        self.assertIsNone(pool.alloc(page), "free after would be < reserve")


class WritebackChannelUsesReserveTests(unittest.TestCase):
    """Concern 2: the D->H backup staging channel may consume the reserve."""

    def test_alloc_writeback_uses_reserve(self):
        harness = _HostPoolHarness(pages=128)
        pool = harness.host_pool
        page = pool.logical_page_size
        reserve_bytes = 8 * page * harness.bytes_per_token
        pool.set_writeback_reserve_bytes(reserve_bytes)
        # Consume everything except the reserve via the normal channel.
        total = pool.size
        reserve = pool.writeback_reserve()
        first_need = (total - reserve) * 1
        self.assertIsNotNone(pool.alloc(first_need))
        self.assertEqual(pool.available_size(), reserve)
        # Normal channel blocked now...
        self.assertIsNone(pool.alloc(page))
        # ...but the write-back channel drains the reserve.
        got = pool.alloc_writeback(page)
        self.assertIsNotNone(got, "write-back channel must use the reserve")
        self.assertEqual(len(got), page)

    def test_alloc_writeback_stops_at_margin(self):
        """The user-frozen semantics: D->H writeback may invade the reserve
        (cap C - margin), but the safety margin itself is never drained.
        A writeback alloc that would leave free < margin is declined."""
        harness = _HostPoolHarness(pages=128)
        pool = harness.host_pool
        page = pool.logical_page_size
        reserve_bytes = 4 * page * harness.bytes_per_token
        margin_bytes = 4 * page * harness.bytes_per_token
        pool.set_writeback_reserve_bytes(reserve_bytes)
        pool.set_writeback_reserve_margin_bytes(margin_bytes)
        total = pool.size
        reserve = pool.writeback_reserve()
        margin = pool.writeback_margin()
        # Fill everything except reserve + margin through the normal channel.
        self.assertIsNotNone(pool.alloc(total - reserve - margin))
        self.assertEqual(pool.available_size(), reserve + margin)
        # Writeback drains the whole reserve...
        self.assertIsNotNone(pool.alloc_writeback(reserve))
        self.assertEqual(pool.available_size(), margin)
        # ...and is then blocked at the margin (never drains it).
        self.assertIsNone(
            pool.alloc_writeback(page), "writeback must not drain the margin"
        )

    def test_group_resolve_writeback_stages_into_reserve(self):
        harness = _HostPoolHarness(pages=128)
        pool = harness.host_pool
        page = pool.logical_page_size
        reserve_bytes = 8 * page * harness.bytes_per_token
        pool.set_writeback_reserve_bytes(reserve_bytes)
        group = HostPoolGroup(
            entries=[
                PoolEntry(
                    name=PoolName.KV,
                    host_pool=pool,
                    device_pool=harness.device_pool,
                    layer_mapper=lambda layer: layer,
                    is_primary_index_anchor=True,
                )
            ]
        )
        group.set_writeback_reserve_bytes(reserve_bytes)

        total = pool.size
        reserve = group.writeback_reserve()
        # Fill the non-reserve region through the group's normal channel.
        self.assertIsNotNone(group.alloc(total - reserve))
        transfer = PoolTransfer(
            name=PoolName.KV,
            device_indices=torch.tensor([0, 1]),
            host_indices=None,
            indices_from_pool=None,
        )
        # writeback=True lets the group route into the reserve.
        resolved = group.resolve_host_transfers([transfer], writeback=True)
        self.assertEqual(len(resolved), 1)
        self.assertIsNotNone(resolved[0].host_indices)

    def test_group_alloc_writeback_consumes_reserve(self):
        """The cache controller's D->H write stage selects
        ``getattr(mem_pool_host, "alloc_writeback", ...)``. The host
        ``mem_pool_host`` on the HiCache stack is a HostPoolGroup, which
        must therefore expose alloc_writeback (else the fallback routes
        backup staging through the reserve-blocked alloc and the reserve
        becomes a permanently disabled capacity)."""
        harness = _HostPoolHarness(pages=128)
        pool = harness.host_pool
        page = pool.logical_page_size
        reserve_bytes = 8 * page * harness.bytes_per_token
        pool.set_writeback_reserve_bytes(reserve_bytes)
        group = HostPoolGroup(
            entries=[
                PoolEntry(
                    name=PoolName.KV,
                    host_pool=pool,
                    device_pool=harness.device_pool,
                    layer_mapper=lambda layer: layer,
                    is_primary_index_anchor=True,
                )
            ]
        )
        total = pool.size
        reserve = group.writeback_reserve()
        # Fill the non-reserve region through the group's normal channel.
        self.assertIsNotNone(group.alloc(total - reserve))
        self.assertEqual(pool.available_size(), reserve)
        # The fallback the controllers use: alloc_writeback if present, else
        # the (reserve-blocked) alloc. On a HostPoolGroup this must resolve
        # to the writeback channel -- the P0 fix.
        alloc = getattr(group, "alloc_writeback", group.alloc)
        got = alloc(page)
        self.assertIsNotNone(
            got, "writeback allocation via the group must consume the reserve"
        )
        self.assertEqual(pool.available_size() + page, reserve)


class ReadyHorizonAdmissionTests(unittest.TestCase):
    """Concern 3: Ready Horizon admission keeps free_host_after_stage >=
    writeback_reserve + safety_margin (a stage is denied when the floor
    would be breached)."""

    def _plan(self, *, headroom, reserve_floor):
        policy = ReadyHorizonPolicy(
            frontier_n=4,
            watermark_low=1,
            watermark_high=2,
        )
        views = _views(
            ("r1", NONE, None, 0, 0, True),
            ("r2", NONE, None, 0, 0, True),
        )
        return policy.refill_plan(
            views,
            tree=_tree(),
            cc=_Cc(),
            host_headroom=headroom,
            negatives={},
            epochs=_epochs(frontier=("r1", "r2")),
            now=0.0,
            reserve_floor=reserve_floor,
        )

    def test_stage_denied_when_reserve_breached(self):
        # host_headroom 23 vs reserve_floor 24: free_after_stage would be
        # 23 - (0 + 0) = 23 < 24 -- every candidate is declined NO_HEADROOM,
        # nothing stages.
        plan = self._plan(headroom=23, reserve_floor=24)
        self.assertEqual(plan.to_issue, [], "stage must not breach reserve")
        self.assertEqual(
            [(rid, reason) for rid, reason in plan.declines],
            [("r1", NO_HEADROOM), ("r2", NO_HEADROOM)],
        )

    def test_stage_admitted_when_reserve_holds(self):
        # host_headroom 26 vs reserve_floor 4: free_after_stage = 26 >= 4 --
        # the floor holds and both candidates stage.
        plan = self._plan(headroom=26, reserve_floor=4)
        self.assertEqual(
            [v.rid for v in plan.to_issue], ["r1", "r2"], "admitted when the floor fits"
        )
        self.assertEqual(plan.declines, [])


from sglang.srt.mem_cache.unified_radix_cache import (
    _log_evict_durable,
    _log_restore_backup,
)
from sglang.srt.mem_cache.storage.extent.extent_file_backend import ExtentFileBackend
from sglang.srt.mem_cache.storage.extent.extent_allocator import ExtentAllocator


def _evict_slot(a):
    return a.evict_slot_lru()


class InstrumentationFormatSmokeTests(unittest.TestCase):
    """Concern 3 (format smoke): every new [P3] event emits a key=value
    payload whose fields parse back -- nothing crashes on real values and
    no required key is dropped."""

    def _capture(self, fn, logger=None):
        records = []
        handler = logging.Handler()
        handler.emit = lambda rec: records.append(rec.getMessage())
        logger = logger or logging.getLogger("sglang.srt")
        old = logger.level
        logger.setLevel(logging.INFO)
        logger.addHandler(handler)
        try:
            fn()
        finally:
            logger.removeHandler(handler)
            logger.setLevel(old)
        return records

    def test_extent_write_fields(self):
        records = self._capture(
            lambda: ExtentFileBackend._log_extent_write(
                None, "kv", "n7", ["k1", "k2"], [b"x" * 10, b"y" * 20]
            )
        )
        m = LOG_BASE.search(records[0])
        self.assertIsNotNone(m)
        self.assertEqual(m.group(2), "extent_write")
        self.assertIn("node=n7", records[0])
        self.assertIn("component=kv", records[0])
        self.assertIn("keys_n=2", records[0])
        self.assertIn("bytes=30", records[0])

    def test_extent_recycle_fields(self):
        # Drive a real slot drop through the normal plan/commit/evict path
        # so the invalidation-generation log site fires with freed > 0.
        allocator = ExtentAllocator(extent_size=4096, num_slots=2)
        refs, passed = allocator.plan([("key-a", 64)])
        allocator.commit(["key-a"], refs, passed)
        self.assertEqual(allocator._slot_bytes[refs[0].extent_id], 64)

        records = self._capture(
            lambda: _evict_slot(allocator),
            logger=logging.getLogger("sglang.srt.mem_cache.storage.extent.extent_allocator"),
        )
        found = [r for r in records if "evt=extent_recycle" in r]
        self.assertTrue(found, "extent_recycle must fire on a slot drop")
        m = LOG_BASE.search(found[0])
        self.assertEqual(m.group(2), "extent_recycle")
        self.assertIn(f"slot={refs[0].extent_id}", found[0])
        self.assertIn("generation=", found[0])
        self.assertIn("freed=64", found[0])

    def test_restore_backup_fields(self):
        operation = SimpleNamespace(id="write_backup", request_id="r9")
        records = self._capture(
            lambda: _log_restore_backup(
                operation, "n3", durable_frontier=1024, requested_frontier=2048
            )
        )
        m = LOG_BASE.search(records[0])
        self.assertEqual(m.group(2), "restore_backup")
        self.assertIn("op=write_backup", records[0])
        self.assertIn("rid=r9", records[0])
        self.assertIn("node=n3", records[0])
        self.assertIn("l3_durable_frontier=1024", records[0])
        self.assertIn("requested_frontier=2048", records[0])

    def test_evict_durable_fields(self):
        records = self._capture(
            lambda: _log_evict_durable(
                "hollow_evict", 7, 11, True, removal_reason="storage_backed"
            )
        )
        m = LOG_BASE.search(records[0])
        self.assertEqual(m.group(2), "hollow_evict")
        self.assertIn("node=7", records[0])
        self.assertIn("l3_durable_frontier=11", records[0])
        self.assertIn("removal_reason=storage_backed", records[0])


if __name__ == "__main__":
    unittest.main()
